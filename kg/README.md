# Milestone 2: Formula 1 knowledge graph

`Create_kg.py` reads the 9 Kaggle/Ergast F1 CSVs (drivers, constructors, circuits, seasons,
status, races, results, qualifying, pit_stops) and loads them into Neo4j as a property graph
following the Milestone 2 schema: entity nodes, fact nodes (Result, Qualifying, PitStop) and one
relationship per foreign key. `queries.txt` holds the 5 required Cypher queries. The full plan
and design decisions are in [`docs/milestone2_plan.md`](../docs/milestone2_plan.md).

## How to run

1. Start Neo4j (see below).
2. Copy `config.example.txt` to `config.txt` and fill in the password (`config.txt` is gitignored).
3. Install the driver: `pip install -r kg/requirements.txt` (the repo uses `.venv`, Python 3.13).
4. Build the graph: `python kg/Create_kg.py --data-dir data/raw`
   (the graded run puts the CSVs next to the script and needs no arguments).

## Local Neo4j

Pinned image tag: _TBD (recorded when the container is set up)_
