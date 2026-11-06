"""Dev-only: run kg/queries.txt against Neo4j and compare with kg/crosscheck_expected.json.

Parsing mimics the autograder: headers must match '^//(\\d)\\. Query \\1$', exactly 5, in order;
the file must be UTF-8 without a BOM, with LF line endings (no '\\r').
Comparison per query: identical column names (and order), same number of rows in the same
order, numbers equal to 2 dp, lists and strings equal exactly.

    python kg/run_queries.py [--queries kg/queries.txt] [--expected kg/crosscheck_expected.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from neo4j import GraphDatabase

KG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(KG_DIR))
from Create_kg import load_config  # noqa: E402

HEADER = re.compile(r"^//(\d)\. Query \1$", re.MULTILINE)
TOLERANCE = 0.005 + 1e-9  # "equal to 2 dp"
SHOW_ROWS = 3


def parse_queries(path: Path, count: int = 5) -> dict:
    raw = path.read_bytes()
    problems = []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("file starts with a UTF-8 BOM")
    if b"\r" in raw:
        problems.append("file contains {} carriage return(s) ('\\r'); use LF line endings".format(raw.count(b"\r")))
    text = raw.decode("utf-8")  # raises if not UTF-8
    headers = list(HEADER.finditer(text))
    numbers = [m.group(1) for m in headers]
    if numbers != [str(i) for i in range(1, count + 1)]:
        problems.append("headers found {} (expected 1..{} in order)".format(numbers, count))
    queries = {}
    for i, m in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[m.end():end].strip()
        if body.endswith(";"):
            problems.append("query {} ends with a semicolon".format(m.group(1)))
        if "//" in body:
            problems.append("query {} contains an extra // comment".format(m.group(1)))
        queries[m.group(1)] = body
    if problems:
        raise SystemExit("queries.txt format problems:\n  " + "\n  ".join(problems))
    return queries


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def values_equal(got, want, strict_types: bool = False) -> bool:
    if is_number(got) and is_number(want):
        if strict_types and type(got) is not type(want):  # e.g. a float stored as an int
            return False
        return abs(got - want) <= TOLERANCE
    return got == want  # strings, lists (exact), None


def compare(columns, rows, expected, strict_types: bool = False) -> list:
    """Return a list of difference messages (empty means PASS)."""
    diffs = []
    want_cols = list(expected[0].keys()) if expected else None
    if want_cols is not None and columns != want_cols:
        diffs.append("columns {} != expected {}".format(columns, want_cols))
        return diffs
    if len(rows) != len(expected):
        diffs.append("row count {} != expected {}".format(len(rows), len(expected)))
    for i, (got, want) in enumerate(zip(rows, expected)):
        bad = [c for c in want if not values_equal(got.get(c), want[c], strict_types)]
        if bad:
            diffs.append("row {}: got {} | expected {} (columns {})".format(i + 1, got, want, bad))
            if len(diffs) >= SHOW_ROWS:
                break
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run queries.txt and compare with the pandas cross-check.")
    ap.add_argument("--queries", type=Path, default=KG_DIR / "queries.txt")
    ap.add_argument("--expected", type=Path, default=KG_DIR / "crosscheck_expected.json")
    ap.add_argument("--config", type=Path, default=KG_DIR / "config.txt")
    ap.add_argument("--count", type=int, default=5, help="number of queries expected in the file")
    ap.add_argument("--strict-types", action="store_true", help="also require int vs float to match the expected JSON")
    args = ap.parse_args(argv)

    queries = parse_queries(args.queries, args.count)
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    config = load_config(args.config)
    session_kwargs = {"database": config["DATABASE"]} if config.get("DATABASE") else {}

    failures = 0
    with GraphDatabase.driver(config["URI"], auth=(config["USERNAME"], config["PASSWORD"])) as driver:
        with driver.session(**session_kwargs) as session:
            for n, query in queries.items():
                try:
                    result = session.run(query)
                    columns = list(result.keys())
                    rows = [dict(r) for r in result]
                except Exception as exc:  # report Cypher errors as a failure
                    failures += 1
                    print("Q{} FAIL  error: {}".format(n, exc))
                    continue
                diffs = compare(columns, rows, expected[n], args.strict_types)
                if diffs:
                    failures += 1
                    print("Q{} FAIL  ({} rows, columns {})".format(n, len(rows), columns))
                    for d in diffs:
                        print("    " + d)
                else:
                    print("Q{} PASS  ({} rows, columns {})".format(n, len(rows), columns))
    print("RESULT: {}".format("ALL {} PASS".format(len(queries)) if failures == 0 else "{} FAILED".format(failures)))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
