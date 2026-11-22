# ui/ (Streamlit, O4)

The six screens from `context/docs/reference/project-plan-v2.md` section 14.1. The UI only talks to the FastAPI backend (`api/`) over HTTP. It never queries PostgreSQL or Neo4j directly, so it uses the same shapes as any other client (see `api/api-shapes-o10.md`).

| Screen | API calls |
|---|---|
| Search | `POST /search` (auto mode: SPECTER2 vector search, or keyword search if the encoder is missing) |
| Paper Explorer | `GET /papers/{id}`, `GET /papers/{id}/related` |
| Research Graph | `GET /papers/{id}/graph` (Neo4j), drawn with Graphviz in the browser |
| Landscape | `GET /landscape`, `GET /clusters`, `GET /trends` |
| Opportunity Dashboard | `GET /opportunities`, plus view-only what-if weight sliders (`ui/rerank.py`, same formula as `scoring.score`) |
| Opportunity Detail | `GET /opportunities/{id}`, `POST /opportunities/{id}/explain`, `POST /rag/query` (501 until O5) |

Every screen shows the corpus size, the publication years, the extraction method and the statement that results are candidates for human review.

## Run (PowerShell, from the repository root)

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-person3.txt -r ui\requirements-ui.txt
# optional, for vector search: the embedding stack from db\embeddings\requirements-embeddings.txt

# 1. API on the pilot database (PC_PG_DSN etc. as in api/README.md)
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
# 2. UI (PC_API_URL defaults to http://127.0.0.1:8000)
.venv\Scripts\python.exe -m streamlit run ui\app.py
```

The first vector search downloads SPECTER2 (about 0.9 GB) into the Hugging Face cache and loads it, which takes a few minutes. Later searches take well under a second.

Tests: `python -m pytest ui` covers the re-ranking formula (it reproduces a stored v1 score) and the HTTP client. They need no server.
