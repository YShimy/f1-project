"""Dev-only: independent pandas answers to the 5 M2 verification questions, computed from the raw CSVs.

Used to cross-check kg/queries.txt (run against Neo4j). Writes kg/crosscheck_expected.json.
Usage: python kg/crosscheck.py [--data-dir data/raw]
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def load(data_dir: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(data_dir / f"{name}.csv", na_values=["\\N"], keep_default_na=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data" / "raw"))
    d = Path(ap.parse_args().data_dir)
    res, races, drv = load(d, "results"), load(d, "races"), load(d, "drivers")
    con, st = load(d, "constructors"), load(d, "status")
    drv["Driver"] = drv["forename"] + " " + drv["surname"]
    r = (res.merge(races[["raceId", "year", "circuitId", "date"]], on="raceId", validate="m:1")
            .merge(drv[["driverId", "Driver", "surname", "forename"]], on="driverId", validate="m:1")
            .merge(con[["constructorId", "name"]], on="constructorId", validate="m:1")
            .merge(st, on="statusId", validate="m:1"))
    assert len(r) == len(res)
    out = {}

    # Q1
    q = r[r.year == 2021].groupby(["driverId", "Driver"], as_index=False).agg(
        Points=("points", "sum"), Wins=("position", lambda s: int((s == 1).sum())))
    q = q.sort_values(["Points", "Wins", "Driver"], ascending=[False, False, True])
    out["1"] = q[["Driver", "Points", "Wins"]].to_dict("records")

    # Q2
    w = r[(r.year >= 2014) & (r.year <= 2021)].copy()
    w["cls"] = (w.status.eq("Finished") | w.status.str.startswith("+")).astype(int)
    q = w.groupby(["constructorId", "name"], as_index=False).agg(Entries=("resultId", "size"), Classified=("cls", "sum"))
    q = q[q.Entries >= 100].assign(Reliability=lambda x: x.Classified / x.Entries).rename(columns={"name": "Constructor"})
    q = q.sort_values(["Reliability", "Constructor"], ascending=[False, True])
    out["2"] = q[["Constructor", "Entries", "Classified", "Reliability"]].to_dict("records")

    # Q3
    h, b = r[r.driverId == 1], r[r.driverId == 822]
    m = h.merge(b, on=["raceId", "constructorId"], suffixes=("_h", "_b"))
    q = m.groupby("name_h", as_index=False).agg(
        Shared_Races=("raceId", "nunique"),
        Hamilton_Ahead=("positionOrder_h", lambda s: int((s < m.loc[s.index, "positionOrder_b"]).sum())),
        Bottas_Ahead=("positionOrder_b", lambda s: int((s < m.loc[s.index, "positionOrder_h"]).sum())),
    ).rename(columns={"name_h": "Constructor"})
    out["3"] = q.sort_values(["Shared_Races", "Constructor"], ascending=[False, True]).to_dict("records")

    # Q4
    mo = r[(r.circuitId == 6) & (pd.to_datetime(r.date) < "2020-01-01")
           & ~r.status.isin(["Did not qualify", "Did not prequalify", "Withdrew"])]
    q = mo.groupby(["driverId", "Driver"], as_index=False).agg(
        Starts=("raceId", "nunique"), Avg_Finish=("positionOrder", "mean"),
        Wins=("position", lambda s: int((s == 1).sum())))
    q = q[q.Starts >= 5].sort_values(["Avg_Finish", "Wins", "Driver"], ascending=[True, False, True])
    out["4"] = q[["Driver", "Starts", "Avg_Finish", "Wins"]].to_dict("records")

    # Q5
    s = r[r.year.isin([2020, 2021])]
    cnt = s.groupby(["driverId", "year", "constructorId"]).size().reset_index(name="n")
    cnt = cnt.sort_values(["driverId", "year", "n", "constructorId"], ascending=[True, True, False, True])
    top = cnt.drop_duplicates(["driverId", "year"]).pivot(index="driverId", columns="year", values="constructorId").dropna()
    changed = top[top[2020] != top[2021]].index
    names = drv[drv.driverId.isin(changed)].sort_values(["surname", "forename"])["Driver"].tolist()
    out["5"] = [{"Drivers_Changed": len(names), "Drivers": names}]

    def conv(o):
        return o.item() if hasattr(o, "item") else o

    path = Path(__file__).resolve().parent / "crosscheck_expected.json"
    path.write_text(json.dumps(out, indent=1, default=conv), encoding="utf-8", newline="\n")
    for k, v in out.items():
        print(f"Q{k}: {len(v)} rows; first: {v[:3]}")


if __name__ == "__main__":
    main()
