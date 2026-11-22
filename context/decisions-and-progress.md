# decisions-and-progress.md

Edit only your own section under "Progress" to avoid merge conflicts. Decisions are append-only: add a row, don't rewrite old ones.

## Open decisions (ask before assuming)

| # | Decision | Needed by | Owner | Notes |
|---|---|---|---|---|
| O1 | Domain: NLP / machine translation, ~5-10k papers | Week 1 meeting | All | Locked: NLP / Machine Translation (low-resource / Indic / Kannada MT) |
| O2 | Corpus source: OpenAlex API | After 500-paper pilot | Person 1 | Locked: OpenAlex API selected for papers/citations; the vocabulary is curated manually in ingest/create_vocabulary.py |
| O3 | Embedding model: SPECTER2 vs Sentence Transformer for prototype | Before loading data | Person 2 | Confirmed by Person 1 on 2026-11-04: SPECTER2 (allenai/specter2_base + allenai/specter2 proximity adapter), 768-dim, no schema change |
| O4 | UI stack | Week 3-4 | UI owner | Do not scaffold before this is decided |
| O5 | LLM / RAG client and model | Phase 3 | RAG owner | |
| O6 | Score weights, `min_support`, confidence constant `k` | Phase 3 | Scoring owner | Tune on real data; keep a sensitivity check |
| O7 | Extraction method: rules-v1 with sentence co-occurrence and strict acronym boundaries (`\b[A-Z]{2,3}\b`); confidence cutoff 0.70 | After first pass | Person 1 | Locked: rules-v1 with 0.70 confidence threshold calibrated on 100-abstract benchmark |
| O8 | Clustering method (default: HDBSCAN on embeddings) | Phase 3 | Graph owner | |
| O9 | Name assignment for Person 1 / 2 / 3 | Week 1 meeting | All | |
| O10 | API request and response schemas for each endpoint | Phase 2 | Person 3 + UI owner | Add to `data-and-contracts.md` once agreed |

## Decision log

