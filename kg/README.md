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

## Tests

Casting, config parsing and schema checks (no database needed):

```bash
pip install -r kg/requirements-dev.txt
python -m pytest kg/tests -q
```

## Local Neo4j

Pinned image tag: **`neo4j:2026.10.1-community`** (Docker, container `f1kg`, named volume `f1kg-data`).

- Browser UI: http://localhost:7474 (log in as `neo4j` with the password from `kg/config.txt`)
- Bolt (used by the script): `neo4j://localhost:7687`

First-time setup (the password must match `kg/config.txt`):

```bash
docker run -d --name f1kg -p 7474:7474 -p 7687:7687   -e NEO4J_AUTH=neo4j/<password>   -v f1kg-data:/data   neo4j:2026.10.1-community
```

Day to day:

```bash
docker start f1kg      # start
docker stop f1kg       # stop (data kept in the f1kg-data volume)
docker rm -f f1kg && docker volume rm f1kg-data   # reset: delete container and all graph data
```

The first start can take several minutes on this PC; wait for `Started.` in `docker logs f1kg`.
