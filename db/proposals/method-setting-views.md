# Proposal: Method × Setting Materialized Views and Combination Scoring Contract

**Author:** Person 1 (Data and Extraction)  
**Date:** 2026-11-19  
**Status:** Proposed (for Person 2 & Person 3 confirmation)  
**Related Decisions:** Decisions #1, #6, #16, #28 in `context/decisions-and-progress.md`  
**Affects:** `context/data-and-contracts.md`, `db/init.sql`, Person 2 materialized views & refresh tasks, Person 3 combination candidate generation

---

## 1. Problem Statement & Motivation

During Phase 1 pilot extraction across 2,000 academic papers (1,054 experiment tuples), empirical analysis revealed a severe imbalance in entity reporting in academic abstracts:
- **`method`**: Extracted in 100% of experiment tuples (1,054 / 1,054).
- **`task`**: Extracted in 68.1% of experiment tuples (718 / 1,054).
- **`setting`**: Extracted in 69.0% of experiment tuples (727 / 1,054) across 10+ diverse settings (`Low-resource`, `Multilingual`, `Zero-shot`, `Supervised`, `Cross-lingual`, `Unsupervised`, etc.).
- **`dataset`**: Explicitly named in only **3.8% of experiment tuples (40 / 1,054 across 32 distinct papers, 17 distinct datasets)**.

### Why This Matters for Downstream Modules
In academic NLP literature, abstracts almost never name the specific benchmark dataset (e.g., authors write *"evaluated on five low-resource African languages in a zero-shot cross-lingual setting"* rather than *"evaluated on FLORES-200"*).

Under the **Same-Universe Rule** (contract §1.1), `method × dataset` expected counts are restricted strictly to papers naming a dataset ($N \approx 32$). With $N=32$, any combination pair has insufficient statistical power, yielding high variance and artificial sparsity. In contrast, `setting` is populated in 727 experiments across hundreds of papers, providing rich signal for research opportunity discovery (e.g., *Has Adapter Tuning been applied in Low-resource settings?* or *Has Minimum Risk Training been tested in Multilingual settings?*).

---

## 2. Proposed Contract Addition: `method × setting` Materialized Views

We propose adding `method × setting` combination tracking alongside `method × dataset` and `method × task`.

### 2.1 Universe Definition
- **Pair Type:** `method_setting`
- **Universe Filter:** `experiment.setting_id IS NOT NULL`
- **Total $N$:** Distinct `paper_id` in experiments where `setting_id IS NOT NULL` (727 experiments, 411 papers).

### 2.2 Schema Additions (for `db/init.sql` / Materialized Views)

```sql
-- 1. Setting individual frequency
CREATE MATERIALIZED VIEW mv_setting_count AS
SELECT setting_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE setting_id IS NOT NULL GROUP BY setting_id;

-- 2. Method x Setting pair frequency (observed count)
CREATE MATERIALIZED VIEW mv_method_setting AS
SELECT method_id, setting_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE setting_id IS NOT NULL
GROUP BY method_id, setting_id;

-- 3. Method count within the Method x Setting universe (n_A for expected count)
CREATE MATERIALIZED VIEW mv_method_count_ms AS
SELECT method_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE setting_id IS NOT NULL GROUP BY method_id;

-- 4. Setting count within the Method x Setting universe (n_B for expected count)
-- Note: identical to mv_setting_count, defined for naming consistency with contract §1.1
CREATE MATERIALIZED VIEW mv_setting_count_ms AS
SELECT setting_id, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE setting_id IS NOT NULL GROUP BY setting_id;
```

### 2.3 Updated `mv_universe_size`

Update the `mv_universe_size` definition in `context/data-and-contracts.md` to include `'method_setting'`:

```sql
CREATE MATERIALIZED VIEW mv_universe_size AS
SELECT 'method_dataset' AS pair_type, COUNT(DISTINCT paper_id) AS n_papers
FROM experiment WHERE dataset_id IS NOT NULL
UNION ALL
SELECT 'method_task', COUNT(DISTINCT paper_id)
FROM experiment WHERE task_id IS NOT NULL
UNION ALL
SELECT 'method_setting', COUNT(DISTINCT paper_id)
FROM experiment WHERE setting_id IS NOT NULL
UNION ALL
SELECT 'dataset_task', COUNT(DISTINCT paper_id)
FROM experiment WHERE dataset_id IS NOT NULL AND task_id IS NOT NULL;
```

### 2.4 Refresh Indexes

```sql
CREATE UNIQUE INDEX ON mv_setting_count (setting_id);
CREATE UNIQUE INDEX ON mv_method_setting (method_id, setting_id);
CREATE UNIQUE INDEX ON mv_method_count_ms (method_id);
CREATE UNIQUE INDEX ON mv_setting_count_ms (setting_id);
```

---

## 3. Impact on Person 2 & Person 3

1. **Person 2 (Database & Loaders):**
   - In `db/init.sql`, add the 4 materialized views and unique indexes.
   - In `db/loaders/load_all.py` / refresh routine, include the new views in `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
   - Loader logic for `experiment` is completely unaffected (`setting_id` was already part of the schema).

2. **Person 3 (Scoring & Analysis):**
   - Combination discovery can now generate candidate pairs of `(method, setting)` in addition to `(method, task)` and `(method, dataset)`.
   - Expected count formula for a `(method, setting)` pair $(m, s)$:
     $$\mathbb{E}[N_{m, s}] = \frac{n_m \cdot n_s}{N_{\text{method\_setting}}}$$
     where:
     - $n_m$ is from `mv_method_count_ms`
     - $n_s$ is from `mv_setting_count_ms`
     - $N_{\text{method\_setting}}$ is from `mv_universe_size` where `pair_type = 'method_setting'`.
   - Sparsity score formula applies identically:
     $$\text{sparsity}(m, s) = 1 - \frac{\text{observed} + 1}{\text{expected} + 1}$$

3. **Person 1 (Extraction & UI):**
   - UI candidate view can present `Method × Setting` cards (e.g. *"Low-Rank Adaptation (LoRA) × Low-resource"*, *"FlashAttention × Multilingual"*).

---

## 4. Verification & Confirmation Checklist

- [ ] **Person 2:** Confirm materialized view DDL compatibility with Docker PostgreSQL 16 container and refresh script.
- [ ] **Person 3:** Confirm candidate scoring query integration for `method_setting` pairs.