| # | Date | Decision | Reason | Status |
|---|---|---|---|---|
| 1 | 2026-10-30 | Add EXPERIMENT entity; combination counts use experiments | "Used together" instead of "co-occurs" | Locked |
| 2 | 2026-10-30 | RESULT links to EXPERIMENT | Metrics belong to a method-dataset pair | Locked |
| 3 | 2026-10-30 | Alias tables and closed vocabulary | Entity normalization | Locked |
| 4 | 2026-10-30 | Extraction provenance on every extracted link | Measurable errors; UI evidence | Locked |
| 5 | 2026-10-30 | Add SETTING and INSTITUTION tables, author order, composite PKs | Schema completeness | Locked |
| 6 | 2026-10-30 | Sparsity uses observed vs expected, with confidence | Raw counts are misleading | Locked |
| 7 | 2026-10-30 | All signals normalized to [0, 1]; per-signal values shown; sensitivity check | Transparent scoring | Locked |
| 8 | 2026-10-30 | Start with three signals; add two only if they change the ranking | Reduce risk | Locked |
| 9 | 2026-10-30 | Pairs first; triples are stretch | Scope, explosion | Locked |
| 10 | 2026-10-30 | Temporal holdout plus baselines are the primary evaluation | Strongest label-free test | Locked |
| 11 | 2026-10-30 | DBMS benchmarks required | Course alignment | Locked |
| 12 | 2026-10-30 | Evidence as structured JSON first; RAG phrases it; citations verified | Grounding | Locked |
| 13 | 2026-10-30 | Nearest-existing-work section on every opportunity | Guards against false gaps | Locked |
| 14 | 2026-10-30 | Neo4j is a derived projection with idempotent batch sync | Consistency | Locked |
| 15 | 2026-10-30 | Context files kept to five plus `docs/reference/` (all inside `context/`); add more only when decisions settle | Avoid stale specs | Locked |
| 16 | 2026-10-30 | Same-universe rule for expected counts; subset count views and `mv_universe_size` added | Mixed universes inflate expected counts and create false sparsity | Locked |
| 17 | 2026-10-30 | `experiment` uniqueness uses `NULLS NOT DISTINCT`; PostgreSQL 15+ required | Prevent duplicate extractions with missing fields | Locked |
| 18 | 2026-10-30 | Values outside the controlled vocabulary go to a review queue, never create entities | Keep the vocabulary controlled | Locked |
| 19 | 2026-10-30 | Postgres container is built from `db/Dockerfile` (`postgres:16` pinned by digest, plus apt `postgresql-16-pgvector` pinned) instead of the `pgvector/pgvector` image, because that image fails with `exec format error` on Person 2's Docker setup; one identical image for everyone | Reproducible environment | Confirmed by Person 3 on 2026-11-01: built from db/Dockerfile with docker compose up -d --build, first time OK, 66 integration tests pass against it, init.sql identical to the contract |
| 20 | 2026-10-31 | Embedding model is SPECTER2 with the proximity adapter; `vector(768)` unchanged | Runs on CPU at about 0.13 s per paper, 768-dim output matches the schema; see `db/experiments/embeddings/results.md` | Confirmed by Person 1 on 2026-11-04 |
| 21 | 2026-11-01 | Postgres and Neo4j host ports are configurable via db/.env (POSTGRES_PORT, NEO4J_HTTP_PORT, NEO4J_BOLT_PORT), defaults unchanged | A local PostgreSQL service can own 5432 | Locked |
| 22 | 2026-11-01 | Clusters stay in `graph/out/clusters.json`; no schema change | Agreed by Persons 2 and 3; revisit if the UI needs to query clusters in SQL | Locked |
| 23 | 2026-11-01 | Python 3.12 and psycopg 3.3.6 for everyone; two lockfiles: core root `requirements.txt` plus add-on `requirements-embeddings.txt` (torch, transformers 4.57.6, adapters) | One environment that also runs the embeddings; keeps torch out of the test environment | Agreed by Persons 2 and 3 |
| 24 | 2026-11-04 | Person 1 accepts paper metadata format (`db/proposals/paper-metadata-format.md`) and vocabulary format (`db/proposals/vocabulary-format.md`) | Unlocks ingestion and vocabulary pipelines | Locked |
| 25 | 2026-11-04 | Primary corpus source is OpenAlex API | Aligns with schema (`W...` work IDs, `A...` author IDs, references, free high-rate API) | Locked |
| 26 | 2026-11-11 | Multi-stream concept query ingestion across NLP/MT domains | Diversifies corpus to 2,000 papers, boosting internal citation density from 7.4% to 14.88% (11,681 internal edges) | Locked |
| 27 | 2026-11-11 | Task taxonomy consolidation: single canonical `Machine Translation` task | Eliminates overlapping label noise across NMT, MT, and low-resource MT; settings capture resource constraints | Locked |
| 28 | 2026-11-11 | Rule-generated reference set (preliminary; not human-labeled) from 100 papers sampled with seed=42, replacing the earlier first-100 reference set | Made by `extraction/create_reference_set_v2.py` with a conservative and an inclusive rule set, no human labeling; 86 of 100 sampled papers had identical labels under both rule sets (not an inter-annotator agreement); 79 rows from 60 papers, 40 sampled papers produced no row; method labels share the extractor's vocabulary and regex style, so method precision/recall (100%) is circular and not an accuracy measurement | Locked |
| 29 | 2026-11-11 | Strict case-sensitive uppercase boundaries (`\b[A-Z]{2,3}\b`) for short acronyms | Eliminates false lowercase dictionary word matches (e.g. POS, MT, SMT) | Locked |
| 30 | 2026-11-11 | Prioritize Method × Task and Method × Setting combination discovery | Empirically verified dataset sparsity in paper abstracts (only 3.8% name explicit datasets); the `method × setting` views it relies on are awaiting Person 2 and Person 3 review | Proposed |
| 31 | 2026-11-22 | UI stack (O4): Streamlit, in `ui/`, calling the FastAPI backend over HTTP only (never the databases) | Same language as the rest of the code, Person 2's demo already used it; all six screens built and checked on pc_pilot (`ui/README.md`) | Decided by Person 3 (UI-stack task); team to confirm |
| 32 | 2026-11-22 | Scoring on pc_pilot (O6): keep `v1-three-signal` weights; `min_support` 5; new `min_sparsity` 0.3; `k` 5; no semantic filter | Temporal holdout over cutoffs 2020-2023: v1 beats random and sparsity-only under both hit definitions; the grid "best" flips between definitions and rests on 1-10 hits per cutoff; see `scoring/tuning-pc_pilot.md` | Locked for pc_pilot; revisit on a larger corpus |
| 33 | 2026-11-22 | Clustering (O8): HDBSCAN after PCA to 20 dimensions, `min_cluster_size` 15, `min_samples` 5 | 768-dim HDBSCAN gave 2 clusters and 46-55% noise on pc_pilot; this gives 7 clusters and 44% noise (`graph/README.md`) | Locked for pc_pilot |
| 34 | 2026-11-22 | API shapes (O10) written out from runs on pc_pilot in `api/api-shapes-o10.md`, with 3 questions | Needs Persons 1 and 2 to confirm before copying into `data-and-contracts.md` | Proposed |

