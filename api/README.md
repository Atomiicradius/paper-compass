# api/ (Person 3)

FastAPI backend for the endpoints in `context/data-and-contracts.md` section 5.

```bash
PC_API_MOCK=1 uvicorn api.main:app --reload                 # clearly marked mock data, no database
PC_PG_DSN=postgresql://... PC_NEO4J_URI=bolt://... PC_NEO4J_PASSWORD=... uvicorn api.main:app
```

| Endpoint | Status |
|---|---|
| `GET /opportunities`, `GET /opportunities/{id}` | Done; response follows the contract's opportunity object |
| `GET /papers/{id}`, `GET /papers/{id}/graph` | Done (graph comes from Neo4j) |
| `GET /trends`, `GET /clusters`, `GET /landscape` | Done |
| `POST /search` | Done; uses Person 2's `db/retrieval` (vector search, or the keyword baseline) |
| `GET /papers/{id}/related` | Done; nearest papers to the paper's own embedding, the paper itself excluded |
| `POST /opportunities/{id}/explain` | `{opportunity_id, evidence, summary, citation_check, disclaimer}` from Person 2's `rag/` (template summary, no LLM); shape provisional, see `db/proposals/evidence-chain-format.md`. 422 if the opportunity is not exactly one pair of method/dataset/task |
| `POST /rag/query` | Returns 501 until an LLM client is chosen (O5) |
| `POST /opportunities/{id}/feedback` | Not built (stretch) |

## Search

`POST /search` body: `{"query": "...", "top_k": 10, "year_min": 2020}` (the contract fields), plus optional
`year_max`, `venues`, `methods`, `datasets`, `tasks` (names or aliases), `match` (`same_experiment` or `any`,
see `db/README.md`) and `mode`:

- `auto` (default): vector search if a query encoder is available and the stored paper embeddings come from
  the same model; otherwise keyword search, with the reason in `note`.
- `vector`: 503 if there is no query encoder, 409 if the paper embeddings are missing or from another model.
- `keyword`: PostgreSQL full-text baseline, no model needed.

Every hit has `paper_id`, `title`, `year`, `venue`, `score`, `methods`, `datasets`, `tasks`. `score_type` says
what `score` is (`cosine_similarity` or `ts_rank`); `model` is the embedding model, null for keyword search.

The query encoder is Person 2's SPECTER2 encoder from `db/embeddings` (proximity adapter, interim until Person 2
compares it with the `specter2_adhoc_query` adapter). It needs `torch`, `transformers` and `adapters` (see
`db/embeddings/requirements-embeddings.txt`); without them `auto` uses keyword search. `PC_QUERY_ENCODER=none`
switches it off. The model (about 0.9 GB) loads on the first vector search.

`GET /papers/{id}/related?top_k=10&year_min=&year_max=`: 404 for an unknown paper, 409 if it has no embedding.

## Tests

`python -m pytest api graph scoring`. Integration tests run when `PC_TEST_PG_DSN` (and `PC_TEST_NEO4J_URI`,
`PC_TEST_NEO4J_USER`, `PC_TEST_NEO4J_PASSWORD` for the graph sync) are set. If a local PostgreSQL already
uses port 5432, run a second container from Person 2's image on another port, e.g.
`docker run -d -p 55432:5432 -e POSTGRES_USER=... -e POSTGRES_PASSWORD=... paper-compass-postgres:16-pgvector`.

Every response shape except the opportunity object is **provisional** until open decision O10 is agreed with the UI owner (see `schemas.py`). Interactive docs are at `/docs`.
