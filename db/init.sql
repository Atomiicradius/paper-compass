-- Loaded verbatim from context/data-and-contracts.md section 1. Do not edit here; change the contract first.

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
