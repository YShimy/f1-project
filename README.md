# Formula 1 — CSEN903 (Team 120)

## Milestone 1: podium prediction

The graded Milestone 1 state is tagged `ms1-submission`.

For every driver entering a Formula 1 race, predict whether that driver finishes on the
podium (`positionOrder <= 3`), using only information that exists **after qualifying and
before the race starts**. Anything produced by the race itself — finishing position, points,
laps, status, pit stops, post-race standings — is treated as leakage and excluded.

### Contents

| File | What it is |
| --- | --- |
| `f1-project-ms1.ipynb` | The run-all notebook: raw-data audit, cleaning, EDA before and after, the three data-engineering questions, feature engineering, the modeling table and leakage checks, three models, experiments, XAI and the inference function. Sections 1–14. |
| `F1_MS1_Report_Team120.pdf` | The analytical report: the same work written up, with every figure and the design decisions behind it. |

### Results in one line

A depth-4 random forest, chosen on the validation seasons, reaches **PR-AUC 0.721 and
ROC-AUC 0.940 on the unseen test seasons (2022–2024)** — about 4.8× the PR-AUC of a random
model at a 15.1% podium rate. Starting position dominates; recent form, championship
position and qualifying speed add smaller, partly overlapping information.

### Data

Formula 1 World Championship 1950–2024 (Kaggle / Ergast):
`rohanrao/formula-1-world-championship-1950-2020`. The CSVs are not committed here.

### Running it

- **On Kaggle (as it was run):** https://www.kaggle.com/code/seifezz11/f1-project-ms1 —
  the dataset above is attached as a notebook input at
  `/kaggle/input/datasets/rohanrao/formula-1-world-championship-1950-2020/`, then **Run All**.
- **Locally:** download the dataset from Kaggle, then change `PATH` in the first code cell of
  section 1 to the folder holding the CSV files. The notebook needs `pandas`, `numpy`,
  `matplotlib`, `seaborn`, `scikit-learn`, `tensorflow`, `shap` and `lime`.

The notebook runs top to bottom with no hidden state; random seeds are fixed, so the
statistical models reproduce exactly (the neural network can move by about ±0.01).

### Notebook map

| Section | Contents |
| --- | --- |
| 1–2 | Setup, loading, `\N` sentinels, semantic typing (dates, lap times → seconds) |
| 3 | Primary and foreign keys, grain `(raceId, driverId)`, duplicate driver-race rows |
| 4 | Scope: qualifying coverage by season, pre-race non-starters, missingness |
| 5 | EDA after cleaning, compared with before |
| 6–8 | Q1 front-row conversion by circuit · Q2 home advantage · Q3 mechanical retirements |
| 9 | Feature engineering: form, reliability, championship rank, qualifying gap |
| 10 | Modeling table, missing-value policy, leakage checks, season split |
| 11 | Logistic regression (baseline), random forest, shallow neural network; preprocessing effects |
| 12 | Feature-group ablation and two preprocessing-order experiments |
| 13 | Permutation importance, SHAP (global and local), LIME |
| 14 | `predict_podium`: inference on a complete and a partially-missing record |

## Milestone 2: knowledge graph

The same F1 data loaded into Neo4j as a knowledge graph: `kg/Create_kg.py` builds the graph from
the 9 raw CSVs and `kg/queries.txt` holds the Cypher queries. Setup, the local Neo4j container
and how to run it are in [`kg/README.md`](kg/README.md); the plan is in
[`docs/milestone2_plan.md`](docs/milestone2_plan.md).
