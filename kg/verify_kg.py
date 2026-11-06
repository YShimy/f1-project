"""Verify the F1 knowledge graph built by Create_kg.py (dev tool, not submitted).

Checks (docs/milestone2_plan.md section 6):
  1. counts: nodes per label, relationships per (source label, type, target label), totals,
     and no unexpected labels or relationship types
  2. types: every stored property has the schema type (INTEGER / FLOAT / STRING / DATE),
     and no node has a property outside the schema
  3. no sentinels: no property equals '\\N' or ''
  4. spot checks: 5 random CSV rows per table compared property by property, plus their links
  5. multiplicity: every node has exactly one relationship of each type its spec requires
  6. direction: relationships only run from the schema's source label to its target label

Exits non-zero on any failure. Expected numbers come from the Milestone 2 PDF and must
never be edited to make a run pass.

    python kg/verify_kg.py --data-dir data/raw --config kg/config.txt
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from neo4j import GraphDatabase

KG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(KG_DIR))
import Create_kg as kg  # noqa: E402

EXPECTED_NODES = {
    "Driver": 861, "Constructor": 212, "Circuit": 77, "Season": 75, "Status": 139,
    "Race": 1125, "Result": 26759, "Qualifying": 10494, "PitStop": 11371,
}
EXPECTED_RELS = {
    ("Race", "AT_CIRCUIT", "Circuit"): 1125,
    ("Race", "IN_SEASON", "Season"): 1125,
    ("Result", "FOR_RACE", "Race"): 26759,
    ("Result", "BY_DRIVER", "Driver"): 26759,
    ("Result", "FOR_CONSTRUCTOR", "Constructor"): 26759,
    ("Result", "HAS_STATUS", "Status"): 26759,
    ("Qualifying", "FOR_RACE", "Race"): 10494,
    ("Qualifying", "BY_DRIVER", "Driver"): 10494,
    ("Qualifying", "FOR_CONSTRUCTOR", "Constructor"): 10494,
    ("PitStop", "FOR_RACE", "Race"): 11371,
    ("PitStop", "BY_DRIVER", "Driver"): 11371,
}
EXPECTED_NODE_TOTAL = 51113
EXPECTED_REL_TOTAL = 163510
NEO4J_TYPE = {"int": "INTEGER", "float": "FLOAT", "str": "STRING", "date": "DATE"}
SPOT_ROWS = 5


class Checker:
    def __init__(self, session):
        self.session = session
        self.failures = 0

    def q(self, query, **params):
        return list(self.session.run(query, **params))

    def check(self, ok, message):
        print("  {} {}".format("PASS" if ok else "FAIL", message))
        if not ok:
            self.failures += 1


def check_counts(c: Checker) -> None:
    print("1. Counts")
    rows = c.q("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")
    got = {r["l"]: r["n"] for r in rows}
    for label, n in EXPECTED_NODES.items():
        c.check(got.get(label, 0) == n, "{:<12} nodes {:>7,} (expected {:,})".format(label, got.get(label, 0), n))
    extra = set(got) - set(EXPECTED_NODES)
    c.check(not extra, "no unexpected labels {}".format(sorted(extra) if extra else ""))
    total = c.q("MATCH (n) RETURN count(n) AS n")[0]["n"]
    c.check(total == EXPECTED_NODE_TOTAL, "total nodes {:,} (expected {:,})".format(total, EXPECTED_NODE_TOTAL))

    rows = c.q("MATCH (a)-[r]->(b) RETURN labels(a)[0] AS s, type(r) AS t, labels(b)[0] AS d, count(*) AS n")
    got_r = {(r["s"], r["t"], r["d"]): r["n"] for r in rows}
    for key, n in EXPECTED_RELS.items():
        c.check(got_r.get(key, 0) == n, "({})-[:{}]->({}) {:>7,} (expected {:,})".format(*key, got_r.get(key, 0), n))
    by_type = {}
    for (s, t, d), n in got_r.items():
        by_type[t] = by_type.get(t, 0) + n
    for t in ("FOR_RACE", "BY_DRIVER", "FOR_CONSTRUCTOR"):
        exp = sum(n for (s, tt, d), n in EXPECTED_RELS.items() if tt == t)
        c.check(by_type.get(t, 0) == exp, "{} total {:,} (expected {:,})".format(t, by_type.get(t, 0), exp))
    rel_total = sum(got_r.values())
    c.check(rel_total == EXPECTED_REL_TOTAL, "total relationships {:,} (expected {:,})".format(rel_total, EXPECTED_REL_TOTAL))


def check_direction(c: Checker) -> None:
    print("6. Direction (no relationship outside the schema's source->target pairs)")
    rows = c.q("MATCH (a)-[r]->(b) RETURN labels(a)[0] AS s, type(r) AS t, labels(b)[0] AS d, count(*) AS n")
    wrong = [(r["s"], r["t"], r["d"], r["n"]) for r in rows if (r["s"], r["t"], r["d"]) not in EXPECTED_RELS]
    c.check(not wrong, "all relationships follow the schema direction {}".format(wrong if wrong else ""))
    n = c.q("MATCH (:Race)-[:FOR_RACE]->() RETURN count(*) AS n")[0]["n"]
    c.check(n == 0, "(:Race)-[:FOR_RACE]->() count is {}".format(n))


def check_types(c: Checker) -> None:
    print("2. Property types and 3. no sentinels")
    for spec in kg.SPECS:
        expected = {p.name: NEO4J_TYPE[p.kind] for p in spec.props}
        if spec.key_fn is not None:
            expected[spec.key] = "STRING"
        rows = c.q(
            "MATCH (n:{}) UNWIND keys(n) AS k "
            "RETURN k, valueType(n[k]) AS t, count(*) AS n".format(spec.label)
        )
        bad = []
        for r in rows:
            want = expected.get(r["k"])
            got = r["t"].replace(" NOT NULL", "")
            if want != got:
                bad.append("{}={} x{} (want {})".format(r["k"], got, r["n"], want))
        c.check(not bad, "{:<12} types {}".format(spec.label, "; ".join(bad)))
        n = c.q(
            "MATCH (n:{}) UNWIND keys(n) AS k WITH n[k] AS v "
            "WHERE v = '' OR v = $nul RETURN count(*) AS n".format(spec.label),
            nul="\\N",
        )[0]["n"]
        c.check(n == 0, "{:<12} sentinel values: {}".format(spec.label, n))


def _native(value):
    return value.to_native() if hasattr(value, "to_native") else value


def check_spot(c: Checker, data_dir: Path, seed: int) -> None:
    print("4. Spot checks ({} random rows per table, seed {})".format(SPOT_ROWS, seed))
    rng = random.Random(seed)
    for spec in kg.SPECS:
        rows = list(kg.read_rows(data_dir / spec.file))
        bad = []
        for row in rng.sample(rows, SPOT_ROWS):
            item = kg.to_batch_row(row, spec)
            expected = dict(item["props"])
            expected[spec.key] = item["key"]
            rec = c.q("MATCH (n:{} {{{}: $k}}) RETURN properties(n) AS p".format(spec.label, spec.key), k=item["key"])
            if len(rec) != 1:
                bad.append("{} found {} nodes".format(item["key"], len(rec)))
                continue
            got = {k: _native(v) for k, v in rec[0]["p"].items()}
            if got != expected:
                diff = sorted(set(got.items()) ^ set(expected.items()), key=str)
                bad.append("{}: {}".format(item["key"], diff))
            for rel in spec.rels:
                tgt = c.q(
                    "MATCH (n:{} {{{}: $k}})-[:{}]->(t:{}) RETURN t.{} AS v".format(
                        spec.label, spec.key, rel.type, rel.target_label, rel.target_key
                    ),
                    k=item["key"],
                )
                if [r["v"] for r in tgt] != [item[rel.column]]:
                    bad.append("{} {} -> {} (want {})".format(item["key"], rel.type, [r["v"] for r in tgt], item[rel.column]))
        c.check(not bad, "{:<12} {}".format(spec.label, "; ".join(bad)))


def check_multiplicity(c: Checker) -> None:
    print("5. Multiplicity (exactly one of each required relationship)")
    for spec in kg.SPECS:
        for rel in spec.rels:
            n = c.q(
                "MATCH (a:{}) WITH a, COUNT {{ (a)-[:{}]->(:{}) }} AS c "
                "WHERE c <> 1 RETURN count(a) AS n".format(spec.label, rel.type, rel.target_label)
            )[0]["n"]
            c.check(n == 0, "{:<12} -[:{}]-> not exactly 1: {}".format(spec.label, rel.type, n))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify the F1 knowledge graph.")
    parser.add_argument("--data-dir", type=Path, default=KG_DIR.parent / "data" / "raw")
    parser.add_argument("--config", type=Path, default=KG_DIR / "config.txt")
    parser.add_argument("--seed", type=int, default=903)
    args = parser.parse_args(argv)

    config = kg.load_config(args.config)
    session_kwargs = {"database": config["DATABASE"]} if config.get("DATABASE") else {}
    with GraphDatabase.driver(config["URI"], auth=(config["USERNAME"], config["PASSWORD"])) as driver:
        with driver.session(**session_kwargs) as session:
            c = Checker(session)
            check_counts(c)
            check_types(c)
            check_spot(c, args.data_dir, args.seed)
            check_multiplicity(c)
            check_direction(c)
    print("\nRESULT: {}".format("ALL CHECKS PASSED" if c.failures == 0 else "{} CHECK(S) FAILED".format(c.failures)))
    return 0 if c.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
