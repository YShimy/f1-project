# F1 Knowledge Graph (CSEN903 Milestone 2): plan and guide

Created Fri 6 Nov 2026. **Deadline: Tue 17 Nov 2026, 23:59.** Target: submit **Sat 14 Nov**, with Sun 15 to Tue 17 as buffer.
The Milestone 2 PDF is authoritative. Where this plan and the PDF disagree, the PDF wins.

---

## 0. Open items to settle first

| # | Item | Why it matters | Action |
|---|---|---|---|
| O1 | The PDF lists **two different form links** (`forms.gle/KcqJKdVqubE92xRT7` under Deliverables, `forms.gle/pkBj32QgbiVpSz8x8` as "Submission link") | Submitting to the wrong form means no submission | Ask the TA which one is correct this week; do not guess on the day |
| O2 | Team or solo for M2? | | **Settled:** team project, Youssef builds M2 alone |
| O3 | Neo4j runtime on your PC | | **Settled:** Docker (Docker Desktop installed). Doesn't affect the deliverables |

**Working mode (settled 6 Nov):** build and submit first, study after. No quizzes during the build. Claude only stops for decisions that need Youssef's call, and reviews Claude Code's plans in chat. Phase 0 (S1–S4) and the viva list move to Sun 15 to Tue 17.
| O4 | Is there an evaluation/viva for M2? | Whether Phase 8 is needed beyond self-study | Ask the TA together with O1 |

---

## 1. What the milestone actually asks for

**Requirement:** a single Python script, `Create_kg.py`, that reads 9 CSVs from its own directory and builds a Neo4j graph matching an exact schema, plus `config.txt` (credentials read by key) and `queries.txt` (5 Cypher queries in a fixed format). An autograder runs the script, checks the graph, then runs your 5 queries and a **private set of other queries**.

That last point drives the whole design: the graph must be *correct in general* (right labels, directions, types, missing-value handling), not just tuned to the 5 example questions.

### Deliverables
1. `Create_kg.py` (capital C, exact name)
2. `config.txt` in exactly this format:
   ```
   URI=neo4j://localhost:7687
   USERNAME=neo4j
   PASSWORD=your_password
   ```
3. `queries.txt`, UTF-8, each query headed `//1. Query 1`, `//2. Query 2`, … in order, sorted as specified, columns named exactly as specified.

### Target sizes (verify against your own build)

| Node label | Rows / nodes | | Relationship | Count |
|---|---|---|---|---|
| Driver | 861 | | AT_CIRCUIT | 1,125 |
| Constructor | 212 | | IN_SEASON | 1,125 |
| Circuit | 77 | | FOR_RACE (Result + Qualifying + PitStop) | 48,624 |
| Season | 75 | | BY_DRIVER (Result + Qualifying + PitStop) | 48,624 |
| Status | 139 | | FOR_CONSTRUCTOR (Result + Qualifying) | 37,253 |
| Race | 1,125 | | HAS_STATUS | 26,759 |
| Result | 26,759 | | | |
| Qualifying | 10,494 | | | |
| PitStop | 11,371 | | | |
| **Total** | **51,113** | | **Total** | **163,510** |

Both totals reconcile exactly with "one node per CSV row" and "one relationship per foreign key per fact row". So **every foreign key must find its parent**. If any count comes out short, a join failed silently: investigate, never patch the number.

---

## 2. Phase 0: Understand before building (chat sessions with me)

Work through these in this chat before writing code. Each one ends with you explaining it back in your own words.

**S1. The property-graph model vs the relational model**
- Nodes, labels, relationships, relationship types, direction, properties.
- How each CSV maps: entity tables → entity nodes; a foreign key → a relationship; a "fact" row → a fact node.
- **Why `Result` is a node and not a relationship.** A result connects four things (race, driver, constructor, status) and carries 14 properties. A relationship joins exactly two nodes, so a 4-way fact must be *reified* (turned into a node). This is the PDF's "entities vs facts" idea.
- Why the same driver can have two `Result` nodes in one race (1950s shared drives, your M1 D1 decision) and why the KG keeps **both** (the KG stores facts as they are; the cleaning rule belongs to the ML table, not the graph).

