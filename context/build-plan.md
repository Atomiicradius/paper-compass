# build-plan.md

Ownership, phases, evaluation, and risks. Full detail: `docs/reference/project-plan-v2.md`.

## Ownership

Names are assigned in the first team meeting. Each person owns an early module and a later module so the load stays even and nothing is unowned. **Each person evaluates their own module.**

| | **Person 1** | **Person 2** | **Person 3** |
|---|---|---|---|
| Name | _TBD_ | _TBD_ | _TBD_ |
| **Early (weeks 1-4)** | **Data and extraction** (`ingest/`, `extraction/`): corpus pilot and full ingestion, cleaning, controlled vocabulary and aliases, extraction with provenance, 100-abstract labeled set, accuracy report | **Database and retrieval** (`db/`, `retrieval/`): Docker Compose, DDL, loaders, SPECTER2 embeddings, HNSW, hybrid search, materialized views, keyword-vs-vector evaluation | **Graph and analysis** (`graph/`): Neo4j model, idempotent sync and count verification, Cypher queries, clusters, bridges, temporal trends |
| **Later (weeks 4-7)** | **UI** (folder created once stack is chosen): six screens, graph visualization, limitations banner; stretch: weight sliders, feedback buttons | **Evidence and RAG** (`rag/`): evidence JSON builder, nearest-existing-work lookup, RAG with citation verification, explanation evaluation, DBMS benchmarks | **Scoring and API** (`scoring/`, `api/`): candidate generation, normalized signals, confidence, score, sensitivity check, FastAPI endpoints, temporal holdout and baselines |
| **Report and demo** | Data, extraction, and UI sections; demo script | Schema, indexing, benchmarks, RAG sections | Graph, scoring, evaluation sections; slides |

Notes:
- If Person 3 is overloaded, move the API to Person 1. (The evidence JSON builder and RAG are already with Person 2.)
- Person 1 helps Person 2 with extraction review after the first pass. Person 2 helps with extraction once the loader is done.
- Everyone should be able to explain the full pipeline in the viva.

## Interfaces between people
1. Database schema (owner: Person 2)
2. Extraction output format (producer: Person 1, consumer: Person 2's loader)
3. Opportunity object and API (owner: Person 3; consumers: UI and RAG)

All three live in `data-and-contracts.md`.

## Phases (about 8 weeks with agent-assisted coding; stretch to 10 if needed)

**Phase 0: Decisions (days 1-2).** Confirm domain and corpus, vocabulary approach, shared ID convention, owners. Repo and context files are in place. Docker Compose started.

**Phase 1: Foundation (weeks 1-2).** Docker, schema, pilot of ~500 papers, loader, Neo4j toy dataset, mock data for downstream work. Milestone: ~5k papers with authors and citations in PostgreSQL.

**Phase 2: Retrieval and graph (weeks 3-4).** Embeddings and hybrid search; Neo4j sync and verification; first extraction pass with accuracy measured. Milestone: search returns relevant papers; graph shows a paper's neighborhood.

**Phase 3: Core novelty (weeks 4-6).** Full extraction, materialized views, sparsity with expected counts, three-signal scoring, clusters, bridges. Milestone: ranked candidate pairs with supporting papers.

**Phase 4: Explanation and UI (weeks 6-7).** Evidence JSON, RAG with citation checks, UI screens, benchmarks. Milestone: end-to-end demo for the primary query.

**Phase 5: Evaluation and polish (week 8).** Retrieval metrics, extraction accuracy, temporal holdout, baselines, sensitivity analysis, limitations, report, slides.

Build a **thin end-to-end version early**: ~500 papers through search → graph → one opportunity → one evidence page. Then scale.

## Evaluation (summary)
- **Retrieval:** Precision@K, Recall@K, nDCG@K; keyword vs vector vs hybrid on ~15-20 team-labeled queries.
- **Extraction:** hand-label ~100 abstracts; precision and recall per entity type; coverage per entity type.
- **Opportunities:** temporal holdout (primary); baselines (random, sparsity only, semantic only); hide-and-recover; small expert rating of the top 10; weight sensitivity.
- **Explanation:** evidence relevance, citation correctness (automated check), factual consistency.
- **DBMS demonstration:** normalization reasoning, constraints, `EXPLAIN ANALYZE` with and without indexes, exact vs HNSW, hybrid query, materialized views and refresh, recursive CTE vs Cypher for multi-hop citations, sync consistency check, transactional batch ingestion.

Caveat for the report: later appearance of a combination can have causes unrelated to our signals. We show predictive signal, not research-gap accuracy.

## Top risks
| Risk | Mitigation |
|---|---|
| Extraction quality drives everything | Annotated source if available; closed vocabulary; provenance; labeled accuracy check; review queue |
| Datasets missing from abstracts, causing false sparsity | Start with method × task; report coverage per entity type |
| Sparsity is a weak signal | Observed vs expected; confidence; support threshold; semantic filter; nearest existing work |
| Combinatorial explosion | Pairs first; query-neighborhood candidates; support threshold |
| Soft validation | Temporal holdout; baselines; expert rating; no gap-accuracy claim |
| Scope vs three people | Locked scope; thin end-to-end first; stretch list |
| DBMS content buried by ML work | Benchmarks scheduled in Phase 4 |
| PostgreSQL / Neo4j drift | Idempotent sync and count verification |
| Agent-written code is fluent but wrong | Tests first for numeric code; spot-check against raw SQL |
| Teammates can't explain their module | Weekly 15-minute cross-walkthroughs |

## Working agreement
- Small branches, one module each, merge daily.
- Weekly check-in and weekly cross-review of modules.
- No silent schema or contract changes.
- Pin environments.
- Keep agent-generated diffs reviewable.
