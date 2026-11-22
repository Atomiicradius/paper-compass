# api/ (Person 3)

FastAPI backend for the endpoints in `context/data-and-contracts.md` section 5. Interactive docs are at `/docs`.

## Run

```bash
powershell -File api/run-api.ps1 [-Port 8000] [-Db pc_pilot]     # reads db/.env; database pc_pilot
uvicorn api.main:app                                              # the same without the script: reads db/.env
PC_PG_DSN=postgresql://... PC_NEO4J_URI=bolt://... PC_NEO4J_PASSWORD=... uvicorn api.main:app   # explicit settings
PC_API_MOCK=1 uvicorn api.main:app --reload                       # clearly marked mock data, no database
```

Settings are read from the environment first, then from `db/.env` (database `PC_PG_DBNAME`, default `pc_pilot`).
Without any database setting every endpoint answers **503 "API is not configured"**.

### After restoring the pilot dump

A restored dump holds papers, experiments, embeddings and citations, but not the derived data a demo shows
(opportunities, clusters, the Neo4j projection). One command fills them in and is safe to repeat:

```bash
python -m api.prepare_demo [--dbname pc_pilot] [--force] [--skip-neo4j]
```

It scores Method x Task with the settings chosen on pc_pilot (`scoring/tuning-pc_pilot.md`), computes the clusters,
and syncs Neo4j when its paper count differs from PostgreSQL. Without it: `/opportunities` is empty (the UI says so),
the graph endpoint answers 503, and `/clusters` computes itself on first use (about 8 seconds, once). Then check:

```bash
curl http://127.0.0.1:8000/health
```

The first vector search used to take about 30 seconds because it loaded the SPECTER2 model. The API now loads it in the
background when it starts (`PC_WARMUP=0` switches that off), so the first search takes a fraction of a second once
`/health` shows `query_encoder.loaded: true`.

`GET /health` always answers 200. `status` is `ok` or `degraded`; `postgres` has the counts (papers, with embeddings,
experiments, opportunities), `neo4j` its paper count, `query_encoder` whether search can use vectors, and `notes` says
what to run for each problem. It never contains a password.

## Endpoints

| Endpoint | Status |
|---|---|
| `GET /health` | Readiness report for a demo (see above) |
| `GET /opportunities`, `GET /opportunities/{id}` | Done; response follows the contract's opportunity object |
| `GET /papers/{id}`, `GET /papers/{id}/graph` | Done (the graph comes from Neo4j). `limit` counts nodes, centre included. When a paper has more neighbours the response has `truncated: true` and `neighbors_total`; the paper's own authors, venue and extracted elements are kept first, then its most recent citations, in a fixed order |
| `GET /trends`, `GET /clusters`, `GET /landscape` | Done. `/clusters` computes `graph/out/clusters.json` on first use if it is missing |
| `POST /search` | Done; Person 2's `db/retrieval`: vector, keyword or hybrid (below) |
| `GET /papers/{id}/related` | Done; nearest papers to the paper's own embedding, the paper itself excluded |
| `POST /opportunities/{id}/explain` | `{opportunity_id, evidence, summary, summary_source, summary_fallback_reason, citation_check, disclaimer}` from Person 2's `rag/`. The summary is the evidence-grounded template; an optional LLM text (`PC_LLM_SUMMARY=1`, off by default) falls back to the template on any problem. 422 if the opportunity is not exactly one pair of method/dataset/task |
| `POST /rag/query` | 501 until an LLM client is chosen (O5) |
| `POST /opportunities/{id}/feedback` | Not built (stretch) |

## Search

`POST /search` body: `{"query": "...", "top_k": 10, "year_min": 2020}` (the contract fields), plus optional `year_max`,
`venues`, `methods`, `datasets`, `tasks` (names or aliases), `match` (`same_experiment` or `any`, see `db/README.md`),
`collapse_same_title` (default false; hides extra records of one title, because the pilot corpus has duplicate OpenAlex
records) and `mode`:

| `mode` | What it does | `score_type` |
|---|---|---|
| `auto` (default) | vector search if a query encoder exists and the stored embeddings match, else keyword search with the reason in `note` | `cosine_similarity` / `ts_rank` |
| `vector` | SPECTER2 vector search. 503 without an encoder, 409 if the paper embeddings are missing or from another model | `cosine_similarity` |
| `keyword` | PostgreSQL full-text search. **Every word must match**, so one word no paper contains gives no result; the response `note` says so | `ts_rank` |
| `hybrid` | vector and keyword lists fused by reciprocal rank fusion (Person 2's `search_hybrid`, k = 60). Never chosen by `auto`. Applies the year filters and `collapse_same_title` only; a method, dataset, task or venue filter is a **422** instead of being ignored. Each hit also has `vector_rank` and `keyword_rank` (null when the paper is not in that list) | `rrf_fused` |

Every hit has `paper_id`, `title`, `year`, `venue`, `score`, `methods`, `datasets`, `tasks`; `model` is what encoded the
query (null for keyword search).

**Query encoder.** Queries are encoded with Person 2's query-side encoder: the SPECTER2 base model with the
`specter2_adhoc_query` adapter (`PC_QUERY_ADAPTER=proximity` selects the old behaviour). Papers were embedded with the
proximity adapter; both write into the same vector space, so the API checks the stored `paper.embedding_model` against
the paper-side model string, not against the query adapter's name. It needs `torch`, `transformers` and `adapters`
(`db/embeddings/requirements-embeddings.txt`), in the same Python environment as uvicorn; without them `auto` uses
keyword search. `PC_QUERY_ENCODER=none` switches it off. The model (about 0.9 GB) loads on the first vector search.

Bad input is a 422, never a 500: a blank or NUL-containing query, a NUL in a filter, `year_min > year_max`, a query over
5,000 characters. Paper ids in the path may not contain NUL and are limited to 200 characters.

`GET /papers/{id}/related?top_k=10&year_min=&year_max=`: 404 for an unknown paper, 409 if it has no embedding.

## What a status code means

| Code | Meaning |
|---|---|
| 422 | the request is invalid (the `detail` names the field) |
| 404 | unknown paper or opportunity |
| 409 | vector data is missing or from another model |
| 501 | `/rag/query` is not built yet |
| 503 | PostgreSQL is not reachable (the `detail` says what to start), the API is not configured, Neo4j is down (graph endpoint), the query encoder is missing (vector / hybrid), or clusters cannot be computed. The `detail` says which and what to run |
| 500 | a bug; please report it |

## Tests

`python -m pytest api graph scoring`. Integration tests run when `PC_TEST_PG_DSN` (and `PC_TEST_NEO4J_URI`,
`PC_TEST_NEO4J_USER`, `PC_TEST_NEO4J_PASSWORD` for the graph sync) are set; they build a throwaway schema, so use a
scratch database, never `pc_pilot`. If a local PostgreSQL already uses port 5432, run the project's container on another
port (`POSTGRES_PORT` in `db/.env`).

Every response shape except the opportunity object is **provisional** until open decision O10 is agreed with the UI
owner (see `schemas.py` and `api-shapes-o10.md`).
