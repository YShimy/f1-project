"""Dev-only: independent pandas answers for kg/robustness_queries.txt (Phase 6 stress queries).

Computes each answer from the raw CSVs with pandas (never from the graph) and writes
kg/robustness_expected.json. Compare with:
    python kg/run_queries.py --queries kg/robustness_queries.txt --expected kg/robustness_expected.json --count 7 --strict-types
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def load(data_dir: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(data_dir / f"{name}.csv", na_values=["\\N"], keep_default_na=False)


def records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data" / "raw"))
    d = Path(ap.parse_args().data_dir)
    races = load(d, "races")
    res = load(d, "results").merge(races[["raceId", "year", "circuitId", "name", "date"]], on="raceId", validate="m:1")
    drv = load(d, "drivers")
    drv["Driver"] = drv["forename"] + " " + drv["surname"]
    out = {}

    # a. 2023 average pit stops per driver-race (driver-races that have at least one stop)
    ps = load(d, "pit_stops").merge(races[["raceId", "year"]], on="raceId")
    ps = ps[ps.year == 2023]
    pairs = ps.groupby(["raceId", "driverId"]).size()
    out["1"] = [{"Season": 2023, "Driver_Races": int(len(pairs)), "Pit_Stops": int(pairs.sum()),
                 "Avg_Stops": float(pairs.sum() / len(pairs))}]

    # b. pole-to-win conversion per season 2010-2024
    q = load(d, "qualifying").merge(races[["raceId", "year"]], on="raceId")
    poles = q[(q.position == 1) & q.year.between(2010, 2024)]
    wins = set(map(tuple, res[res.position == 1][["raceId", "driverId"]].values.tolist()))
    poles = poles.assign(won=[(r, dr) in wins for r, dr in zip(poles.raceId, poles.driverId)])
    g = poles.groupby("year").agg(Poles=("qualifyId", "size"), Pole_Wins=("won", "sum")).reset_index()
    g = g.rename(columns={"year": "Season"}).assign(Conversion=lambda x: x.Pole_Wins / x.Poles)
    out["2"] = records(g.sort_values("Season")[["Season", "Poles", "Pole_Wins", "Conversion"]])

    # c. races per circuit country, top 10
    circ = load(d, "circuits")
    rc = races.merge(circ[["circuitId", "country"]], on="circuitId", validate="m:1")
    g = rc.groupby("country").size().reset_index(name="Races").rename(columns={"country": "Country"})
    out["3"] = records(g.sort_values(["Races", "Country"], ascending=[False, True]).head(10))

    # d. 10 youngest race winners (age at their youngest win)
    w = res[res.position == 1].merge(drv[["driverId", "Driver", "dob"]], on="driverId", validate="m:1")
    w["date_d"] = pd.to_datetime(w.date)
    w["dob_d"] = pd.to_datetime(w.dob)
    w["Age_Days"] = (w.date_d - w.dob_d).dt.days
    w["Age_Years"] = (w.date_d.dt.year - w.dob_d.dt.year
                      - ((w.date_d.dt.month * 100 + w.date_d.dt.day) < (w.dob_d.dt.month * 100 + w.dob_d.dt.day)).astype(int))
    first = w.sort_values("Age_Days").drop_duplicates("driverId")
    first = first.rename(columns={"name": "Race", "year": "Season"})
    first = first.sort_values(["Age_Days", "Driver"]).head(10)
    out["4"] = records(first[["Driver", "Race", "Season", "Age_Days", "Age_Years"]])

    # e. most common non-classified statuses 1950-1979
    st = load(d, "status")
    e = res[res.year.between(1950, 1979)].merge(st, on="statusId", validate="m:1")
    e = e[~(e.status.eq("Finished") | e.status.str.startswith("+"))]
    g = e.groupby("status").size().reset_index(name="Entries").rename(columns={"status": "Status"})
    out["5"] = records(g.sort_values(["Entries", "Status"], ascending=[False, True]).head(10))

    # f. 2019 qualifying rows vs rows with a non-empty q3 (read as raw strings, not via pandas NA logic)
    qs = pd.read_csv(d / "qualifying.csv", dtype=str, keep_default_na=False).merge(
        races[["raceId", "year"]].astype({"raceId": str}), on="raceId")
    qs = qs[qs.year == 2019]
    has_q3 = ~qs.q3.str.strip().isin(["", "\\N"])
    out["6"] = [{"Qualifying_Entries": int(len(qs)), "With_Q3": int(has_q3.sum())}]

    # g. highest fastestLapSpeed per season at Monza 2004-2024
    monza = circ.loc[circ.circuitRef == "monza", "circuitId"].item()
    m = res[(res.circuitId == monza) & res.year.between(2004, 2024) & res.fastestLapSpeed.notna()]
    g = m.groupby("year").fastestLapSpeed.max().reset_index().rename(columns={"year": "Season", "fastestLapSpeed": "Top_Speed"})
    g["Top_Speed"] = g.Top_Speed.astype(float)
    out["7"] = records(g.sort_values("Season"))

    path = Path(__file__).resolve().parent / "robustness_expected.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    for k, v in out.items():
        print(f"Q{k}: {len(v)} rows; first: {v[:2]}")


if __name__ == "__main__":
    main()
