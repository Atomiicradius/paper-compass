# decisions-and-progress.md

Edit only your own section under "Progress" to avoid merge conflicts. Decisions are append-only: add a row, don't rewrite old ones.

## Open decisions (ask before assuming)

| # | Decision | Needed by | Owner | Notes |
|---|---|---|---|---|
| O1 | Domain: NLP / machine translation, ~5-10k papers | Week 1 meeting | All | Proposed |
| O2 | Corpus source: OpenAlex / Semantic Scholar / ACL Anthology / annotated dump | After 500-paper pilot | Person 1 | Check whether an annotated Papers with Code dump is obtainable |
| O3 | Embedding model: SPECTER2 vs Sentence Transformer for prototype | Before loading data | Person 2 | SPECTER2 (allenai/specter2_base + allenai/specter2 proximity adapter), 768-dim, no schema change; proposed, awaiting teammates' confirmation; measured on Person 2's machine, see db/experiments/embeddings/results.md |
| O4 | UI stack | Week 3-4 | UI owner | Do not scaffold before this is decided |
| O5 | LLM / RAG client and model | Phase 3 | RAG owner | |
| O6 | Score weights, `min_support`, confidence constant `k` | Phase 3 | Scoring owner | Tune on real data; keep a sensitivity check |
| O7 | Extraction method: annotations, LLM, rules, or mix; confidence threshold | After first pass | Person 1 | |
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
| 19 | 2026-10-30 | Postgres container is built from `db/Dockerfile` (`postgres:16` pinned by digest, plus apt `postgresql-16-pgvector` pinned) instead of the `pgvector/pgvector` image, because that image fails with `exec format error` on Person 2's Docker setup; one identical image for everyone | Reproducible environment | Proposed, teammates to confirm |
| 20 | 2026-10-31 | Embedding model is SPECTER2 with the proximity adapter; `vector(768)` unchanged | Runs on CPU at about 0.13 s per paper, 768-dim output matches the schema; see `db/experiments/embeddings/results.md` | Proposed |

## Progress

Update after each task: what's done, what's next, blockers.

### Person 1: Data and extraction (then UI)
- Status: not started

### Person 2: Database and retrieval (then evidence and RAG)
- Status: week-1 foundation done (branch `db/foundation`).
- Done: schema and containers (Postgres 16.15 + pgvector 0.8.7, Neo4j 5.26.32; schema from the contracts loaded verbatim via `db/init.sql`); 76 tests passing; loader (vocabulary, papers, extractions, refresh, load-all) done and run on the mock data in `db/mock/`; proposals for the paper metadata and vocabulary formats written in `db/proposals/`, awaiting Person 1's confirmation.
- Done (embeddings): SPECTER2 measured on CPU (about 0.13 s per paper, 768-dim; `db/experiments/embeddings/results.md`); embedding pipeline `embed-papers` in `db/embeddings/` built with tests (stub encoder, plus one `slow` real-model test) and run on the mock papers.
- Proposed, awaiting teammates: decision #19 (Postgres built from `db/Dockerfile`); O3 / decision #20 (SPECTER2 with the proximity adapter, `vector(768)` unchanged). Real papers are not embedded until O3 is confirmed.
- Done (retrieval): SQL search layer in `db/retrieval/` with tests: vector search (year, venue, method/dataset/task filters with aliases, offset, exclusions, optional entity names) using pgvector iterative index scans for selective filters, and a full-text keyword baseline. No API (Person 3 owns it). Tested on synthetic vectors only; no real embeddings exist yet.
- Done (evaluation): retrieval metrics (precision@K, recall@K, MRR, nDCG@K with graded relevance) and a runner that scores precomputed ranking files, in `db/retrieval/evaluation/` with hand-computed tests; no database or model involved. Query-set format written as a proposal (`db/proposals/retrieval-eval-format.md`), awaiting the team.
- Next: embedding the real corpus once O3 is confirmed, labelling 15-20 queries, and the keyword-vs-vector evaluation. The query encoder (`specter2_adhoc_query` adapter vs the proximity adapter) is not implemented; it will be compared on the labelled query set once real papers exist.
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
  - Clusters have no table in the schema. They stay in a JSON file unless the team decides to add one.
  - `/explain` and `/rag/query` return 501 until `rag/` exists.
  - `/search` takes optional filter fields and a `mode` on top of the contract body (see `api/README.md`). Provisional under O10; I will copy the final shape into `data-and-contracts.md` once agreed.
- Update (2026-11-01): `/search` and `/papers/{id}/related` built on Person 2's `db/retrieval` (branch `person3` merges `db/embeddings`).
  - The query encoder is Person 2's SPECTER2 proximity encoder until their adapter comparison. Vector search refuses paper embeddings from another model; in `auto` mode it falls back to keyword search and says why.
  - Tests: 66 passing with no skips, against Person 2's Postgres image and Neo4j 5.26.32. Person 2's `init.sql` is identical to the contract DDL my tests use.
  - Note for Person 2: `requirements-person3.txt` pins psycopg 3.2.13, `db/requirements.txt` pins 3.3.6. We should agree on one version in a shared lockfile.
- Blockers: none. Pinned deps are in `requirements-person3.txt`.