**S2. Cypher fundamentals for the 5 questions**
- `MATCH` patterns and direction, `WHERE`, `WITH` as a pipeline stage, implicit grouping in aggregation (`count`, `sum`, `avg`, `collect`), `DISTINCT`, `ORDER BY`, `CASE`, `toFloat`.
- **Null semantics.** A missing property returns `null`; `null = 1` is `null` (not false), so the row drops out of `WHERE`. This is why omitting `\N` is safe for "position = 1" but matters for averages and counts.

**S3. Loading data correctly**
- `CREATE` vs `MERGE`, and why **re-running must not duplicate** (idempotency).
- Uniqueness constraints: they guarantee uniqueness *and* create the index that makes `MERGE` fast.
- `UNWIND $rows` batching and query parameters (no string-built Cypher: avoids injection and lets Neo4j cache the plan).
- The classic trap: `MERGE (a)-[:R]->(b:Label {id: x})` merges the *whole pattern* and can create a duplicate `b`. Correct form: `MATCH` both endpoints, then `MERGE` only the relationship.

**S4. Types**
- Neo4j types: Integer, Float, String, Date. Why `dob` and `date` must be real dates (so `r.date < date('2020-01-01')` works; a string comparison would not).
- **Why pandas is dangerous here:** an integer column containing any `\N` becomes float64, so `number = 44` would be stored as `44.0`. This is the strongest reason for the design choice in D3 below.

---

## 3. Phase 1: Environment (Fri 6 to Sat 7 Nov)

**Recommendation: Neo4j in Docker** if Docker Desktop is installed. Reasons: a fresh container is a perfect "grader's empty database" in seconds, it's version-pinned, and it's real DevOps practice (container, port publishing, named volumes, env-var config).

```bash
docker run -d --name f1kg -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/<your-password> \
  -v f1kg-data:/data \
  neo4j:<pinned 2026.x tag>
```
- Use a **pinned tag**, not `latest` (record it in `kg/README.md`).
- Use a **named volume** (`f1kg-data`), not a Windows bind mount (avoids permission problems).
- Browser UI: http://localhost:7474. Bolt (what the script uses): port 7687.
- Before learning each flag, ask me what it does. You should be able to explain `-p`, `-e`, `-v`, `-d` without notes.

**Fallback:** Neo4j Desktop (GUI) if Docker isn't available. Same URI and credentials.

**Compatibility rule:** the grader's Neo4j version is unknown. Keep `Create_kg.py` and `queries.txt` to Cypher that also runs on Neo4j 5.x (no features introduced only in the newest releases).

---

## 4. Phase 2: Design decisions (Sun 8 Nov, in chat, before code)