## Progress

Update after each task: what's done, what's next, blockers.

### Person 1: Data and extraction (then UI)
- Status: Phase 1 complete (Data, Vocabulary, Extraction, rule-generated reference set (preliminary; not a human-labeled benchmark), and Evaluation Report done); the corpus was scaled to 2,000 papers.
- Done:
  1. Accepted Person 2's paper metadata and vocabulary format proposals. Confirmed O3 (SPECTER2).
  2. Selected OpenAlex API as primary corpus source. Built multi-stream ingestion (`ingest/fetch_openalex.py`, five concept streams plus the seed query) and scaled the corpus to 2,000 papers in `ingest/data/papers_pilot.jsonl` (10,679 authors, 78,513 citation references; 11,681 of them, 14.88%, point to a paper inside the file, up from 7.4% for the first 500 papers).
  3. Consolidated the task taxonomy in `ingest/create_vocabulary.py` (single canonical `Machine Translation` task; resource constraints go to `SETTING`). Provenance in `ingest/vocabulary_provenance.md`. `ingest/data/vocabulary.jsonl` has 125 entries (54 methods, 41 datasets, 18 tasks, 12 settings).
  4. Built the extraction pipeline `extraction/extract.py` (sentence segmentation, entity linking against canonical names and aliases, case-sensitive matching for short uppercase aliases, confidence threshold 0.70, deterministic output). Output: `extraction/data/extractions_pilot.jsonl`.
  5. Built a rule-generated reference set (preliminary; not human-labeled) from 100 sampled papers (seed 42) in `extraction/data/labeled_benchmark.jsonl`, using `extraction/create_reference_set_v2.py`.
  6. Computed coverage, and precision, recall and F1 against the rule-generated reference set (these compare two rule-based systems and are not accuracy measurements), via `extraction/evaluate.py`. Findings and limitations in `extraction/accuracy_report.md`.
  7. Checked data integrity with `ingest/test_pilot_integrity.py` (this script's own checks; it does not call the loaders).
  8. Wrote `db/proposals/method-setting-views.md` (proposed, not yet agreed by Person 2 and Person 3).
- Open item (not a decision): the corpus has one duplicate paper under two OpenAlex IDs, W1522301498 (rejected by the loader) and W2964121744 (kept; 0 references, no affiliations): Kingma & Ba, "Adam", arXiv 1412.6980. Follow-up for Person 1: de-duplicate by DOI at ingest, keep the record with more references and fuller authorships (here W1522301498), remap citations from the dropped ID to the kept ID, and check other near-duplicate titles with different DOIs (for example three copies of "Survey of low-resource machine translation"). Details in `extraction/accuracy_report.md` (Limitations).
- Next: Phase 2 (UI Preparation): Wireframe/mocks for Person 3, agree on API endpoint schemas (O10), and select UI stack (O4). Do not scaffold UI code until stack is locked.

### Person 2: Database and retrieval (then evidence and RAG)
- Status: week-1 foundation done (branch `db/foundation`).
- Done: schema and containers (Postgres 16.15 + pgvector 0.8.7, Neo4j 5.26.32; schema from the contracts loaded verbatim via `db/init.sql`); 76 tests passing; loader (vocabulary, papers, extractions, refresh, load-all) done and run on the mock data in `db/mock/`; proposals for the paper metadata and vocabulary formats written in `db/proposals/`, awaiting Person 1's confirmation.
- Done (embeddings): SPECTER2 measured on CPU (about 0.13 s per paper, 768-dim; `db/experiments/embeddings/results.md`); embedding pipeline `embed-papers` in `db/embeddings/` built with tests (stub encoder, plus one `slow` real-model test) and run on the mock papers.
- Confirmed: decision #19 (Postgres built from `db/Dockerfile`), by Person 3 on 2026-11-01. Proposed, awaiting teammates: O3 / decision #20 (SPECTER2 with the proximity adapter, `vector(768)` unchanged). Real papers are not embedded until O3 is confirmed.
- Done (retrieval): SQL search layer in `db/retrieval/` with tests: vector search (year, venue, method/dataset/task filters with aliases, offset, exclusions, optional entity names) using pgvector iterative index scans for selective filters, and a full-text keyword baseline. Entity filters by default need one experiment to satisfy all of them (`match="same_experiment"`; `match="any"` allows different experiments). No API (Person 3 owns it). Tested on synthetic vectors only; no real embeddings exist yet.
- Done (ports): host ports are configurable in `db/.env` (decision #21) because a local PostgreSQL service can own 5432; the loaders, embedding and search commands and the tests all read `POSTGRES_PORT`. Defaults are unchanged. 196 tests pass in the embeddings environment (185 passed and 11 skipped in the root environment, where the embeddings tools are not installed).
- Done (evaluation): retrieval metrics (precision@K, recall@K, MRR, nDCG@K with graded relevance) and a runner that scores precomputed ranking files, in `db/retrieval/evaluation/` with hand-computed tests; no database or model involved. Query-set format written as a proposal (`db/proposals/retrieval-eval-format.md`), awaiting the team.
- Done (evidence, branch `rag/evidence`): `rag/` has `nearest_existing` (exact papers first, then close ones by embedding similarity; the signature agreed with Person 3), `build_evidence` and `build_evidence_ids` (counts over the same universe and cutoff year, yearly series, roles supports_A / supports_B / bridge / nearest_existing with source sentences), `[paper:ID]` citation markers with `verify_citations`, and a deterministic template summary (`summarize_evidence`, no LLM). Tested on synthetic data against hand counts, raw SQL, the materialized views and brute-force Python; mutation checks done; smoke-tested read-only on the mock data. Format written as a proposal (`db/proposals/evidence-chain-format.md`) with open questions for Person 3 and the UI owner (O10). The LLM client (O5) is not chosen and not implemented.
- Next: embedding the real corpus once O3 is confirmed, labelling 15-20 queries, and the keyword-vs-vector evaluation. The query encoder (`specter2_adhoc_query` adapter vs the proximity adapter) is not implemented; it will be compared on the labelled query set once real papers exist. Person 3 can switch his scoring to `rag.nearest.nearest_existing` and `build_evidence_ids` once the proposal is agreed.
- Notes: Neo4j credentials are in the local `db/.env` (not committed); share them with Person 3 outside git.

### Person 3: Graph and analysis (then scoring and API)
- Status: first version of `graph/`, `scoring/`, `api/` built and tested (2026-10-30). No real data loaded yet.
- Done:
  - `graph/`: Neo4j constraints, idempotent MERGE sync with mark-and-sweep, count verification, Cypher queries (graph screen, method bridges, multi-hop citations plus the recursive-CTE equivalent), trends, HDBSCAN clusters (written to `graph/out/clusters.json`), bridge papers, weakly connected cluster pairs.
  - `scoring/`: same-universe pair counts (views, cutoff query, Python), candidates, normalized signals, v1/v2 weights, ranking, sensitivity check, temporal holdout with random / sparsity-only / semantic-only baselines, DB pipeline writing `opportunity` and `opportunity_evidence` in one transaction.
  - `api/`: FastAPI endpoints for opportunities, papers, paper graph, trends, clusters and landscape. The opportunity response matches the contract. `PC_API_MOCK=1` serves clearly marked mock data for UI work.
  - Tests: 55 passing, including integration tests on PostgreSQL 16 + pgvector and Neo4j 5.26. Views were checked against raw counts, and the sync was shown to be idempotent and to remove deleted rows.
- Choices within my modules (tell me if you disagree):
  - Sparsity = `1 - (obs+1)/(exp+1)`, clipped to [0, 1], fixed for the evaluation.
  - Pairs with expected < 1 are dropped.
  - Semantic compatibility and temporal activity are percentile-ranked across the candidate set.
  - `nearest_existing` uses papers that already have both elements; otherwise, A papers closest to B's centroid. This is interim until Person 2's lookup exists.
- Next: run on the 500-paper pilot once Person 2's DDL and loader exist; tune O6 on real data; temporal holdout run.
- Needs the team:
  - O10: agree response shapes with the UI owner. Everything except the opportunity object is provisional in `api/schemas.py`.
  - `/rag/query` returns 501 until O5 (LLM client) is decided.
  - `/search` takes optional filter fields and a `mode` on top of the contract body (see `api/README.md`). Provisional under O10; I will copy the final shape into `data-and-contracts.md` once agreed.
- Update (2026-11-01): `/search` and `/papers/{id}/related` built on Person 2's `db/retrieval` (branch `person3` merges `db/embeddings`).
  - The query encoder is Person 2's SPECTER2 proximity encoder until their adapter comparison. Vector search refuses paper embeddings from another model; in `auto` mode it falls back to keyword search and says why.
  - Tests: 66 passing with no skips, against Person 2's Postgres image and Neo4j 5.26.32. Person 2's `init.sql` is identical to the contract DDL my tests use.
  - Python 3.12 + psycopg 3.3.6 (decision 23): 66 tests pass with no skips on Python 3.12.16, run in a `python:3.12-slim` container against Person 2's Postgres image and Neo4j. `requirements-person3.txt` updated.
  - Interim `nearest_existing` in `scoring/` will be replaced by Person 2's read-only `rag.nearest_existing(conn, element_a, element_b, cutoff_year, limit)`, called inside the scoring transaction.
- Update (2026-11-01): on Person 2's `rag/` (branch `person3` merges main with PR #1 and #2).
  - `scoring.pipeline` writes `opportunity_evidence` from `rag.evidence.build_evidence_ids`; my interim lookup is gone. Two visible changes: `nearest_existing` now fills up to 5 with close papers after the exact ones, and `bridge` only counts citations between the A-only and B-only papers.
  - `POST /opportunities/{id}/explain` returns `{opportunity_id, evidence, summary, citation_check, disclaimer}` from `build_evidence`, `summarize_evidence` and `verify_citations` (shape provisional under O10). 422 if the opportunity is not exactly one method/dataset/task pair. `/rag/query` stays 501 until O5 (LLM client).
  - An integration test checks that the stored observed/expected equal `build_evidence(...)["corpus"]` on the same data.
  - Tests: 425 passed, 10 skipped (dotenv-only tests) across api, graph, scoring, rag and db/tests on Python 3.12, against the compose Postgres and Neo4j.
- Update (2026-11-22): first run on the real pilot data (`pc_pilot` dump of 2026-11-21: 1,999 papers, 1,055 experiments, 1,999 embeddings).
  - Neo4j synced from pc_pilot: 12,864 nodes, 34,796 relationships; all 26 counts match PostgreSQL; a second run is unchanged.
  - Scoring (O6, decision 32): `scoring/tune.py` (temporal holdout over a weight grid, two hit definitions) and `scoring/tuning-pc_pilot.md`. 13 Method × Task opportunities stored with 252 evidence rows; #1 checked against raw SQL. New `min_sparsity` in candidates and `--replace` in the pipeline (re-runs no longer duplicate rows).
  - Clusters (O8, decision 33): PCA option in `graph/clusters.py`; 7 clusters on pc_pilot.
  - API (O10, decision 34): every endpoint checked on pc_pilot, shapes and 3 questions in `api/api-shapes-o10.md`. A Neo4j error on `/papers/{id}/graph` is now a 503 with a reason instead of a 500.
  - UI (O4, decision 31): Streamlit, six screens, in `ui/`; vector search with SPECTER2 works and its top 3 equal the pilot report's.
  - Tests: 357 passed and 5 skipped (Neo4j sync tests and dotenv-only tests, skipped so the test sweep would not wipe the pc_pilot graph) in api, graph, scoring and rag against a scratch database `pc_test`; plus 10 UI tests.
  - For Person 1: (a) the corpus Method × Task universe is 399 papers, 338 of them Machine Translation, so most expected counts are driven by MT; (b) "Masked Language Model Scoring" (W3024308166) is not tagged with Masked Language Modeling though its abstract says "masked language models (MLMs)"; plural forms may be missing from the aliases.
- Blockers: none. Pinned deps are in `requirements-person3.txt`.
