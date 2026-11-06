"""Build the CSEN903 Milestone 2 Formula 1 knowledge graph in Neo4j.

Schema mapping
--------------
* Entity tables become entity nodes: drivers -> Driver, constructors -> Constructor,
  circuits -> Circuit, seasons -> Season, status -> Status, races -> Race.
* Fact tables become fact nodes: results -> Result, qualifying -> Qualifying,
  pit_stops -> PitStop. A fact links several entities (a Result links a race, a driver,
  a constructor and a status) and carries its own properties. A relationship can only join
  two nodes, so each fact row is stored as a node of its own.
* Every foreign key becomes a relationship instead of a property:
      (Race)-[:AT_CIRCUIT]->(Circuit)          (Race)-[:IN_SEASON]->(Season)
      (Result|Qualifying|PitStop)-[:FOR_RACE]->(Race)
      (Result|Qualifying|PitStop)-[:BY_DRIVER]->(Driver)
      (Result|Qualifying)-[:FOR_CONSTRUCTOR]->(Constructor)
      (Result)-[:HAS_STATUS]->(Status)
* PitStop has no natural id, so eventId = "raceId:driverId:stop".
* CSV columns outside the schema (url, the race fp*/quali*/sprint* columns) are not loaded.

Types and missing values
------------------------
Each property has one explicit type in SPECS (int, float, str or date). The CSVs are read
with the standard-library csv module, so every cell arrives as a string and is cast once,
on purpose. pandas is avoided because an integer column containing even one missing value
becomes float64, which would store a driver number 44 as 44.0. Missing values (the literal
\\N, or an empty cell) are never stored: the property is omitted from the node.

Idempotency
-----------
Each node label has a uniqueness constraint on its id, which also creates the index used by
MERGE. Nodes are MERGEd on their id and their properties set with SET n += props.
Relationships are created by MATCHing both endpoints and then MERGEing only the
relationship. Re-running the script therefore leaves the graph unchanged. The script never
deletes anything.

Usage
-----
    python Create_kg.py                 # CSVs and config.txt next to this script
    python Create_kg.py --data-dir data/raw --config kg/config.txt
"""

from __future__ import annotations

import argparse
import csv
import datetime
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

from neo4j import GraphDatabase

BATCH_SIZE = 2000
SCRIPT_DIR = Path(__file__).resolve().parent
REQUIRED_CONFIG_KEYS = ("URI", "USERNAME", "PASSWORD")
NULL_TOKENS = ("", "\\N")