| ID | Decision | Label | Reasoning / alternative |
|---|---|---|---|
| KG1 | Code lives in the team repo `YShimy/f1-project` (renamed from `f1-project-ms1`; M1 graded state tagged `ms1-submission`) under `kg/`, on `main` | Decision (Youssef) | One repo across milestones. M2 doesn't use M1 code. `Create_kg.py` must be **self-contained** (graders run it alone) |
| KG2 | Only dependency is the `neo4j` driver; CSVs read with the standard-library `csv` module | Recommendation | pandas would silently turn int columns with `\N` into floats (S4). The stdlib reads everything as strings, then we cast explicitly per a type map. Alternative: pandas with `dtype=str, keep_default_na=False`, which is workable but adds a dependency for no gain |
| KG3 | Explicit **type map** per column (table in §4.1); `\N` and empty string → property omitted | Requirement (types, omission) + Recommendation (map) | The PDF fixes the types; a map makes them auditable and testable |
| KG4 | Exact schema only: drop `url`, Race `fp*/quali*/sprint*` columns; foreign-key ids (`raceId`, `driverId`, … on facts) become relationships, **not** properties | Recommendation | Adding properties isn't explicitly forbidden, but the schema doesn't list them, and storing them invites queries that bypass the graph. Defend as "the relationship *is* the foreign key" |
| KG5 | Renames: Constructor `name→constructor_name`, `nationality→constructor_nationality`; Circuit `name→circuit_name`, `location→circuit_loc`, `country→circuit_country` | Requirement | Schema property names |
| KG6 | `PitStop.eventId = f"{raceId}:{driverId}:{stop}"` (string) | Requirement | Pit-stop rows have no natural single id |
| KG7 | Idempotency: uniqueness constraint per entity/fact id (`IF NOT EXISTS`), `MERGE` nodes on id, `SET n += props`, `MATCH` endpoints then `MERGE` relationships | Requirement (no duplicates) + Recommendation (method) | Second run must leave 51,113 / 163,510 unchanged |
| KG8 | Load order: constraints → Season, Status, Circuit, Driver, Constructor → Race (+ AT_CIRCUIT, IN_SEASON) → Result → Qualifying → PitStop | Requirement (parents first) | |
| KG9 | Batches of ~2,000 rows per `UNWIND` transaction | Recommendation | One huge transaction risks memory; row-by-row is very slow |
| KG10 | Config parsed **by key** (`split('=', 1)`, so passwords containing `=` survive); if a `DATABASE` key is present it's passed to the driver, otherwise the server default is used; never hardcode `neo4j` | Requirement + Recommendation | Grading `config.txt` has an extra `DATABASE` line |
| KG11 | Paths resolved relative to the **script's folder** (`Path(__file__).parent`), not the current working directory; optional `--data-dir` for local dev | Recommendation | "CSV files located in the same directory"; grader may launch from elsewhere |
| KG12 | The script **does not wipe** the database | Recommendation | Idempotency comes from `MERGE`, which is what the requirement tests. A wipe would hide duplicate bugs and destroy unrelated data |
| KG13 | Real `config.txt` is gitignored; the submitted `config.txt` has placeholder values | Recommendation | Never commit or submit a real password |

### 4.1 Type map

| Label | Property ← CSV column | Type |
|---|---|---|
| Driver | driverId | int |
| | driverRef, code, forename, surname, nationality | str |
| | number | int |
| | dob | date |
| Constructor | constructorId | int |
| | constructorRef, constructor_name←name, constructor_nationality←nationality | str |
| Circuit | circuitId, alt | int |
| | circuitRef, circuit_name←name, circuit_loc←location, circuit_country←country | str |
| | lat, lng | float |
| Season | year | int |
| Status | statusId | int |
| | status | str |
| Race | raceId, year, round | int |
| | name, time | str |
| | date | date |
| Result | resultId, number, grid, position, positionOrder, laps, milliseconds, fastestLap, rank | int |
| | positionText, time, fastestLapTime | str |
| | points, fastestLapSpeed | float |
| Qualifying | qualifyId, number, position | int |
| | q1, q2, q3 | str |
| PitStop | eventId, time, duration | str |
| | stop, lap, milliseconds | int |

Relationship sources: Race.circuitId → AT_CIRCUIT; Race.year → IN_SEASON; fact `raceId` → FOR_RACE; `driverId` → BY_DRIVER; `constructorId` → FOR_CONSTRUCTOR; `statusId` → HAS_STATUS.

---

## 5. Phase 3: Build `Create_kg.py` (Sun 8 to Mon 9 Nov)

Run the Claude Code prompts in §10 (P1, P2, P3). After P2, before accepting the plan, check it against §4 yourself. After it lands, I'll walk through the script with you function by function until you can explain each Cypher statement.

---

## 6. Phase 4: Verify the graph (Tue 10 Nov)

Never trust it because it ran. `kg/verify_kg.py` (not submitted) checks:

