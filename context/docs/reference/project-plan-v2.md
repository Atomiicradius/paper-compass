# Research Paper Discovery and Exploration System

## Project Context, Locked Design, and Execution Plan (v2)

**Course:** Database Management Systems (CD252IA), RV College of Engineering, Bengaluru
**Team:** Samarth Kulkarni (1RV24CS244), Samarth P Rao (1RV24CS245), Samarth Sainath Naik (1RV24CS246)

**Reference document.** This file holds the detailed reasoning behind the design. The day-to-day source of truth is the set of context files in the `context/` folder (two levels up from this file): `data-and-contracts.md` (schema and interfaces), `build-plan.md` (ownership, phases, timeline), and `decisions-and-progress.md` (open decisions, decision log, status). **If this file disagrees with one of those files, those files are correct.** Section 16 (team and timeline) and Section 18 (decision log) were moved to those files and are now pointers only. This file supersedes `original-context.md` where they differ. The synopsis wording remains valid at a high level.

---

## 1. Project Summary

**Problem.** Researchers can find papers easily but still have to connect methods, tasks, datasets, and topics by hand to see what is well covered and what is weakly covered.

**Solution.** A research exploration system that retrieves papers for a research idea, maps how the surrounding work is connected, detects combinations of research elements that are individually common but rarely used together, ranks them, and shows the evidence behind each one.

**Pipeline:**

```text
DISCOVER → CONNECT → MAP → DETECT → SCORE → EXPLAIN
```

| Stage | What happens | Main technology |
|---|---|---|
| Discover | Embed the query, retrieve similar papers, apply metadata filters | pgvector + PostgreSQL |
| Connect | Exact metadata, citations, entity relationships | PostgreSQL + Neo4j |
| Map | Clusters, temporal trends, bridges, weak links | SQL + Neo4j + embeddings |
| Detect | Find weakly represented combinations of elements | PostgreSQL (materialized views) |
| Score | Rank candidates with normalized signals | Python scoring engine |
| Explain | Structured evidence chain, then RAG phrasing | PostgreSQL + Neo4j + LLM |

**One-line story:**

> Find the papers → understand the relationships → identify weakly explored combinations → rank them → explain why they matter.

**Critical caveat.** A candidate opportunity is a signal for further investigation, not proof of a research gap.

---

## 2. Positioning and Claims

This is a **DBMS / system-engineering project with intelligent retrieval and analysis components**. We are not proposing a new embedding model, LLM, or graph algorithm. The contribution is the integrated workflow and the evidence-grounded opportunity analysis on top of it.

**Defensible novelty statement (long):**

> Existing academic discovery systems provide strong capabilities for searching, recommending, mapping, and summarizing literature. Our system focuses on the next step: identifying potentially underexplored combinations of research elements such as methods, tasks, datasets, and topics, ranking them using semantic, graph, temporal, and sparsity signals, and exposing the evidence behind each result through an integrated database and RAG workflow.

**Short version:**

> The system goes beyond finding related papers by detecting and explaining potentially underexplored research-element combinations.

**DBMS version:**

> The project demonstrates how relational, vector, and graph representations can be combined to support queries that are difficult to answer using any single representation, culminating in evidence-based research-opportunity analysis.

### 2.1 Do NOT claim novelty for

Semantic search, citation graphs, knowledge graphs, paper recommendation, research clustering, temporal mapping, RAG, generic research-gap detection, graph + embeddings, method-aware recommendation. All of these exist in research or commercial tools.

### 2.2 Terminology rules

| Prefer | Avoid |
|---|---|
| potentially underexplored | definitely unexplored |
| candidate research opportunity | guaranteed research gap |
| weakly represented in the analyzed corpus | nobody has done this |
| evidence-grounded explanation | AI discovered a new research area |
| research-element combination | RAG finds research gaps automatically |
| three complementary representations | three databases |

### 2.2.1 Evaluation claim rule