class _Missing:
    """Marker for a missing CSV value; such properties are omitted from the node."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


# --------------------------------------------------------------------------- schema spec


class Prop(NamedTuple):
    name: str  # property name in the graph
    column: str  # column in the CSV
    kind: str  # "int" | "float" | "str" | "date"


class Rel(NamedTuple):
    type: str  # relationship type, always (this node)-[:type]->(target)
    column: str  # foreign-key column in the CSV
    target_label: str
    target_key: str


class NodeSpec(NamedTuple):
    label: str
    file: str
    key: str  # unique id property
    props: Tuple[Prop, ...]
    rels: Tuple[Rel, ...] = ()
    key_fn: Optional[Callable[[Dict[str, str]], object]] = None  # computed id (PitStop)


def _pitstop_event_id(row: Dict[str, str]) -> str:
    return "{}:{}:{}".format(
        cast(row["raceId"], "int"), cast(row["driverId"], "int"), cast(row["stop"], "int")
    )


def _p(*items: Tuple[str, str, str]) -> Tuple[Prop, ...]:
    return tuple(Prop(*item) for item in items)


FOR_RACE = Rel("FOR_RACE", "raceId", "Race", "raceId")
BY_DRIVER = Rel("BY_DRIVER", "driverId", "Driver", "driverId")
FOR_CONSTRUCTOR = Rel("FOR_CONSTRUCTOR", "constructorId", "Constructor", "constructorId")

# Load order: parents before the nodes that link to them.
SPECS: Tuple[NodeSpec, ...] = (
    NodeSpec("Season", "seasons.csv", "year", _p(("year", "year", "int"))),
    NodeSpec(
        "Status",
        "status.csv",
        "statusId",
        _p(("statusId", "statusId", "int"), ("status", "status", "str")),
    ),
    NodeSpec(
        "Circuit",
        "circuits.csv",
        "circuitId",
        _p(
            ("circuitId", "circuitId", "int"),
            ("circuitRef", "circuitRef", "str"),
            ("circuit_name", "name", "str"),
            ("circuit_loc", "location", "str"),
            ("circuit_country", "country", "str"),
            ("lat", "lat", "float"),
            ("lng", "lng", "float"),
            ("alt", "alt", "int"),
        ),
    ),
    NodeSpec(
        "Driver",
        "drivers.csv",
        "driverId",
        _p(
            ("driverId", "driverId", "int"),
            ("driverRef", "driverRef", "str"),
            ("number", "number", "int"),
            ("code", "code", "str"),
            ("forename", "forename", "str"),
            ("surname", "surname", "str"),
            ("dob", "dob", "date"),
            ("nationality", "nationality", "str"),
        ),
    ),
    NodeSpec(
        "Constructor",
        "constructors.csv",
        "constructorId",
        _p(
            ("constructorId", "constructorId", "int"),
            ("constructorRef", "constructorRef", "str"),
            ("constructor_name", "name", "str"),
            ("constructor_nationality", "nationality", "str"),
        ),
    ),
    NodeSpec(
        "Race",
        "races.csv",
        "raceId",
        _p(
            ("raceId", "raceId", "int"),
            ("year", "year", "int"),
            ("round", "round", "int"),
            ("name", "name", "str"),
            ("date", "date", "date"),
            ("time", "time", "str"),
        ),
        rels=(
            Rel("AT_CIRCUIT", "circuitId", "Circuit", "circuitId"),
            Rel("IN_SEASON", "year", "Season", "year"),
        ),
    ),
    NodeSpec(
        "Result",
        "results.csv",
        "resultId",
        _p(
            ("resultId", "resultId", "int"),
            ("number", "number", "int"),
            ("grid", "grid", "int"),
            ("position", "position", "int"),
            ("positionText", "positionText", "str"),
            ("positionOrder", "positionOrder", "int"),
            ("points", "points", "float"),
            ("laps", "laps", "int"),
            ("time", "time", "str"),
            ("milliseconds", "milliseconds", "int"),
            ("fastestLap", "fastestLap", "int"),
            ("rank", "rank", "int"),
            ("fastestLapTime", "fastestLapTime", "str"),
            ("fastestLapSpeed", "fastestLapSpeed", "float"),
        ),
        rels=(
            FOR_RACE,
            BY_DRIVER,
            FOR_CONSTRUCTOR,
            Rel("HAS_STATUS", "statusId", "Status", "statusId"),
        ),
    ),
    NodeSpec(
        "Qualifying",
        "qualifying.csv",
        "qualifyId",
        _p(
            ("qualifyId", "qualifyId", "int"),
            ("number", "number", "int"),
            ("position", "position", "int"),
            ("q1", "q1", "str"),
            ("q2", "q2", "str"),
            ("q3", "q3", "str"),
        ),
        rels=(FOR_RACE, BY_DRIVER, FOR_CONSTRUCTOR),
    ),
    NodeSpec(
        "PitStop",
        "pit_stops.csv",
        "eventId",
        _p(
            ("stop", "stop", "int"),
            ("lap", "lap", "int"),
            ("time", "time", "str"),
            ("duration", "duration", "str"),
            ("milliseconds", "milliseconds", "int"),
        ),
        rels=(FOR_RACE, BY_DRIVER),
        key_fn=_pitstop_event_id,
    ),
)


# --------------------------------------------------------------------------- config


def parse_config(text: str) -> Dict[str, str]:
    """Parse KEY=VALUE lines by key. Splits on the first '=' only, so values may contain '='."""
    config: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip().upper()] = value.strip()
    missing = [k for k in REQUIRED_CONFIG_KEYS if not config.get(k)]
    if missing:
        raise ValueError("config.txt is missing required key(s): " + ", ".join(missing))
    return config


def load_config(path: Path) -> Dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError("config file not found: {}".format(path))
    return parse_config(path.read_text(encoding="utf-8-sig"))


# --------------------------------------------------------------------------- casting


def cast(raw: Optional[str], kind: str) -> object:
    """Cast one CSV cell to its schema type; return MISSING for \\N or an empty cell."""
    if raw is None:
        return MISSING
    value = raw.strip()
    if value in NULL_TOKENS:
        return MISSING
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "date":
        return datetime.date.fromisoformat(value)
    if kind == "str":
        return value
    raise ValueError("unknown kind: {!r}".format(kind))


def row_to_props(row: Dict[str, str], spec: NodeSpec) -> Dict[str, object]:
    """Cast a CSV row to node properties, leaving out missing values."""
    props: Dict[str, object] = {}
    for prop in spec.props:
        try:
            value = cast(row[prop.column], prop.kind)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                "{}: cannot read column {!r} as {} (value {!r})".format(
                    spec.file, prop.column, prop.kind, row.get(prop.column)
                )
            ) from exc
        if value is not MISSING:
            props[prop.name] = value
    return props


def node_key(row: Dict[str, str], spec: NodeSpec) -> object:
    if spec.key_fn is not None:
        return spec.key_fn(row)
    column = next(p for p in spec.props if p.name == spec.key)
    key = cast(row[column.column], column.kind)
    if key is MISSING:
        raise ValueError("{}: row without {}: {!r}".format(spec.file, spec.key, row))
    return key


def to_batch_row(row: Dict[str, str], spec: NodeSpec) -> Dict[str, object]:
    """Shape one CSV row as the $rows parameter element: key, props and one value per FK."""
    item: Dict[str, object] = {"key": node_key(row, spec), "props": row_to_props(row, spec)}
    if spec.key_fn is not None:
        item["props"][spec.key] = item["key"]
    for rel in spec.rels:
        fk = cast(row.get(rel.column), "int")
        item[rel.column] = None if fk is MISSING else fk
    return item


# --------------------------------------------------------------------------- reading


def read_rows(path: Path) -> Iterator[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError("CSV file not found: {}".format(path))
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            yield row


def batched(items: Iterable, size: int) -> Iterator[list]:
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


# --------------------------------------------------------------------------- Cypher


def constraint_query(spec: NodeSpec) -> str:
    return (
        "CREATE CONSTRAINT {name} IF NOT EXISTS "
        "FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
    ).format(name="{}_{}_unique".format(spec.label.lower(), spec.key), label=spec.label, key=spec.key)


def node_query(spec: NodeSpec) -> str:
    return (
        "UNWIND $rows AS row "
        "MERGE (n:{label} {{{key}: row.key}}) "
        "SET n += row.props"
    ).format(label=spec.label, key=spec.key)


def rel_query(spec: NodeSpec, rel: Rel) -> str:
    return (
        "UNWIND $rows AS row "
        "WITH row WHERE row.{fk} IS NOT NULL "
        "MATCH (a:{label} {{{key}: row.key}}) "
        "MATCH (b:{target} {{{tkey}: row.{fk}}}) "
        "MERGE (a)-[:{type}]->(b) "
        "RETURN count(*) AS linked"
    ).format(
        label=spec.label,
        key=spec.key,
        target=rel.target_label,
        tkey=rel.target_key,
        fk=rel.column,
        type=rel.type,
    )


def _run(tx, query: str, rows: list) -> int:
    record = tx.run(query, rows=rows).single()
    return record["linked"] if record is not None and "linked" in record.keys() else 0


def create_constraints(session) -> None:
    for spec in SPECS:
        session.run(constraint_query(spec)).consume()


def load_spec(session, spec: NodeSpec, data_dir: Path, batch_size: int = BATCH_SIZE) -> None:
    rows_seen = 0
    linked = {rel.type: 0 for rel in spec.rels}
    nq = node_query(spec)
    rqs = [(rel, rel_query(spec, rel)) for rel in spec.rels]
    rows = (to_batch_row(row, spec) for row in read_rows(data_dir / spec.file))
    for batch in batched(rows, batch_size):
        session.execute_write(_run, nq, batch)
        for rel, rq in rqs:
            linked[rel.type] += session.execute_write(_run, rq, batch)
        rows_seen += len(batch)
    print("  {:<12} {:>7,} nodes".format(spec.label, rows_seen), end="")
    print("".join("  {} {:,}".format(t, n) for t, n in linked.items()))
    for rel_type, count in linked.items():
        if count != rows_seen:
            print(
                "  WARNING: {} {} relationships for {} rows; {} foreign keys found no parent".format(
                    count, rel_type, rows_seen, rows_seen - count
                )
            )


def report_counts(session) -> None:
    labels = [spec.label for spec in SPECS]
    rel_types: List[str] = []
    for spec in SPECS:
        for rel in spec.rels:
            if rel.type not in rel_types:
                rel_types.append(rel.type)
    print("Node counts:")
    node_total = 0
    for label in labels:
        n = session.run("MATCH (n:{}) RETURN count(n) AS c".format(label)).single()["c"]
        node_total += n
        print("  {:<16} {:>8,}".format(label, n))
    print("  {:<16} {:>8,}".format("TOTAL", node_total))
    print("Relationship counts:")
    rel_total = 0
    for rel_type in rel_types:
        n = session.run("MATCH ()-[r:{}]->() RETURN count(r) AS c".format(rel_type)).single()["c"]
        rel_total += n
        print("  {:<16} {:>8,}".format(rel_type, n))
    print("  {:<16} {:>8,}".format("TOTAL", rel_total))


# --------------------------------------------------------------------------- main


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the F1 knowledge graph in Neo4j.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="folder with the 9 CSV files (default: this script's folder)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=SCRIPT_DIR / "config.txt",
        help="config file with URI, USERNAME, PASSWORD (default: config.txt next to this script)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    session_kwargs = {"database": config["DATABASE"]} if config.get("DATABASE") else {}
    with GraphDatabase.driver(config["URI"], auth=(config["USERNAME"], config["PASSWORD"])) as driver:
        driver.verify_connectivity()
        with driver.session(**session_kwargs) as session:
            print("Creating constraints...")
            create_constraints(session)
            print("Loading data from {}".format(args.data_dir.resolve()))
            for spec in SPECS:
                load_spec(session, spec, args.data_dir)
            report_counts(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