1. **Counts** per label and per relationship type (incl. FOR_RACE split by source label) against §1.
2. **Idempotency:** run `Create_kg.py` twice; counts unchanged.
3. **Types:** sample every property of every label and assert the Python type returned by the driver (`int`, `float`, `str`, `neo4j.time.Date`). No float where int is expected.
4. **No sentinels:** no property anywhere equals `'\N'` or `''`; e.g. `MATCH (q:Qualifying) WHERE q.q3 = '' RETURN count(q)` must be 0.
5. **Spot checks against the CSV:** 5 random rows per table, every property compared.
6. **Orphans:** every fact node has exactly one of each relationship it should have (e.g. no Result without HAS_STATUS, none with two FOR_RACE).
7. **Direction:** `MATCH (:Race)-[:FOR_RACE]->() RETURN count(*)` must be 0.

---

## 7. Phase 5: The 5 queries (Wed 11 to Thu 12 Nov)

**Process (important for learning):** for each question, *you* write the query first in Neo4j Browser. Then paste it here; I review it. Then Claude Code's independent pandas cross-check (P4) must produce identical numbers. Two independent implementations agreeing is the evidence.

Before running each one, write down a prediction (e.g. "who tops Q1?", "how many drivers change team in Q5?"). Wrong predictions are where learning happens.

| Q | What it tests | Traps to watch |
|---|---|---|
| 1 | 2021 points and wins | Points are **GP only** (no sprints), so the totals will not match the official 2021 standings. Explain why. Win = `position = 1`; unclassified rows have no `position` (null drops out) |
| 2 | Reliability 2014–2021, ≥100 entries | Classified = status `'Finished'` or `STARTS WITH '+'`. Integer division: use `toFloat`. Constructors counted by node (renames separate) |
| 3 | Hamilton vs Bottas, same team, same race | Both Result nodes must share the **same Race and the same Constructor**. Ahead = lower `positionOrder` |
| 4 | Monaco before 2020, ≥5 starts | Starts = **distinct races** after excluding the three statuses (check exact spelling in `status.csv`); averages and wins over **all remaining Result nodes** (shared drives give more than one). `date` comparison needs a real Date |
| 5 | Primary-constructor change 2020→2021 | Most entries per driver-season, tie → lower `constructorId`; only drivers with entries in both seasons; return **one row** even if the list were empty |