Do not claim "research-gap accuracy." We evaluate plausibility and predictive signal (Section 12), not ground-truth correctness.

---

## 3. Locked Scope

### 3.1 Core (must be built)

- PostgreSQL schema with constraints and indexes
- pgvector semantic search
- Neo4j research graph
- Method / Dataset / Task / Setting / Result modeling via an Experiment entity
- Controlled vocabulary with aliases and extraction provenance
- Weak-combination detection (pairs first)
- Opportunity scoring with normalized signals and confidence
- Evidence chain (structured JSON) and RAG phrasing with citation verification
- Evaluation (retrieval, extraction, temporal holdout, baselines)
- DBMS benchmarks (Section 13)
- Web UI for the one-query demo

### 3.2 Stretch (only if core is done)

- Triple combinations (Method + Dataset + Task)
- Graph bridge strength and method compatibility as extra signals (see 8.3 for phasing)
- Clustering beyond HDBSCAN on embeddings
- Weight sliders in the UI
- User feedback buttons

### 3.3 Deferred / cut

Temporal forecasting, contradiction analysis, intra-paper knowledge graph, collaboration analysis, research path finder, method transfer detector. These may be mentioned as future work.

### 3.4 Domain decision (to confirm in the Week 1 meeting)

- **Subfield:** NLP, with machine translation as the demo area (supports the Kannada low-resource example).
- **Corpus size:** about 5,000 to 10,000 papers.
- **Source candidates:** OpenAlex API, Semantic Scholar API, ACL Anthology. Check whether an annotated Papers with Code dump is still obtainable; if it is, use it to seed method/dataset/task labels.
- **Pilot:** download ~500 papers first and confirm that abstracts, years, and citation links are usable before committing to a source.

---

## 4. Architecture: Three Complementary Representations

```text
                    RESEARCH IDEA
                         |
                         v
              Embedding + Metadata Filters
                         |
                         v
                  Relevant Papers
                         |
            +------------+------------+
            |                         |
            v                         v
      PostgreSQL + pgvector         Neo4j
      exact data, vectors,       relationships,
      statistics                 traversal, bridges
            |                         |
            +------------+------------+
                         |
                         v
                Research Landscape
        (clusters, temporal trends, weak links)
                         |
                         v
              Candidate Generation
          (combination frequencies, filters)
                         |
                         v
               Opportunity Scoring
                         |
                         v
        Evidence Chain (structured JSON)
                         |
                         v
        RAG phrasing + citation verification
                         |
                         v
                    Researcher
```

| Need | Technology |
|---|---|
| Exact metadata, constraints, filtering | PostgreSQL |
| Aggregation, temporal counts, combination frequency | PostgreSQL |
| Semantic similarity | pgvector (extension inside PostgreSQL) |
| Citation traversal, multi-hop relationships | Neo4j |
| Bridges and graph exploration | Neo4j |
| Opportunity scoring | PostgreSQL + Neo4j + vector results |
| Natural-language explanation | RAG over structured evidence |

**Source of truth rule.** PostgreSQL is authoritative. Neo4j is a derived graph projection rebuilt by an idempotent batch sync (Section 7). Neo4j is a graph NoSQL database; pgvector is not a separate database.

**Embeddings.** SPECTER2 (title + abstract) for the real system, 768 dimensions. A small Sentence Transformer is acceptable for the first prototype, but record the model name and version so vectors are never mixed.

---

## 5. Data Model Changes (Locked Improvements)

These changes are what make the "Method + Dataset + Task" claim meaningful.

