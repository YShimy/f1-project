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

## Local Neo4j (Docker)

Pinned image: `neo4j:2026.10.1-community` (checked on Docker Hub 2026-11-06; no `latest`, no enterprise).

```bash
docker run -d --name f1kg -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/<password> \
  -v f1kg-data:/data \
  neo4j:2026.10.1-community
```

- Browser UI: http://localhost:7474. Bolt (used by the script): port 7687.
- Start / stop: `docker start f1kg` / `docker stop f1kg`.
- Reset (deletes all data): `docker rm -f f1kg && docker volume rm f1kg-data`.
- The password lives only in `config.txt` (gitignored) and in the container's `NEO4J_AUTH`.

The grader's Neo4j version is unknown, so the Cypher used must also run on Neo4j 5.x
(`5.26-community` is the matching 5.x tag to test against in the P5 dry run).
