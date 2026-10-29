# data-and-contracts.md

**The only file where changes need team agreement.** Everything here is an interface between people's modules (and their agents). Change it only via the process in `AGENTS.md` and log the change in `decisions-and-progress.md`.

Detailed reasoning for every item is in `docs/reference/project-plan-v2.md`.

## Contents
1. PostgreSQL schema (DDL, indexes, materialized views)
2. Neo4j model and sync rules
3. Extraction output format (Person 1 produces, Person 2's loader consumes)
4. Opportunity object (Person 3 produces, UI and RAG consume)
5. API endpoints

---

## 1. PostgreSQL schema (starting DDL)

This is the locked starting point. After Phase 1, schema changes are team decisions recorded in `decisions-and-progress.md`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Reference entities ----------------------------------------------------

CREATE TABLE institution (
    institution_id  SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    country         TEXT
);

CREATE TABLE venue (
    venue_id  SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    type      TEXT CHECK (type IN ('conference', 'journal', 'workshop', 'preprint', 'other')),
    UNIQUE (name, type)
);

CREATE TABLE author (
    author_id       SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    external_id     TEXT UNIQUE,          -- e.g. OpenAlex author ID
    institution_id  INT REFERENCES institution(institution_id)
);

-- Core paper table ------------------------------------------------------

CREATE TABLE paper (
    paper_id         TEXT PRIMARY KEY,    -- shared ID used in Neo4j (e.g. OpenAlex work ID)
    title            TEXT NOT NULL,
    abstract         TEXT,
    year             INT  CHECK (year BETWEEN 1950 AND 2100),
    doi              TEXT UNIQUE,
    venue_id         INT REFERENCES venue(venue_id),
    embedding        vector(768),         -- SPECTER2 on title + abstract
    embedding_model  TEXT                 -- model name and version
);

CREATE TABLE paper_author (
    paper_id      TEXT REFERENCES paper(paper_id) ON DELETE CASCADE,
    author_id     INT  REFERENCES author(author_id),
    author_order  INT  NOT NULL,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE citation (
    citing_paper_id  TEXT REFERENCES paper(paper_id) ON DELETE CASCADE,
    cited_paper_id   TEXT REFERENCES paper(paper_id) ON DELETE CASCADE,
    PRIMARY KEY (citing_paper_id, cited_paper_id),
    CHECK (citing_paper_id <> cited_paper_id)
);

-- Controlled vocabulary entities ----------------------------------------

CREATE TABLE method (
    method_id       SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL UNIQUE,
    description     TEXT,
    embedding       vector(768)          -- optional: centroid or description embedding
);

CREATE TABLE dataset (
    dataset_id      SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE task (
    task_id         SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE topic (
    topic_id        SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE setting (
    setting_id      SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE  -- e.g. 'low-resource', 'multilingual'
);

-- Aliases ---------------------------------------------------------------

CREATE TABLE method_alias (
    alias       TEXT PRIMARY KEY,
    method_id   INT NOT NULL REFERENCES method(method_id) ON DELETE CASCADE
);

CREATE TABLE dataset_alias (
    alias       TEXT PRIMARY KEY,
    dataset_id  INT NOT NULL REFERENCES dataset(dataset_id) ON DELETE CASCADE
);

CREATE TABLE task_alias (
    alias    TEXT PRIMARY KEY,
    task_id  INT NOT NULL REFERENCES task(task_id) ON DELETE CASCADE
);

-- Paper-level topic link (topics are paper-level, not experiment-level) -

CREATE TABLE paper_topic (
    paper_id  TEXT REFERENCES paper(paper_id) ON DELETE CASCADE,
    topic_id  INT  REFERENCES topic(topic_id),
    PRIMARY KEY (paper_id, topic_id)
);

-- Experiment: the unit that means "used together" -----------------------

CREATE TABLE experiment (
    experiment_id    SERIAL PRIMARY KEY,
    paper_id         TEXT NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    method_id        INT  NOT NULL REFERENCES method(method_id),
    dataset_id       INT  REFERENCES dataset(dataset_id),   -- nullable: not always stated
    task_id          INT  REFERENCES task(task_id),
    setting_id       INT  REFERENCES setting(setting_id),
    confidence       REAL CHECK (confidence BETWEEN 0 AND 1),
    source_sentence  TEXT,                                  -- evidence shown in the UI
    extractor        TEXT,                                  -- e.g. 'llm-v1', 'rules-v2', 'manual'
    reviewed         BOOLEAN DEFAULT FALSE,
    UNIQUE NULLS NOT DISTINCT (paper_id, method_id, dataset_id, task_id, setting_id)  -- PostgreSQL 15+
);

CREATE TABLE result (
    result_id      SERIAL PRIMARY KEY,
    experiment_id  INT NOT NULL REFERENCES experiment(experiment_id) ON DELETE CASCADE,
    metric         TEXT NOT NULL,
    value          NUMERIC,
    context        TEXT
);

-- Opportunities (computed output, stored for the UI and evaluation) -----

CREATE TABLE opportunity (
    opportunity_id         SERIAL PRIMARY KEY,
    method_id              INT REFERENCES method(method_id),
    dataset_id             INT REFERENCES dataset(dataset_id),
    task_id                INT REFERENCES task(task_id),
    setting_id             INT REFERENCES setting(setting_id),
    corpus_cutoff_year     INT NOT NULL,        -- supports the temporal holdout test
    observed_count         INT NOT NULL,
    expected_count         REAL NOT NULL,
    sparsity               REAL,
    semantic_compatibility REAL,
    temporal_activity      REAL,
    graph_bridge_strength  REAL,
    method_compatibility   REAL,
    confidence             REAL,
    score                  REAL,
    weights_version        TEXT,
    created_at             TIMESTAMP DEFAULT now()
);

CREATE TABLE opportunity_evidence (
    opportunity_id  INT REFERENCES opportunity(opportunity_id) ON DELETE CASCADE,
    paper_id        TEXT REFERENCES paper(paper_id),
    role            TEXT CHECK (role IN ('supports_A', 'supports_B', 'bridge', 'nearest_existing')),
    PRIMARY KEY (opportunity_id, paper_id, role)
);

CREATE TABLE opportunity_feedback (          -- optional stretch
    feedback_id     SERIAL PRIMARY KEY,
    opportunity_id  INT REFERENCES opportunity(opportunity_id) ON DELETE CASCADE,
    useful          BOOLEAN NOT NULL,
    note            TEXT,
    created_at      TIMESTAMP DEFAULT now()
);

-- Indexes ---------------------------------------------------------------

CREATE INDEX idx_paper_year          ON paper(year);
CREATE INDEX idx_paper_venue         ON paper(venue_id);
CREATE INDEX idx_citation_cited      ON citation(cited_paper_id);
CREATE INDEX idx_experiment_paper    ON experiment(paper_id);
CREATE INDEX idx_experiment_method   ON experiment(method_id);
CREATE INDEX idx_experiment_dataset  ON experiment(dataset_id);
CREATE INDEX idx_experiment_task     ON experiment(task_id);
CREATE INDEX idx_paper_embedding_hnsw
    ON paper USING hnsw (embedding vector_cosine_ops);
```

**Notes**

- `paper_id` is a text ID from the source (for example an OpenAlex work ID) so that the same value is used in Neo4j.
- `dataset_id` and `task_id` are nullable in `experiment` because abstracts do not always state them. The combination views below only count rows where the relevant columns are present.
- The `experiment` uniqueness uses `NULLS NOT DISTINCT` (PostgreSQL 15+) so rows with a missing dataset, task, or setting cannot be inserted twice. Pin the Docker image to PostgreSQL 15 or later with pgvector (for example `pgvector/pgvector:pg16`).
- `vector(768)` matches SPECTER2. The dimension is fixed by the embedding model. Switching to a model with a different dimension (many Sentence Transformers use 384) means altering the column, re-embedding every paper, and rebuilding the HNSW index. Decide the model (open decision O3) before loading data.
- `author.institution_id` is a simplification: it stores one institution per author, although affiliations change from paper to paper.
- Normal form: all tables are intended to be in 3NF. The `opportunity` table stores derived scores on purpose (a deliberate denormalization for speed and reproducibility); note this in the report.

### 1.1 Combination-frequency materialized views

Count **distinct papers**, not experiment rows, so a paper with several experiments is not counted twice.

**Same-universe rule.** For any pair, `n_A`, `n_B`, the total `N`, and the observed count must all be counted over the same set of papers: those where every element of the pair was extracted. Method is always present; dataset and task may be missing. Mixing universes (for example method counts over all papers with dataset counts over only papers that name a dataset) inflates the expected count and makes pairs look falsely sparse. The views below follow this rule:

| Pair | Universe | Count views to use | Total `N` |
|---|---|---|---|
| method × dataset | experiments with a dataset | `mv_method_count_md`, `mv_dataset_count` | `mv_universe_size` row `method_dataset` |
| method × task | experiments with a task | `mv_method_count_mt`, `mv_task_count` | `mv_universe_size` row `method_task` |
| dataset × task | experiments with both | `mv_dataset_count_dt`, `mv_task_count_dt` | `mv_universe_size` row `dataset_task` |

`mv_dataset_count` and `mv_task_count` already filter to non-null values, so they match the method × dataset and method × task universes. `mv_method_count` (all papers with a method) is for method popularity only, never for pair expected counts.

```sql
-- Individual frequencies
CREATE MATERIALIZED VIEW mv_method_count AS
SELECT method_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment GROUP BY method_id;

CREATE MATERIALIZED VIEW mv_dataset_count AS
SELECT dataset_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL GROUP BY dataset_id;

CREATE MATERIALIZED VIEW mv_task_count AS
SELECT task_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE task_id IS NOT NULL GROUP BY task_id;

-- Pair frequencies
CREATE MATERIALIZED VIEW mv_method_dataset AS
SELECT method_id, dataset_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL
GROUP BY method_id, dataset_id;

CREATE MATERIALIZED VIEW mv_method_task AS
SELECT method_id, task_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE task_id IS NOT NULL
GROUP BY method_id, task_id;

CREATE MATERIALIZED VIEW mv_dataset_task AS
SELECT dataset_id, task_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL
GROUP BY dataset_id, task_id;

-- Counts within each pair's universe (see the same-universe rule above)
CREATE MATERIALIZED VIEW mv_method_count_md AS
SELECT method_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL GROUP BY method_id;

CREATE MATERIALIZED VIEW mv_method_count_mt AS
SELECT method_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE task_id IS NOT NULL GROUP BY method_id;

CREATE MATERIALIZED VIEW mv_dataset_count_dt AS
SELECT dataset_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL
GROUP BY dataset_id;

CREATE MATERIALIZED VIEW mv_task_count_dt AS
SELECT task_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL
GROUP BY task_id;

-- Universe sizes (the N for each pair type)
CREATE MATERIALIZED VIEW mv_universe_size AS
SELECT 'method_dataset' AS pair_type, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL
UNION ALL
SELECT 'method_task', COUNT(DISTINCT paper_id)
FROM experiment WHERE task_id IS NOT NULL
UNION ALL
SELECT 'dataset_task', COUNT(DISTINCT paper_id)
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL;

-- Triple frequencies (stretch)
CREATE MATERIALIZED VIEW mv_method_dataset_task AS
SELECT method_id, dataset_id, task_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL
GROUP BY method_id, dataset_id, task_id;
```

**Refresh strategy.** Refresh after each ingestion/extraction batch with `REFRESH MATERIALIZED VIEW CONCURRENTLY`, which requires a unique index on each view. Document this in the report.

```sql
CREATE UNIQUE INDEX ON mv_method_count (method_id);
CREATE UNIQUE INDEX ON mv_dataset_count (dataset_id);
CREATE UNIQUE INDEX ON mv_task_count (task_id);
CREATE UNIQUE INDEX ON mv_method_dataset (method_id, dataset_id);
CREATE UNIQUE INDEX ON mv_method_task (method_id, task_id);
CREATE UNIQUE INDEX ON mv_dataset_task (dataset_id, task_id);
CREATE UNIQUE INDEX ON mv_method_count_md (method_id);
CREATE UNIQUE INDEX ON mv_method_count_mt (method_id);
CREATE UNIQUE INDEX ON mv_dataset_count_dt (dataset_id);
CREATE UNIQUE INDEX ON mv_task_count_dt (task_id);
CREATE UNIQUE INDEX ON mv_universe_size (pair_type);
CREATE UNIQUE INDEX ON mv_method_dataset_task (method_id, dataset_id, task_id);
```

---

## 2. Neo4j model and sync rules

### 2.1 Nodes

`Paper`, `Author`, `Institution`, `Venue`, `Method`, `Dataset`, `Task`, `Topic`, `Setting`, `Experiment`, `Result`

Every node carries the same ID as its PostgreSQL row (`paper_id`, `author_id`, and so on).

### 2.2 Relationships

```text
(Author)-[:WROTE {order}]->(Paper)
(Author)-[:AFFILIATED_WITH]->(Institution)
(Paper)-[:PUBLISHED_IN]->(Venue)
(Paper)-[:CITES]->(Paper)
(Paper)-[:ABOUT]->(Topic)
(Paper)-[:HAS_EXPERIMENT]->(Experiment)
(Experiment)-[:USES_METHOD]->(Method)
(Experiment)-[:EVALUATED_ON]->(Dataset)
(Experiment)-[:SOLVES]->(Task)
(Experiment)-[:IN_SETTING]->(Setting)
(Experiment)-[:REPORTS]->(Result)
```

**Derived shortcut edges** (kept so the synopsis edge list stays accurate and common queries stay short):

```text
(Paper)-[:USES_METHOD]->(Method)
(Paper)-[:EVALUATED_ON]->(Dataset)
(Paper)-[:SOLVES]->(Task)
(Paper)-[:REPORTS]->(Result)
```

These are generated from the Experiment nodes during sync. Experiment nodes are the canonical representation.

### 2.3 Sync rules

1. PostgreSQL is the only place data is written first.
2. Sync is a **batch, idempotent job** using `MERGE` on IDs, never `CREATE`.
3. After each sync run, a verification script compares counts (papers, citations, experiments) between PostgreSQL and Neo4j and fails loudly on mismatch.
4. Re-running the sync must not change the result.
5. Create uniqueness constraints in Neo4j on every node ID before loading.

---

## 3. Extraction output format

One JSON object per extracted experiment, delivered as JSON Lines (`.jsonl`). Entity names must come from the controlled vocabulary or its aliases. Unknown values are `null`, never invented.

```json
{
  "paper_id": "W1234567890",
  "method": "Knowledge Distillation",
  "dataset": "FLORES-200",
  "task": "Machine Translation",
  "setting": "Low-resource",
  "confidence": 0.86,
  "source_sentence": "We evaluate knowledge distillation on FLORES-200 for low-resource translation.",
  "extractor": "llm-v1"
}
```

Rules:
- `paper_id` must already exist in the `paper` table (same ID is used in Neo4j).
- `method` is required. `dataset`, `task`, `setting` may be `null`.
- `confidence` is in [0, 1]. Rows below the agreed threshold go to the review queue, not into scoring.
- `source_sentence` is stored verbatim and shown in the UI as evidence.
- A `method`, `dataset`, `task`, or `setting` that is not in the controlled vocabulary or its aliases is **not inserted**. The loader writes the row to a review queue (a rejects file or table) and never creates a new entity silently. New vocabulary entries are added deliberately by the extraction owner.

---

## 4. Opportunity object

```json
{
  "opportunity_id": 17,
  "elements": {
    "method": "Knowledge Distillation",
    "task": "Machine Translation",
    "dataset": "FLORES-200",
    "setting": "Low-resource"
  },
  "corpus": { "papers": 6420, "cutoff_year": 2025 },
  "observed_count": 2,
  "expected_count": 11.4,
  "signals": {
    "sparsity": 0.82,
    "semantic_compatibility": 0.89,
    "temporal_activity": 0.91,
    "graph_bridge_strength": 0.71,
    "method_compatibility": 0.80
  },
  "confidence": 0.78,
  "score": 84,
  "weights_version": "v1-three-signal",
  "evidence": {
    "supports_A": ["paper_id_1", "paper_id_2"],
    "supports_B": ["paper_id_3"],
    "bridge": ["paper_id_4"],
    "nearest_existing": ["paper_id_5"]
  }
}
```

Signals not yet implemented are `null`, not omitted. Phase 1 uses three signals (sparsity, semantic compatibility, temporal activity); graph bridge strength and method compatibility are added only if they change the ranking.

---

## 5. API endpoints

```text
POST /search                         body: {"query": "...", "top_k": 10, "year_min": 2020}
GET  /papers/{id}
GET  /papers/{id}/graph
GET  /papers/{id}/related
GET  /landscape
GET  /clusters
GET  /trends
GET  /opportunities
GET  /opportunities/{id}
POST /opportunities/{id}/explain
POST /opportunities/{id}/feedback    (stretch)
POST /rag/query
```

Request bodies and response shapes should follow the objects above. Add exact schemas here as endpoints are built.