| # | Change | Why |
|---|---|---|
| 1 | Add **EXPERIMENT** entity (paper, method, dataset, task, setting) | Co-occurrence in a paper does not mean the method was evaluated on that dataset. An experiment row encodes "used together." |
| 2 | **RESULT links to EXPERIMENT**, not only to Paper | A metric belongs to a specific method-dataset pair. |
| 3 | **Alias tables** for Method, Dataset, Task | Normalizes BERT / mBERT / BERT-base to one canonical entity. |
| 4 | **Extraction provenance** (confidence, source sentence, extractor, version) on every extracted link | Makes extraction errors measurable and filterable, and doubles as UI evidence. |
| 5 | **SETTING** entity (low-resource, multilingual, etc.) | The demo query depends on it. |
| 6 | **INSTITUTION table** added | The synopsis lists it but the earlier schema had no table. |
| 7 | **Author order** on PAPER_AUTHOR | Needed for correct author lists. |
| 8 | **Composite primary keys** on all junction tables and CITATION | Prevents duplicates. |
| 9 | Combination counts come from **materialized views** over EXPERIMENT | Replaces the undefined `paper_method_dataset_task` table in the old queries. |

---

## 6. PostgreSQL Schema (Starting DDL)

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

### 6.1 Combination-frequency materialized views

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

### 6.2 Example queries

Hybrid search (metadata filter plus vector similarity in one statement):

```sql
SELECT paper_id, title, year,
       1 - (embedding <=> :query_vec) AS similarity
FROM paper
WHERE year >= 2020
ORDER BY embedding <=> :query_vec
LIMIT 10;
```

Method usage:

```sql
SELECT m.canonical_name, c.n_papers
FROM mv_method_count c
JOIN method m USING (method_id)
ORDER BY c.n_papers DESC;
```

Weak method-dataset pairs, restricted to common elements. All counts and the total come from the same universe (experiments with a dataset extracted):

```sql
SELECT m.canonical_name AS method, d.canonical_name AS dataset,
       COALESCE(md.n_papers, 0) AS observed,
       (mc.n_papers::real * dc.n_papers) / u.n_papers AS expected
FROM mv_method_count_md mc
JOIN mv_dataset_count dc ON TRUE
JOIN mv_universe_size u ON u.pair_type = 'method_dataset'
JOIN method  m ON m.method_id  = mc.method_id
JOIN dataset d ON d.dataset_id = dc.dataset_id
LEFT JOIN mv_method_dataset md
       ON md.method_id = mc.method_id AND md.dataset_id = dc.dataset_id
WHERE mc.n_papers >= :min_support AND dc.n_papers >= :min_support
  AND COALESCE(md.n_papers, 0) < (mc.n_papers::real * dc.n_papers) / u.n_papers
ORDER BY COALESCE(md.n_papers, 0)::real
         / ((mc.n_papers::real * dc.n_papers) / u.n_papers);
```

`:min_support` prevents scoring rare entities. For method × task and dataset × task, use the matching `_mt` / `_dt` views and the `method_task` / `dataset_task` rows of `mv_universe_size`.

---

## 7. Neo4j Graph Model and Sync

### 7.1 Nodes

`Paper`, `Author`, `Institution`, `Venue`, `Method`, `Dataset`, `Task`, `Topic`, `Setting`, `Experiment`, `Result`

Every node carries the same ID as its PostgreSQL row (`paper_id`, `author_id`, and so on).

### 7.2 Relationships

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

### 7.3 Sync rules

1. PostgreSQL is the only place data is written first.
2. Sync is a **batch, idempotent job** using `MERGE` on IDs, never `CREATE`.
3. After each sync run, a verification script compares counts (papers, citations, experiments) between PostgreSQL and Neo4j and fails loudly on mismatch.
4. Re-running the sync must not change the result.
5. Create uniqueness constraints in Neo4j on every node ID before loading.

### 7.4 Example Cypher