Format rules for `queries.txt`: header line exactly `//N. Query N`; no other comments; columns aliased with `AS` exactly as specified; ORDER BY as specified; no trailing semicolons; UTF-8 **without BOM** (a BOM can break an autograder's first-line match).

---

## 8. Phase 6: Robustness for the private queries (Fri 13 Nov)

The grader will ask questions you haven't seen. Write 5 of your own, in the same style, that stress different parts of the graph, e.g.:
- pit stops: average number of stops per race in 2023 (uses PitStop + Race + Season);
- qualifying vs result: how often pole (Qualifying.position = 1) became a win, by season;
- a circuit-country question (Circuit properties + traversal);
- a status question outside the 2014–21 window;
- a driver-age question using `dob` and `date` (proves dates are real dates).

If any of these is awkward or wrong because of how the graph was built, fix the builder, not the query.

Then the **clean-room dry run (P5):** new empty Neo4j container, a temp folder containing only the 9 CSVs, `Create_kg.py` and a `config.txt` that includes an extra `DATABASE=` line; run from a *different* working directory; verify counts; parse `queries.txt` with a regex that mimics the autograder and run each query.

---

## 9. Phase 7: Submit (Sat 14 Nov) and Phase 8: Defend

**Submit:** correct form link (O1) · `Create_kg.py` · `config.txt` (placeholders) · `queries.txt`. Keep Sun 15 to Tue 17 as buffer. If anything changes after submission, rerun P5 before resubmitting.

**Defend (viva study, even if there's no formal viva; M3 builds on this):**
1. Why is Result a node and not a relationship?
2. Why must re-running not create duplicates, and how does your script guarantee it? What would `CREATE` do?
3. What does a uniqueness constraint give you beyond uniqueness?
4. Why omit `\N` rather than store `null` or `0`? What would `0` do to Q4's average?
5. Why did you avoid pandas? What exactly goes wrong with integers?
6. Why can the same driver have two Result nodes in one race, and how does Q4 handle it?
7. Why do Q1 totals differ from the official 2021 standings?
8. Why does Q5 count Renault → Alpine as a change, and when would that be the wrong choice? (Connect to your M1 constructor-lineage decision.)
9. Why are the fact nodes' foreign keys relationships rather than properties?
10. Walk through one query and say what rows exist after each `MATCH` / `WITH`.

**M3 foundation:** don't build anything for M3 now. Keep the builder clean and the verification script, which will catch regressions if M3 extends the graph.

---

## 10. Claude Code prompts (paste one at a time)

Repo: `C:\Users\yshim\dev\f1-project` (GitHub `YShimy/f1-project`). Raw CSVs in `data/raw/` (gitignored); for local runs pass `--data-dir data/raw`. Run Claude Code **locally**, not in a cloud session (Neo4j must run in Docker Desktop on the PC).

### P1 · Scaffold and environment check `[Sonnet · Plan mode no]`
```
Milestone 2 setup. Do not modify src/ or notebooks/.
1. Save the plan I attach as docs/milestone2_plan.md.
2. Find where the raw Kaggle F1 CSVs live in this repo. For these 9 files report the data-row count and header:
   drivers, constructors, circuits, seasons, status, races, results, qualifying, pit_stops.
   Compare with the counts in docs/milestone2_plan.md §1 and flag any mismatch.
3. Check whether Docker is available (docker --version, docker ps). Report only; don't start containers.
4. Create kg/ with: README.md (one-paragraph purpose + how to run, placeholder for the pinned Neo4j tag),
   requirements.txt (neo4j, pinned to the version you install into .venv), config.example.txt
   (exact 3-line format from the plan).
5. .gitignore: kg/config.txt, kg/*.csv.
6. Commit: "kg: scaffold milestone 2 folder and plan".
Summary ≤10 lines.
```

### P1b · Start Neo4j in Docker `[Sonnet · Plan mode no]`
```
Set up the local Neo4j server for milestone 2. Do not modify src/ or notebooks/.
1. Confirm Docker Desktop is running (docker info). If not, stop and tell me to start it.
2. Find the current stable Neo4j Community image tag on Docker Hub (a numeric 2026.x tag, not latest/enterprise),
   pull it, and record the exact tag in kg/README.md.
3. Generate a random 16-character alphanumeric password. Write kg/config.txt in the exact 3-line format
   (URI=neo4j://localhost:7687, USERNAME=neo4j, PASSWORD=<generated>). Confirm with git check-ignore that it is ignored.
4. docker run -d --name f1kg -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> -v f1kg-data:/data <pinned tag>
   (named volume, no bind mount). If the ports are taken, stop and report.
5. Wait until Bolt accepts connections, then verify with the neo4j Python driver from .venv: RETURN 1 and the server version.
6. Add to kg/README.md: start/stop/reset commands (docker start f1kg, docker stop f1kg,
   docker rm -f f1kg && docker volume rm f1kg-data) and the Browser URL http://localhost:7474.
7. Commit: "kg: document local Neo4j container". Never print or commit the password.
Summary ≤10 lines.
```

### P2 · Build `Create_kg.py` `[Opus · Plan mode yes]`
```
Implement kg/Create_kg.py exactly as specified in docs/milestone2_plan.md §4 (decisions KG2–KG13 and the type map in §4.1).
Constraints:
- Self-contained: standard library + neo4j driver only. No pandas, no imports from src/.
- Read CSVs with csv.DictReader; cast each column via one explicit TYPE_MAP; '\N' and '' (after strip) mean "omit the property".
- Dates via neo4j.time.Date / datetime.date.
- config.txt parsed by key with split('=', 1); pass DATABASE to the driver only if present.
- Paths relative to Path(__file__).parent; optional --data-dir and --config CLI args for local dev.
- Uniqueness constraints with IF NOT EXISTS; MERGE nodes on id + SET n += props; MATCH endpoints then MERGE each relationship separately.
- Load order per KG8; UNWIND batches of 2000.
- At the end print node counts per label and relationship counts per type (do not assert hardcoded totals).
- Keep functions small; a module docstring explaining the schema mapping and why stdlib csv is used.
Also add kg/tests/test_casting.py (pytest, no database needed): sentinel omission, int vs float casting,
date parsing, eventId format, config parsing incl. extra DATABASE line and '=' inside the password.
Run the tests. Commit: "kg: add Create_kg.py and casting tests".
Summary ≤10 lines.
```

### P3 · Build and verify `[Sonnet · Plan mode no]`
```
Neo4j is running locally (credentials in kg/config.txt). Copy nothing into git.
1. Write kg/verify_kg.py implementing every check in docs/milestone2_plan.md §6 (counts incl. FOR_RACE/BY_DRIVER/FOR_CONSTRUCTOR split by source label,
   types per property, no '\N' or '' values, 5-row spot check per table against the CSVs, orphan/multiplicity checks, direction check).
   It must exit non-zero on any failure.
2. Run Create_kg.py, then verify_kg.py. Run Create_kg.py a second time, then verify_kg.py again (idempotency).
3. If anything fails, stop and explain the root cause; do not change expected numbers to make it pass.
Commit: "kg: add graph verification script".
Summary ≤10 lines, including both runs' totals.
```

### P4 · Independent cross-check of my queries `[Opus · Plan mode no]`
Run this only after you've written all 5 queries yourself and I've reviewed them.
```
kg/queries.txt contains my 5 Cypher queries. Do not edit it.
1. Write kg/crosscheck.py that computes the answer to each of the 5 questions in docs/milestone2_plan.md §7 / the M2 PDF
   directly from the CSVs with pandas (dev-only script), following the PDF definitions literally.
2. Run each query in queries.txt against Neo4j and compare with the pandas result: same rows, same order, values equal to 2 dp, exact column names.
3. Report per query: PASS, or the first differing rows and your diagnosis of which side is wrong and why. Do not fix queries.txt.
Commit: "kg: add pandas cross-check for verification queries".
Summary ≤10 lines.
```

### P5 · Clean-room dry run `[Sonnet · Plan mode no]`
```
Simulate the grader.
1. Start a fresh Neo4j container on different host ports (e.g. 17474/17687) with a new named volume, same pinned tag as kg/README.md.
2. In a temp folder outside the repo, place only the 9 CSVs, Create_kg.py, and a config.txt pointing at that container
   that ALSO has a DATABASE=neo4j line in the middle.
3. Run Create_kg.py from a different working directory (e.g. the user's home). Then run kg/verify_kg.py against that container.
4. Parse kg/queries.txt with a regex for '^//(\d)\. Query \1$' headers; check there are exactly 5 in order, UTF-8 without BOM,
   no trailing semicolons; run each and confirm the exact column names.
5. Stop and remove the container and its volume, and delete the temp folder.
Commit only if a fix was needed (explain it first). Summary ≤10 lines.
```

---

## 11. Schedule

| Day | Work | Where |
|---|---|---|
| Fri 6 to Sat 7 | P1 scaffold, P1b Neo4j container; ask TA about O1/O4 | Claude Code |
| Sat 7 to Sun 8 | P2 build (paste its plan into chat for review before accepting) | Claude Code + chat |
| Mon 9 | P3 build + verify; investigate any failure | Claude Code + chat |
| Tue 10 to Wed 11 | Write the 5 queries (with Claude's help in chat); P4 cross-check | Browser + chat + Claude Code |
| Thu 12 | Phase 6 own queries; P5 clean-room run | All |
| Fri 13 to Sat 14 | **Submit** | Form |
| Sun 15 to Tue 17 | Study: S1–S4, script walkthrough, viva list (§9) | Chat |

If a day slips, compress Phase 6 first; never skip P3 or P5.
