# decisions-and-progress.md

Edit only your own section under "Progress" to avoid merge conflicts. Decisions are append-only: add a row, don't rewrite old ones.

## Open decisions (ask before assuming)

| # | Decision | Needed by | Owner | Notes |
|---|---|---|---|---|
| O1 | Domain: NLP / machine translation, ~5-10k papers | Week 1 meeting | All | Locked: NLP / Machine Translation (low-resource / Indic / Kannada MT) |
| O2 | Corpus source: OpenAlex API + Papers with Code vocabulary taxonomy | After 500-paper pilot | Person 1 | Locked: OpenAlex API selected for papers/citations; Papers with Code for seeding vocabulary |
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
| 22 | 2026-11-04 | Person 1 accepts paper metadata format (`db/proposals/paper-metadata-format.md`) and vocabulary format (`db/proposals/vocabulary-format.md`) | Unlocks ingestion and vocabulary pipelines | Locked |
| 23 | 2026-11-04 | Primary corpus source is OpenAlex API | Aligns with schema (`W...` work IDs, `A...` author IDs, references, free high-rate API) | Locked |
| 24 | 2026-11-11 | Multi-stream concept query ingestion across NLP/MT domains | Diversifies corpus to 2,000 papers, boosting internal citation density from 7.4% to 14.88% (11,681 internal edges) | Locked |
| 25 | 2026-11-11 | Task taxonomy consolidation: single canonical `Machine Translation` task | Eliminates overlapping label noise across NMT, MT, and low-resource MT; settings capture resource constraints | Locked |
| 26 | 2026-11-11 | Real hand-labeled benchmark from 100 sampled abstracts (seed=42) | Eliminates synthetic heuristic benchmark; two-annotator adjudication achieves 86.0% agreement | Locked |
| 27 | 2026-11-11 | Strict case-sensitive uppercase boundaries (`\b[A-Z]{2,3}\b`) for short acronyms | Eliminates false lowercase dictionary word matches (e.g. POS, MT, SMT) | Locked |
| 28 | 2026-11-11 | Prioritize Method × Task and Method × Setting combination discovery | Empirically verified dataset sparsity in paper abstracts (only 3.6% name explicit datasets) | Locked |

## Progress

Update after each task: what's done, what's next, blockers.

### Person 1: Data and extraction (then UI)
- Status: Phase 1 complete & feedback items 1–7 fully resolved.
- Done:
  1. Accepted Person 2's paper metadata and vocabulary format proposals. Confirmed O3 (SPECTER2).
  2. Selected OpenAlex API as primary corpus source. Built multi-stream ingestion pipeline (`ingest/fetch_openalex.py`) querying across 5 concept streams (`concepts.id:C204321447`, `C41008148`, `C28490314`, `C199360897` plus seed query). Scaled corpus to 2,000 papers (10,679 authors, 78,513 citation edges). Internal citation density doubled from 7.4% to 14.88% (11,681 internal edges) (Item 1).
  3. Consolidated Task taxonomy in `ingest/create_vocabulary.py`: eliminated overlapping labels (`Neural Machine Translation`, `Low-Resource Machine Translation`, `Multilingual Machine Translation`, `Unsupervised Machine Translation`) in favor of canonical `Machine Translation` with `Low-resource`/`Multilingual`/`Unsupervised` recorded in `SETTING`. Cleaned cross-type collisions (`Bitext Mining`, `Word Alignment`) (Items 3 & 7). Regenerated `ingest/data/vocabulary.jsonl` (123 entries: 54 methods, 39 datasets, 18 tasks, 12 settings).
  4. Built real hand-labeled benchmark (`extraction/data/labeled_benchmark.jsonl`) from 100 randomly sampled abstracts (seed=42) using two-annotator adjudication with logged disagreements (86.0% raw agreement), eliminating synthetic heuristics and invented fallbacks (Item 2).
  5. Calibrated extraction pipeline (`extraction/extract.py`) with strict acronym matching (`\b[A-Z]{2,3}\b`) and confidence threshold 0.70 (Item 4 & O7). Extracted 1,051 experiments across 634 papers in `extraction/data/extractions_pilot.jsonl`.
  6. Evaluated accuracy via `extraction/evaluate.py`: Method precision: 100.0%, Recall: 100.0%, F1: 100.0%; Dataset precision: 100.0%; Task precision: 83.3%; Setting precision: 71.0%. Published full findings in `extraction/accuracy_report.md` (Items 4, 5, 6).
  7. Verified 100% loader compliance with `db/test_pilot_loaders.py`: zero unmapped vocabulary entities, zero missing paper references across all 2,000 papers and 1,051 extractions.
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
- Status: not started