```cypher
// Papers using a method
MATCH (p:Paper)-[:USES_METHOD]->(m:Method {canonical_name: "Knowledge Distillation"})
RETURN p;

// Datasets used for a task (experiment-level, so "evaluated together" is correct)
MATCH (e:Experiment)-[:SOLVES]->(t:Task {canonical_name: "Machine Translation"})
MATCH (e)-[:EVALUATED_ON]->(d:Dataset)
RETURN d.canonical_name, count(DISTINCT e) AS n
ORDER BY n DESC;

// Bridge papers between two methods via shared tasks
MATCH (m1:Method {canonical_name: $a})<-[:USES_METHOD]-(:Experiment)-[:SOLVES]->(t:Task)
      <-[:SOLVES]-(:Experiment)-[:USES_METHOD]->(m2:Method {canonical_name: $b})
RETURN t.canonical_name, count(*) AS links
ORDER BY links DESC;

// Multi-hop citation traversal (used in the DBMS benchmark)
MATCH path = (p:Paper {paper_id: $id})-[:CITES*1..3]->(q:Paper)
RETURN q.paper_id, length(path);
```

---

## 8. Opportunity Detection and Scoring

### 8.1 Candidate generation (pairs first)

```text
1. Extract methods / tasks / datasets / settings into EXPERIMENT
2. Count single-entity frequencies (distinct papers)
3. Count pair intersections (mv_method_dataset, mv_method_task, mv_dataset_task)
4. Keep only entities with support >= min_support (for example 10 papers)
5. Compute expected vs observed count for each pair
6. Keep pairs where observed is clearly below expected
7. Filter by semantic compatibility (drop unrelated pairs)
8. Compute remaining signals
9. Compute score and confidence
10. Retrieve evidence, then generate the explanation
```

To avoid combinatorial explosion, generate candidates from the **neighborhood of the user query** (entities found in the retrieved papers) plus entities above the support threshold, never all-versus-all.

Triples are a stretch goal and should be built only after pairs are evaluated.

### 8.2 Signals

All signals are normalized to the range 0 to 1 **before** weighting.

**Sparsity (replaces raw counts).** Raw counts are misleading, so compare observed with expected under independence:

```text
For elements A and B in a corpus of N papers:
    expected(A,B) = n_A * n_B / N
    lift(A,B)     = observed(A,B) / expected(A,B)

    sparsity = 1 - min(1, lift)          # 1 means never co-occurs when expected to
```

A smoothed variant such as `1 - (observed + 1) / (expected + 1)` (clipped to [0, 1]) avoids division by zero. An alternative is pointwise mutual information; pick one and keep it fixed for the evaluation.

**Same-universe rule.** `n_A`, `n_B`, `N`, and `observed` must all be counted over the same set of papers: those where every element of the pair was extracted. For method × dataset, that means papers with at least one experiment that names a dataset. Mixing universes (for example method counts over all papers with dataset counts over papers that name a dataset) inflates `expected` and makes pairs look falsely sparse.

**Confidence for sparsity.** A low observed count is only informative when the expected count is high enough:

```text
confidence = min(1, expected / k)        # k is a tuning constant, for example 5
```

If `expected < 1`, the pair is simply rare for structural reasons, so it should score low confidence or be filtered out.

**Semantic compatibility.** Cosine similarity between the centroid embeddings of papers for A and for B, rescaled to [0, 1] using the corpus distribution (percentile rank).

**Temporal activity.** Combine recent paper share and trend slope for both elements, for example the fraction of each element's papers from the last 3 years and the slope of yearly counts, normalized by percentile rank.

**Graph bridge strength** (phase 2 signal). Evidence connecting the areas: number of bridge papers, shared neighbors (Jaccard of entity neighborhoods), shared authors, and citation links between the two sets. Normalize by percentile rank.

**Method compatibility** (phase 2 signal). Whether the method appears technically relevant to the target task or area. Practical definition: similarity between the method's usage profile (distribution over tasks) and the target task or its neighbors. This is evidence of compatibility, not a feasibility guarantee.

### 8.3 Score

```text
Score = 100 * sum(w_i * s_i)         with sum(w_i) = 1 and each s_i in [0, 1]
```

**Phase 1 (three signals):**

| Signal | Default weight |
|---|---|
| Sparsity | 0.40 |
| Semantic compatibility | 0.35 |
| Temporal activity | 0.25 |

