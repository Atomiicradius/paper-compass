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
| `POST /search`, `GET /papers/{id}/related`, `POST /opportunities/{id}/explain`, `POST /rag/query` | Return 501 until Person 2's `retrieval/` and `rag/` exist |
| `POST /opportunities/{id}/feedback` | Not built (stretch) |

Every response shape except the opportunity object is **provisional** until open decision O10 is agreed with the UI owner (see `schemas.py`). Interactive docs are at `/docs`.
