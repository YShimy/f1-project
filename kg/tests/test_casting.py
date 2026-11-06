"""Unit tests for Create_kg.py that need no database."""

import datetime
import sys
from pathlib import Path

import pytest

KG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KG_DIR))

import Create_kg as kg  # noqa: E402

RAW_DIR = KG_DIR.parent / "data" / "raw"
SPEC = {s.label: s for s in kg.SPECS}

# The schema exactly as listed in the Milestone 2 PDF.
PDF_PROPS = {
    "Driver": {"driverId", "driverRef", "number", "code", "forename", "surname", "dob", "nationality"},
    "Constructor": {"constructorId", "constructorRef", "constructor_name", "constructor_nationality"},
    "Circuit": {"circuitId", "circuitRef", "circuit_name", "circuit_loc", "circuit_country", "lat", "lng", "alt"},
    "Season": {"year"},
    "Status": {"statusId", "status"},
    "Race": {"raceId", "year", "round", "name", "date", "time"},
    "Result": {
        "resultId", "number", "grid", "position", "positionText", "positionOrder", "points", "laps",
        "time", "milliseconds", "fastestLap", "rank", "fastestLapTime", "fastestLapSpeed",
    },
    "Qualifying": {"qualifyId", "number", "position", "q1", "q2", "q3"},
    "PitStop": {"eventId", "stop", "lap", "time", "duration", "milliseconds"},
}
PDF_RELS = {
    ("Race", "AT_CIRCUIT", "Circuit"), ("Race", "IN_SEASON", "Season"),
    ("Result", "FOR_RACE", "Race"), ("Result", "BY_DRIVER", "Driver"),
    ("Result", "FOR_CONSTRUCTOR", "Constructor"), ("Result", "HAS_STATUS", "Status"),
    ("Qualifying", "FOR_RACE", "Race"), ("Qualifying", "BY_DRIVER", "Driver"),
    ("Qualifying", "FOR_CONSTRUCTOR", "Constructor"),
    ("PitStop", "FOR_RACE", "Race"), ("PitStop", "BY_DRIVER", "Driver"),
}
PDF_TYPES = {  # PDF "Property types" paragraph
    "int": {"year", "round", "number", "grid", "position", "positionOrder", "laps", "milliseconds",
            "fastestLap", "rank", "stop", "lap", "alt", "driverId", "constructorId", "circuitId",
            "statusId", "raceId", "resultId", "qualifyId"},
    "float": {"points", "lat", "lng", "fastestLapSpeed"},
    "date": {"dob", "date"},
}
ROW_COUNTS = {
    "drivers.csv": 861, "constructors.csv": 212, "circuits.csv": 77, "seasons.csv": 75,
    "status.csv": 139, "races.csv": 1125, "results.csv": 26759, "qualifying.csv": 10494,
    "pit_stops.csv": 11371,
}


# ---------------------------------------------------------------- sentinels and casting

@pytest.mark.parametrize("raw", ["\\N", "", "   ", None])
@pytest.mark.parametrize("kind", ["int", "float", "str", "date"])
def test_missing_values_are_omitted(raw, kind):
    assert kg.cast(raw, kind) is kg.MISSING


def test_int_stays_int():
    value = kg.cast("44", "int")
    assert value == 44 and type(value) is int


def test_float_columns_are_float():
    points = kg.cast("10", "float")
    assert points == 10.0 and type(points) is float
    assert kg.cast("218.300", "float") == pytest.approx(218.3)
    assert kg.cast("-37.8497", "float") == pytest.approx(-37.8497)


def test_bad_int_raises():
    with pytest.raises(ValueError):
        kg.cast("1.5", "int")


def test_strings_are_kept_as_strings():
    assert kg.cast("1:27.452", "str") == "1:27.452"
    assert kg.cast("26.898", "str") == "26.898"


def test_dates_parse_to_date():
    assert kg.cast("1985-01-07", "date") == datetime.date(1985, 1, 7)


def test_bad_date_raises():
    with pytest.raises(ValueError):
        kg.cast("07/01/1985", "date")


def test_row_to_props_omits_missing_and_renames():
    row = {"qualifyId": "9", "raceId": "18", "driverId": "1", "constructorId": "1",
           "number": "22", "position": "1", "q1": "1:26.572", "q2": "\\N", "q3": ""}
    props = kg.row_to_props(row, SPEC["Qualifying"])
    assert props == {"qualifyId": 9, "number": 22, "position": 1, "q1": "1:26.572"}

    ctor = {"constructorId": "1", "constructorRef": "mclaren", "name": "McLaren",
            "nationality": "British", "url": "http://x"}
    assert kg.row_to_props(ctor, SPEC["Constructor"]) == {
        "constructorId": 1, "constructorRef": "mclaren",
        "constructor_name": "McLaren", "constructor_nationality": "British",
    }


def test_row_to_props_names_file_and_column_on_error():
    row = {"year": "nineteen"}
    with pytest.raises(ValueError, match="seasons.csv.*year"):
        kg.row_to_props(row, SPEC["Season"])


# ---------------------------------------------------------------- PitStop eventId