**Phase 2 (five signals, add only if they measurably change the ranking):**

| Signal | Default weight |
|---|---|
| Sparsity | 0.30 |
| Semantic compatibility | 0.25 |
| Temporal activity | 0.20 |
| Graph bridge strength | 0.15 |
| Method compatibility | 0.10 |

These weights are starting values, not claims. Report a **sensitivity check**: vary each weight and show how the top-10 ranking changes. Store `weights_version` with every opportunity.

**Always display per-signal values and the confidence next to the score**, not only a single number.

### 8.4 Opportunity object

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

---

## 9. Evidence Chain and RAG

### 9.1 Evidence chain (structured first)

Every opportunity exposes a structured, checkable chain before any text is generated:

```text
Potential opportunity
   -> Area A (papers, counts, years)
   -> Area B (papers, counts, years)
   -> Connecting papers / bridges (few)
   -> Method X common in A, rare in B (with counts)
   -> Recent activity (yearly counts)
   -> Nearest existing work (closest paper that already combines two of the elements)
   -> Supporting papers
```

The **nearest existing work** section is mandatory. It guards against false "gaps."

The same layer explains why a paper was recommended: semantic similarity, shared task, method, or dataset, graph proximity, citation evidence, and temporal relevance.

### 9.2 RAG rules

1. Retrieve evidence first.
2. The LLM phrases and summarizes the structured evidence; it does not invent gaps.
3. Ground every claim in retrieved papers.
4. Separate "the corpus shows" from "the system infers."
5. Never claim a gap is proven.
6. State corpus limitations (size, date range, extraction confidence).
7. Prefer multiple supporting papers.
8. **Citation verification:** after generation, check that every paper the answer names is in the retrieved evidence set; reject or regenerate otherwise.

### 9.3 Example RAG questions

- Why was this opportunity flagged?
- Which papers support it?
- What existing work comes closest?
- Which methods and datasets are involved?
- Are there contradictory results in the evidence?

---

## 10. Data Pipeline and Extraction

```text
Raw papers / metadata
        |
Metadata cleaning (dedupe by DOI / ID, normalize years and venues)
        |
Entity extraction (method, dataset, task, setting, metric)
        |
Normalization via alias tables and closed vocabulary
        |
Relationship construction (EXPERIMENT rows with confidence and source sentence)
        |
PostgreSQL  +  Neo4j sync  +  embeddings
```

### 10.1 Extraction approach

Extraction is the single riskiest component. Rules:

1. **Prefer existing annotations** if a usable source exists (for example an annotated Papers with Code dump). Use an LLM only to fill gaps.
2. **Closed vocabulary first.** Start with about 100 methods, 50 tasks, 50 datasets. The extractor must choose from this list (or return "none") rather than inventing names. Grow the list deliberately.
3. **Store provenance:** confidence, source sentence, extractor name and version for every link.
4. **Low-confidence queue.** Anything below a threshold goes to a review list instead of being used in scoring.
5. **Measure accuracy.** Hand-label about 100 abstracts and report precision and recall per entity type. This number goes in the report.
6. **Remember abstract limits.** Many abstracts do not name the dataset. Missing datasets cause undercounting and false sparsity, so restrict early analysis to pairs the extractor covers well (for example method × task) and state coverage per entity type.

Example extraction:

> We evaluate knowledge distillation on FLORES-200 for low-resource translation.

```text
Method:  Knowledge Distillation
Dataset: FLORES-200
Task:    Machine Translation
Setting: Low-resource
```

---

## 11. Research Landscape Analysis

- **Clusters:** HDBSCAN (or k-means) on paper embeddings, optionally combined with citation and topic overlap. Clusters are useful but are not the novelty; keep them simple.
- **Weakly connected areas:** two clusters that are semantically related but share few citations, authors, methods, or datasets are flagged. This is a signal, not a proof.
- **Bridges:** a paper, author, method, dataset, or topic that connects two clusters.
- **Temporal evolution:** emerging and declining topics, method transitions, dataset usage trends, changing citation activity, computed from yearly SQL aggregates.

