# Milestone 2: F1 Knowledge Graph

`Create_kg.py` (to be added) reads nine Kaggle/Ergast CSVs (drivers, constructors, circuits, seasons, status,
races, results, qualifying, pit_stops) from its own directory and loads them into Neo4j as a property graph
with the schema fixed by the CSEN903 Milestone 2 PDF. It is idempotent: running it twice must not create
duplicates. The full plan and design decisions are in [`../docs/milestone2_plan.md`](../docs/milestone2_plan.md).

## How to run

1. Start a Neo4j server (see below) and copy `config.example.txt` to `config.txt`, filling in the real password.
   `config.txt` is gitignored.
2. Put the nine CSVs next to `Create_kg.py` (or pass `--data-dir`). `kg/*.csv` is gitignored.
3. `pip install -r requirements.txt`, then `python Create_kg.py`.

## Neo4j version

Pinned Neo4j image tag: `TODO` (set in step P1b).

The grader's Neo4j version is unknown, so the Cypher used must also run on Neo4j 5.x.