def test_pitstop_event_id_and_types():
    row = {"raceId": "841", "driverId": "153", "stop": "1", "lap": "1",
           "time": "17:05:23", "duration": "26.898", "milliseconds": "26898"}
    item = kg.to_batch_row(row, SPEC["PitStop"])
    assert item["key"] == "841:153:1"
    assert item["props"] == {"eventId": "841:153:1", "stop": 1, "lap": 1, "time": "17:05:23",
                             "duration": "26.898", "milliseconds": 26898}
    assert item["raceId"] == 841 and item["driverId"] == 153


def test_foreign_keys_are_not_properties():
    row = {"resultId": "1", "raceId": "18", "driverId": "1", "constructorId": "1", "number": "22",
           "grid": "1", "position": "1", "positionText": "1", "positionOrder": "1", "points": "10",
           "laps": "58", "time": "1:34:50.616", "milliseconds": "5690616", "fastestLap": "39",
           "rank": "2", "fastestLapTime": "1:27.452", "fastestLapSpeed": "218.300", "statusId": "1"}
    item = kg.to_batch_row(row, SPEC["Result"])
    assert not {"raceId", "driverId", "constructorId", "statusId"} & set(item["props"])
    assert (item["raceId"], item["driverId"], item["constructorId"], item["statusId"]) == (18, 1, 1, 1)


# ---------------------------------------------------------------- config

def test_config_exact_format():
    cfg = kg.parse_config("URI=neo4j://localhost:7687\nUSERNAME=neo4j\nPASSWORD=secret\n")
    assert cfg == {"URI": "neo4j://localhost:7687", "USERNAME": "neo4j", "PASSWORD": "secret"}


def test_config_extra_database_line_is_read_by_key():
    cfg = kg.parse_config("URI=neo4j://h:7687\nDATABASE=f1\nUSERNAME=neo4j\nPASSWORD=pw\n")
    assert cfg["DATABASE"] == "f1" and cfg["PASSWORD"] == "pw" and cfg["USERNAME"] == "neo4j"


def test_config_password_may_contain_equals():
    cfg = kg.parse_config("URI=neo4j://h:7687\nUSERNAME=neo4j\nPASSWORD=a=b==c\n")
    assert cfg["PASSWORD"] == "a=b==c"


def test_config_crlf_and_spaces():
    cfg = kg.parse_config("URI = neo4j://h:7687 \r\n\r\nUSERNAME=neo4j\r\nPASSWORD= pw \r\n")
    assert cfg["URI"] == "neo4j://h:7687" and cfg["PASSWORD"] == "pw"


def test_config_missing_password_raises():
    with pytest.raises(ValueError, match="PASSWORD"):
        kg.parse_config("URI=neo4j://h:7687\nUSERNAME=neo4j\n")


def test_load_config_tolerates_bom(tmp_path):
    path = tmp_path / "config.txt"
    path.write_bytes("URI=neo4j://h:7687\nUSERNAME=neo4j\nPASSWORD=pw\n".encode("utf-8-sig"))
    assert kg.load_config(path)["URI"] == "neo4j://h:7687"


# ---------------------------------------------------------------- schema guard

def test_specs_match_pdf_properties():
    assert set(SPEC) == set(PDF_PROPS)
    for label, expected in PDF_PROPS.items():
        spec = SPEC[label]
        names = {p.name for p in spec.props}
        if spec.key_fn is not None:
            names.add(spec.key)
        assert names == expected, label


def test_specs_match_pdf_relationships():
    rels = {(s.label, r.type, r.target_label) for s in kg.SPECS for r in s.rels}
    assert rels == PDF_RELS


def test_property_types_match_pdf():
    for spec in kg.SPECS:
        for prop in spec.props:
            expected = next((k for k, names in PDF_TYPES.items() if prop.name in names), "str")
            assert prop.kind == expected, (spec.label, prop.name)


def test_parents_load_before_children():
    order = [s.label for s in kg.SPECS]
    for spec in kg.SPECS:
        for rel in spec.rels:
            assert order.index(rel.target_label) < order.index(spec.label)


def test_queries_use_parameters_and_merge():
    for spec in kg.SPECS:
        assert "MERGE (n:{} ".format(spec.label) in kg.node_query(spec)
        assert "IF NOT EXISTS" in kg.constraint_query(spec)
        for rel in spec.rels:
            q = kg.rel_query(spec, rel)
            assert q.index("MATCH (b:") < q.index("MERGE (a)-[:{}]->(b)".format(rel.type))


# ---------------------------------------------------------------- real data smoke test

@pytest.mark.skipif(not RAW_DIR.is_dir(), reason="data/raw not present")
def test_all_csv_rows_cast_cleanly():
    for spec in kg.SPECS:
        keys = set()
        count = 0
        for row in kg.read_rows(RAW_DIR / spec.file):
            item = kg.to_batch_row(row, spec)
            keys.add(item["key"])
            for value in item["props"].values():
                assert value not in ("", "\\N"), (spec.file, item)
            for rel in spec.rels:
                assert isinstance(item[rel.column], int), (spec.file, rel.column, item)
            count += 1
        assert count == ROW_COUNTS[spec.file], spec.file
        assert len(keys) == count, "duplicate ids in " + spec.file