---

## 12. Evaluation Plan

### 12.1 Retrieval

- Metrics: Precision@K, Recall@K, nDCG@K (MRR where it fits).
- Compare keyword search (PostgreSQL full-text) against vector search, and optionally a hybrid.
- Build a small query set (for example 15 to 20 queries) with relevance judgments from the team.

### 12.2 Extraction

- Hand-label ~100 abstracts.
- Report precision and recall per entity type, and the share of papers with a dataset or task extracted at all.

### 12.3 Opportunity detection

1. **Temporal holdout (primary test).** Build the corpus using papers up to year Y (for example 2022). Run the detector. Check which flagged combinations actually appear in papers from Y+1 onward. No human labels needed.
2. **Baselines.** Compare the full multi-signal ranking against (a) random, (b) sparsity only, and (c) semantic similarity only. Report whether the multi-signal score ranks future-appearing combinations higher.
3. **Hide-and-recover.** Hide a set of known combinations, run the detector, and measure their ranks.
4. **Small expert rating.** Ask a few NLP-aware classmates or a faculty member to rate the top 10 candidates for relevance, plausibility, novelty signal, and evidence quality.
5. **Sensitivity analysis** of the score weights.

**Caveat to state in the report:** a combination can appear later for reasons unrelated to our signals, and absence from the corpus does not mean absence from research. The evaluation shows predictive signal, not research-gap accuracy.

### 12.4 Explanation

- Evidence relevance, citation correctness (automated check against the retrieved set), factual consistency, and grounding, on a sample of generated explanations.

### 12.5 Graph

- Query latency and traversal time for typical Cypher queries (see Section 13).

---

## 13. DBMS Demonstration (Course Alignment)

Because this is a DBMS course, these items must be visible in the report and demo.

| Topic | What to show |
|---|---|
| Normalization | ER diagram, normal form for each table, and the reasoning behind any denormalization (`opportunity`) |
| Constraints | PK / FK / CHECK / UNIQUE examples and what they prevent |
| Indexing | `EXPLAIN ANALYZE` for metadata filters with and without B-tree indexes |
| Vector search | Exact scan versus HNSW (and optionally IVFFlat): latency and recall tradeoff |
| Hybrid query | One SQL statement combining a year filter with vector similarity |
| Materialized views | Combination counts, refresh strategy, speedup over computing on the fly |
| Graph vs relational | Multi-hop citation traversal: recursive CTE in SQL versus Cypher, with timings |
| Consistency | Idempotent PostgreSQL → Neo4j sync and the count-verification check |
| Transactions | Batch ingestion inside transactions, with rollback on failure |

---

## 14. UI and API

### 14.1 Screens

1. **Search:** research idea input; results show title, authors, year, similarity, methods, datasets, topics.
2. **Paper Explorer:** details, authors, topics, methods, datasets, citations, related papers.
3. **Research Graph:** interactive graph of papers, authors, methods, datasets, tasks, topics, citations.
4. **Landscape:** clusters, topic distribution, temporal evolution, bridge papers.
5. **Opportunity Dashboard:** ranked list with per-signal values and confidence.
6. **Opportunity Detail:** signals, evidence chain, supporting and nearest-existing papers, "Why?" explanation, RAG chat.

Always show on screen: corpus size, date range, extraction confidence, and the statement that results are candidates for human review.

Stretch: weight sliders that re-rank live, and useful / not-useful feedback buttons.

### 14.2 Backend API (FastAPI suggested)

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

---

## 15. Demo Plan

Use one polished query and one backup query.

**Primary query:** "knowledge distillation for low-resource Kannada machine translation."

