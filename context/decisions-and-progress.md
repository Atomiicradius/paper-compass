# decisions-and-progress.md

Edit only your own section under "Progress" to avoid merge conflicts. Decisions are append-only: add a row, don't rewrite old ones.

## Open decisions (ask before assuming)

| # | Decision | Needed by | Owner | Notes |
|---|---|---|---|---|
| O1 | Domain: NLP / machine translation, ~5-10k papers | Week 1 meeting | All | Locked: NLP / Machine Translation (low-resource / Indic / Kannada MT) |
| O2 | Corpus source: OpenAlex API | After 500-paper pilot | Person 1 | Locked: OpenAlex API selected for papers/citations; the vocabulary is curated manually in ingest/create_vocabulary.py |
| O3 | Embedding model: SPECTER2 vs Sentence Transformer for prototype | Before loading data | Person 2 | Confirmed by Person 1 on 2026-11-04: SPECTER2 (allenai/specter2_base + allenai/specter2 proximity adapter), 768-dim, no schema change |
| O4 | UI stack | Week 3-4 | UI owner | Decided: React + Vite + TypeScript + Tailwind in `ui/` (decision 35). Team to confirm |
| O5 | LLM / RAG client and model | Phase 3 | RAG owner | Settled in practice as **optional, off by default, not yet shown live**: `rag/llm_summary.py` can phrase the explanation (Gemini or Anthropic SDK) and falls back to the template on any problem, but every real Gemini call so far timed out, so no real model answer has passed its guardrails (`rag/llm-summary.md`). `/rag/query` is still 501 |
| O6 | Score weights, `min_support`, confidence constant `k` | Phase 3 | Scoring owner | Set for pc_pilot (decision 32): v1 weights, `min_support` 5, `min_sparsity` 0.3, `k` 5. Re-run `scoring.tune` if the corpus grows |
| O7 | Extraction method: rules-v1 with sentence co-occurrence and strict acronym boundaries (`\b[A-Z]{2,3}\b`); confidence cutoff 0.70 | After first pass | Person 1 | Locked: rules-v1 with 0.70 confidence threshold calibrated on 100-abstract benchmark |
| O8 | Clustering method (default: HDBSCAN on embeddings) | Phase 3 | Graph owner | HDBSCAN after PCA to 20 dimensions (decision 33) |
| O9 | Name assignment for Person 1 / 2 / 3 | Week 1 meeting | All | |
| O10 | API request and response schemas for each endpoint | Phase 2 | Person 3 + UI owner | Proposed in `api/api-shapes-o10.md` (decision 34) with 3 open questions; copy into `data-and-contracts.md` once agreed |

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
| 31 | 2026-11-22 | UI stack (O4): first choice, superseded by decision 35 | Replaced once the richer UI was built | Superseded |
| 32 | 2026-11-22 | Scoring on pc_pilot (O6): keep `v1-three-signal` weights; `min_support` 5; new `min_sparsity` 0.3; `k` 5; no semantic filter | Temporal holdout over cutoffs 2020-2023: v1 beats random and sparsity-only under both hit definitions; the grid "best" flips between definitions and rests on 1-10 hits per cutoff; see `scoring/tuning-pc_pilot.md` | Locked for pc_pilot; revisit on a larger corpus |
| 33 | 2026-11-22 | Clustering (O8): HDBSCAN after PCA to 20 dimensions, `min_cluster_size` 15, `min_samples` 5 | 768-dim HDBSCAN gave 2 clusters and 46-55% noise on pc_pilot; this gives 7 clusters and 44% noise (`graph/README.md`) | Locked for pc_pilot |
| 34 | 2026-11-22 | API shapes (O10) written out from runs on pc_pilot in `api/api-shapes-o10.md`, with 3 questions | Needs Persons 1 and 2 to confirm before copying into `data-and-contracts.md` | Proposed |
| 35 | 2026-11-22 | UI stack revised (O4): React + Vite + TypeScript + Tailwind, Radix-based components, motion and react-force-graph-2d, in `ui/`; supersedes decision 31. HTTP to the API only; dev server proxies `/api` so the API needs no CORS settings | Richer interaction than the first UI could give: three panes, a slide-over evidence drawer with verified citations, an interactive graph. Built and checked on pc_pilot run on the real data | Proposed; team to confirm |
| 36 | 2026-11-22 | Search: the API encodes queries with the `adhoc_query` adapter (Person 2's `make_query_encoder`) and checks stored embeddings against the paper-side model string; optional `hybrid` mode (reciprocal rank fusion, year filters only, a method/dataset/task/venue filter is a 422), never chosen by `auto`; keyword search stays the all-words baseline and says so when it finds nothing | The old API used the paper (proximity) adapter for queries and had no hybrid mode; both of Person 2's options were unused by the API | Locked (api module) |
| 37 | 2026-11-22 | `GET /health`; `python -m api.prepare_demo` (opportunities, clusters, Neo4j from a restored dump); `/clusters` computes itself on first use; trend slope in exact arithmetic and `math.fsum` in the cosine, so results do not depend on the Python version | A fresh machine showed empty opportunities and a 503 on `/clusters`; the same code gave different temporal values on Python 3.11 and 3.12 (`scoring/tuning-pc_pilot.md` section 6) | Locked (api, graph, scoring modules) |
| 38 | 2026-11-22 | Ingestion Deduplication (Items 1 & 2): merge shared DOIs and repeated titles with close years/authors | Merged 25 duplicate records (including Adam arXiv duplicate and 3 copies of Low-Resource MT Survey); remapped 179 citations; clean corpus has 1,975 papers | Locked |
| 39 | 2026-11-22 | Corpus Direction (Item 3): keep Low-Resource MT as the anchor domain; enriching Speech Translation and Quality Estimation is **proposed, not done** | The retrieval diagnosis (`db/retrieval-diagnosis.md`) found few papers for these two topics. No enrichment has been run: this branch contains no paper that `origin/main` did not already have (0 added, 25 duplicates dropped), and a keyword search of titles and abstracts finds 7 papers on speech translation both before and after, and 8 on quality estimation before and 7 after deduplication. Still needed: choose the OpenAlex queries for the two topics, fetch, deduplicate, re-extract and re-embed | Proposed; not done |
| 40 | 2026-11-22 | Rule-based check set (Item 4): 50 abstracts labeled by two regex passes in `extraction/sample_and_label_50.py`. **Not hand-labeled and not independent ground truth** | Replaces the earlier 100-paper rule-generated set with a deterministic one on the deduplicated corpus. The two passes give the same labels for 44 of 50 papers (88.0%): an overlap of two rule sets, not an inter-annotator agreement (no kappa). Extractor figures against it compare two rule-based systems, not accuracy. A check labeled by people is still to do. Files: `extraction/data/rule_based_check_set_50.jsonl` and the two rule passes | Preliminary |
| 41 | 2026-11-22 | Short-Alias Cleanup (Item 6): Removed bare `APE` alias from `Automatic Post-Editing` | Eliminates false collision with 'Automatic Prompt Engineer (APE)'; all 23 remaining short acronyms verified with `\b[A-Z]{2,3}\b` | Locked |

## Progress

Update after each task: what's done, what's next, blockers.

### Person 1: Data and extraction (then UI)
- Status: deduplication (items 1 and 2), dataset coverage (item 5) and the short-alias audit (item 6) are done. Item 3 (enriching speech translation and quality estimation) is **not done**: no paper was added. Item 4 is a rule-based check set, not a hand-labeled benchmark.
- Done:
  1. Accepted Person 2's paper metadata and vocabulary format proposals. Confirmed O3 (SPECTER2).
  2. Selected OpenAlex API as primary corpus source. Built multi-stream ingestion (`ingest/fetch_openalex.py`) querying across concept streams and scaled the corpus.
  3. Implemented full de-duplication in `ingest/deduplicate.py` (Items 1 & 2): merged shared DOIs (e.g. Adam `W1522301498` into `W2964121744` with fuller references and affiliations) and 24 preprint/conference duplicate titles. Remapped 179 citations to kept IDs. Final deduplicated corpus has **1,975 clean papers** (10,566 authors, 78,188 citation references).
  4. Consolidated the task taxonomy in `ingest/create_vocabulary.py`. Removed bare `APE` alias to eliminate false prompt engineering hits (Item 6). Final vocabulary: 125 entries (54 methods, 41 datasets, 18 tasks, 12 settings). Full provenance documented in `ingest/vocabulary_provenance.md`.
  5. Improved dataset extraction in `extraction/extract.py` with abstract-level inheritance for unambiguous datasets (Item 5). The share of tuples that name a dataset went from 3.8% (40 of 1,055 tuples, earlier 2,000-paper corpus) to **10.1% (104 of 1,033 tuples**, from 63 of the 623 papers with extractions, on the 1,975-paper corpus). Different corpora, so not a like-for-like gain.
  6. Built a rule-based check set for 50 abstracts (seed 2026) with two regex passes and a combining rule (Item 4, `extraction/sample_and_label_50.py`). **No person labeled it, so it is not hand-labeled and not independent ground truth.** The two passes give the same labels for 44 of 50 papers (88.0%), which is not an inter-annotator agreement. The extractor compared with it gives Method recall 100%, Task precision 90.9%, Setting precision 75.0%, Dataset recall 100% (one true positive): these compare two rule-based systems and are not accuracy measurements. Saved to `extraction/data/rule_based_check_set_50.jsonl`. Still to do: a check labeled by people.
  7. Checked data integrity with `ingest/test_pilot_integrity.py`: 100% PASS across all vocabulary, paper, and extraction checks.
  8. Wrote `db/proposals/method-setting-views.md` (Decision #30 proposed, awaiting Person 2 and Person 3 review).
- Next: decide and run the corpus enrichment for speech translation and quality estimation (item 3); get 50 to 100 abstracts labeled by people (item 4); review Person 3's API shapes proposal (O10).

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
  - UI (O4, decision 35): six screens on the real data; vector search with SPECTER2 works and its top 3 equal the pilot report's.
  - Tests: 357 passed and 5 skipped (Neo4j sync tests and dotenv-only tests, skipped so the test sweep would not wipe the pc_pilot graph) in api, graph, scoring and rag against a scratch database `pc_test`; plus 10 UI tests.
  - UI revised (decision 35, branch `ui/react`): React + Vite + TypeScript + Tailwind SPA in `ui/`, same API, no new endpoints. 61 UI tests (logic, components, API client; three of the fixes were mutation-checked), typecheck clean, production build OK. Checked in the browser on pc_pilot in dark and light, on a phone width, with the API down, and in mock mode (orange MOCK DATA banner). Known gaps: no endpoint lists settings, so the Settings filter is empty until a stored candidate has one; `/rag/query` is still 501 (O5).
  - Review fixes (decisions 36 and 37): query adapter and hybrid search in the API and the React UI; `/health` and `api.prepare_demo`; `/clusters` no longer 503s on a fresh machine; exact-arithmetic signals (identical on Python 3.11 and 3.12); measured data limits in `scoring/tuning-pc_pilot.md` section 7. Graph screens were exercised with Neo4j running on pc_pilot (17 nodes for W3028876793, 343 for the largest of the bridge papers tried). Decision 30 (Method x Setting) stays Proposed: nothing in scoring, the API or the UI uses it.
  - Second audit (2026-11-22): 148 backend checks against raw SQL / numpy / an exact scan of all embeddings, linters on both languages, axe-core in a real browser, keyboard and layout checks at four widths. Fixed: weakly-connected cluster pairs could never flag a zero-citation pair (tie-averaged percentile; on the current clusters still 0 qualify, so the output is unchanged); bridge papers listed only unclustered papers; a truncated graph dropped the paper's own authors/venue/methods (now kept first, with a note); PostgreSQL down gave a bare 500 (now a 503 that says what to start); the first vector search took about 33 s (model now loads at startup); UI: colour contrast failed AA in both themes (text shades added, hex kept for dots/borders/nodes), invalid ARIA roles, no h1, drawer did not take focus or return it, cards were two tab stops, header stats crushed at tablet width, no URL state (reload lost everything), stale data could show after a dependency change. No SQL-injection or concurrency problem was found.
  - For Person 1: (a) the corpus Method × Task universe is 399 papers, 338 of them Machine Translation, so most expected counts are driven by MT; (b) "Masked Language Model Scoring" (W3024308166) is not tagged with Masked Language Modeling though its abstract says "masked language models (MLMs)"; plural forms may be missing from the aliases.
- Blockers: none. Pinned deps are in `requirements-person3.txt`.