```text
1.  Enter research idea
2.  Semantic retrieval (hybrid: filter + vector)
3.  Show top papers
4.  Open a paper
5.  Show graph relationships
6.  Show research clusters
7.  Show weak connection
8.  Show candidate opportunity with per-signal scores and confidence
9.  Click "Why?"
10. Show evidence chain, including nearest existing work
11. Ask the RAG agent for an explanation (citations verified)
12. Show the evaluation slide: temporal holdout and baseline comparison
```

The point to make: this is more than search → paper list.

---

## 16. Team Division and Timeline

**Moved to `build-plan.md`**, which is the single source of truth for ownership, phases, and timeline. An earlier version of this section (roles A/B/C and a 10-week plan) was replaced by the current split:

- **Person 1:** data and extraction, then UI
- **Person 2:** database and retrieval, then evidence and RAG
- **Person 3:** graph and analysis, then scoring and API

The plan runs about 8 weeks with agent-assisted coding (stretch to 10 if needed). Working rules, interfaces between people, and the feature test are in `build-plan.md`, `AGENTS.md`, and `project-context.md`.

---

## 17. Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| Extraction quality | Drives every downstream count and score | Annotated source if available; closed vocabulary; provenance; hand-labeled accuracy check; review queue |
| Dataset missing from abstracts | Undercounts intersections and creates false sparsity | Start with method × task; report coverage per entity type; mention full-text extraction as future work |
| Sparsity is a weak signal | Rare can mean nonsensical, thin corpus, or missed extraction | Observed vs expected; confidence; support thresholds; semantic filter; show nearest existing work |
| Combinatorial explosion | Triples over many entities are unmanageable | Pairs first; query-neighborhood candidates; support threshold |
| Soft validation | No ground truth for "research gaps" | Temporal holdout; baselines; expert rating; no "gap accuracy" claim |
| Scope vs team size (3 people) | Many layers | Locked scope (Section 3); cut list; thin end-to-end first |
| DBMS content gets buried by ML work | Course grading looks for database concepts | Section 13 benchmarks scheduled in Phase 4 |
| Postgres / Neo4j drift | Inconsistent results | Idempotent batch sync and count verification |
| LLM hallucination | Unsupported claims | Structured evidence first; citation verification; terminology rules |
| Corpus bias or incompleteness | Misleading "underexplored" labels | Display corpus limits in the UI and report |

---

## 18. Decision Log

**Moved to `decisions-and-progress.md`**, which holds the live open-decisions list, the decision log, and per-person progress. It is kept there so there is one copy to update.

---

## 19. Glossary

| Term | Meaning |
|---|---|
| Research element | A method, task, dataset, topic, or setting |
| Experiment | A row linking a paper to a method, dataset, task, and setting that were used together |
| Combination | A set of two or more research elements (pairs first) |
| Observed count | Number of distinct papers containing the combination |
| Expected count | Papers expected to contain it if elements were independent: `n_A * n_B / N` |
| Lift | Observed / expected |
| Bridge | A paper, author, method, dataset, or topic connecting two clusters |
| Candidate opportunity | A weakly represented combination ranked by the score; a signal for human review |
| Evidence chain | Structured trail from a candidate to the supporting papers and counts |
| Nearest existing work | The closest paper already combining some of the candidate's elements |
| Temporal holdout | Evaluating by building the corpus up to year Y and checking later years |

---

## 20. Final Quick Reference

**Title:** Research Paper Discovery and Exploration System

**Core stack:** PostgreSQL + pgvector + Neo4j + embedding model + RAG + frontend

**Core elements:** Paper, Author, Institution, Venue, Topic, Method, Task, Dataset, Setting, Experiment, Result, Citation

**Core output:** Relevant papers + research landscape + candidate opportunities + opportunity score with confidence + evidence chain + RAG explanation

**Strongest contribution:** Detect potentially underexplored combinations of research elements and explain the evidence behind them.

**Critical caveat:** A candidate opportunity is a signal for further investigation, not proof of a research gap.
