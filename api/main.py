"""FastAPI backend (data-and-contracts.md section 5).

    uvicorn api.main:app --reload

Configuration (environment variables):
    PC_API_MOCK=1          serve clearly marked mock data, no database needed
    PC_PG_DSN              PostgreSQL connection string
    PC_NEO4J_URI / PC_NEO4J_USER / PC_NEO4J_PASSWORD
    PC_CLUSTERS_PATH       output of graph.clusters (default graph/out/clusters.json)
    PC_QUERY_ENCODER       specter2 (default) or none; see api/query_encoder.py

/search and /papers/{id}/related use Person 2's db/retrieval search layer.
/opportunities/{id}/explain uses Person 2's rag/ evidence builder and, by default, the template summary; an
optional LLM explanation (PC_LLM_SUMMARY=1, rag/llm_summary.py) falls back to the template on any problem.
/rag/query returns 501 until an LLM client is chosen (open decision O5).
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from api import schemas
from api.query_encoder import QueryEncoder, get_query_encoder
from api.repository import PostgresRepository, Repository, VectorSearchUnavailable

DISCLAIMER = (
    "Candidate research opportunities are combinations weakly represented in the analyzed corpus. "
    "They are signals for human review, not proof of a research gap."
)

log = logging.getLogger("paper-compass.api")


def _warm_up_encoder(encoder) -> None:
    """Load the SPECTER2 model now (about 30 s) so that the first search does not pay for it."""
    try:
        encoder.embed(["warm up"])
        log.info("query encoder is loaded")
    except Exception as e:  # noqa: BLE001 - a failed warm-up must never stop the API; the first search will say why
        log.warning("query encoder warm-up failed: %s: %s", type(e).__name__, str(e)[:200])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("PC_WARMUP", "1") != "0":
        encoder = get_query_encoder()
        if encoder is not None:
            threading.Thread(target=_warm_up_encoder, args=(encoder,), daemon=True, name="encoder-warmup").start()
    yield


app = FastAPI(title="paper-compass API", version="0.1.0", lifespan=lifespan)

# OpenAlex ids look like W1234567890. PostgreSQL cannot store NUL characters, so one in a path or a
# search term would otherwise surface as a 500; reject it (and absurd lengths) with a 422 instead.
PaperId = Annotated[str, PathParam(min_length=1, max_length=200, pattern=r"^[^\x00]+$")]


class NotConfigured(RuntimeError):
    """The server was started without a database (PC_PG_DSN) or PC_API_MOCK=1."""


@app.exception_handler(NotConfigured)
def _not_configured(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _register_database_errors() -> None:
    """A database that is down is a 503 that says what to do, not a bare 500. Only the error's class is named: the
    message of a connection error can contain the host, user or other connection details."""
    import psycopg
    from fastapi.responses import JSONResponse

    @app.exception_handler(psycopg.OperationalError)
    def _postgres_unreachable(request, exc):
        return JSONResponse(status_code=503, content={"detail": (
            "PostgreSQL is not reachable (" + type(exc).__name__ + "). Start the containers (cd db; docker compose up -d) "
            "and check PC_PG_DSN / db/.env. GET /health shows the state of each service.")})


_register_database_errors()


DB_ENV_FILE = Path(__file__).resolve().parent.parent / "db" / ".env"


def _settings_from_env_file(path: Path = DB_ENV_FILE) -> dict[str, str]:
    """PC_* settings built from db/.env (the compose credentials), or {} if the file is missing.

    Used only when PC_PG_DSN is not set, so `uvicorn api.main:app` works without exporting anything.
    The database is PC_PG_DBNAME (default pc_pilot, the pilot corpus), not POSTGRES_DB.
    """
    from urllib.parse import quote

    if not path.is_file():
        return {}
    vals: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip("'\"")
    if not (vals.get("POSTGRES_USER") and vals.get("POSTGRES_PASSWORD")):
        return {}
    db = os.environ.get("PC_PG_DBNAME", "pc_pilot")
    out = {"PC_PG_DSN": f"postgresql://{quote(vals['POSTGRES_USER'])}:{quote(vals['POSTGRES_PASSWORD'])}"
                        f"@{vals.get('POSTGRES_HOST', '127.0.0.1')}:{vals.get('POSTGRES_PORT', '5432')}/{db}"}
    if vals.get("NEO4J_PASSWORD"):
        out["PC_NEO4J_URI"] = f"bolt://127.0.0.1:{vals.get('NEO4J_BOLT_PORT', '7687')}"
        out["PC_NEO4J_USER"] = vals.get("NEO4J_USER", "neo4j")
        out["PC_NEO4J_PASSWORD"] = vals["NEO4J_PASSWORD"]
    return out


@lru_cache(maxsize=1)
def get_repo() -> Repository:
    if os.environ.get("PC_API_MOCK") == "1":
        from api.mock_data import MockRepository

        return MockRepository()
    dsn = os.environ.get("PC_PG_DSN")
    if not dsn:
        for k, v in _settings_from_env_file().items():
            os.environ.setdefault(k, v)
        dsn = os.environ.get("PC_PG_DSN")
    if not dsn:
        raise NotConfigured("API is not configured: set PC_PG_DSN (and PC_NEO4J_URI / PC_NEO4J_PASSWORD) "
                            "before starting uvicorn, or PC_API_MOCK=1 for mock data. See api/README.md")
    driver = None
    if os.environ.get("PC_NEO4J_URI"):
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.environ["PC_NEO4J_URI"],
            auth=(os.environ.get("PC_NEO4J_USER", "neo4j"), os.environ.get("PC_NEO4J_PASSWORD", "")),
            # fail in seconds, not a minute, when Neo4j is down (the graph endpoint and /health both depend on it)
            connection_timeout=3, connection_acquisition_timeout=5, max_transaction_retry_time=2,
        )
    clusters = os.environ.get("PC_CLUSTERS_PATH", str(Path(__file__).resolve().parent.parent / "graph" / "out" / "clusters.json"))
    return PostgresRepository(dsn, driver, clusters)


def _disclaimer() -> str:
    if os.environ.get("PC_API_MOCK") == "1":
        from api.mock_data import MOCK_NOTICE

        return f"{MOCK_NOTICE}. {DISCLAIMER}"
    return DISCLAIMER


# --- health ---------------------------------------------------------------------

@app.get("/health")
def health(encoder: QueryEncoder | None = Depends(get_query_encoder)):
    """Is the backend ready for a demo? Always answers 200; `status` is "ok" or "degraded" and `notes` says what
    to run for each problem. Reports mock mode, PostgreSQL counts, Neo4j, the query encoder and the clusters file."""
    try:
        data = get_repo().health()
    except NotConfigured as e:
        data = {"mock": False, "postgres": {"ok": False, "error": "not configured"},
                "neo4j": {"configured": False, "ok": None}, "clusters": {"file": False}, "notes": [str(e)]}
    notes = list(data["notes"])
    enc: dict = {"available": encoder is not None}
    if encoder is not None:
        enc.update(model=encoder.model_string, paper_model=encoder.paper_model_string, loaded=getattr(encoder, "loaded", None))
    elif not data.get("mock"):
        notes.append("No query encoder (torch / transformers / adapters missing, or PC_QUERY_ENCODER=none): "
                     "search falls back to keyword mode and hybrid mode is unavailable")
    pg, neo = data["postgres"], data["neo4j"]
    ready = bool(pg.get("ok") and pg.get("opportunities", 0) > 0 and pg.get("with_embeddings", 0) > 0
                 and neo.get("ok") is True and encoder is not None)
    return {"status": "ok" if (ready or data.get("mock")) else "degraded", "mock": bool(data.get("mock")),
            "postgres": pg, "neo4j": neo, "query_encoder": enc, "clusters": data["clusters"], "notes": notes}


# --- Person 3 endpoints ------------------------------------------------------

@app.get("/opportunities", response_model=schemas.OpportunityList)
def list_opportunities(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cutoff_year: int | None = None,
    weights_version: str | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    repo: Repository = Depends(get_repo),
):
    total, items = repo.list_opportunities(limit, offset, cutoff_year, weights_version, min_confidence)
    return {"total": total, "items": items, "disclaimer": _disclaimer()}


@app.get("/opportunities/{opportunity_id}", response_model=schemas.Opportunity)
def get_opportunity(opportunity_id: int, repo: Repository = Depends(get_repo)):
    opp = repo.get_opportunity(opportunity_id)
    if opp is None:
        raise HTTPException(404, "opportunity not found")
    return opp


@app.get("/papers/{paper_id}", response_model=schemas.Paper)
def get_paper(paper_id: PaperId, repo: Repository = Depends(get_repo)):
    paper = repo.get_paper(paper_id)
    if paper is None:
        raise HTTPException(404, "paper not found")
    return paper


@app.get("/papers/{paper_id}/graph", response_model=schemas.PaperGraph)
def get_paper_graph(paper_id: PaperId, limit: int = Query(200, ge=1, le=1000), repo: Repository = Depends(get_repo)):
    from neo4j.exceptions import DriverError, Neo4jError

    try:
        graph = repo.paper_graph(paper_id, limit)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except (Neo4jError, DriverError) as e:
        # e.g. wrong credentials or Neo4j not running: say so instead of a bare 500
        raise HTTPException(503, f"Neo4j unavailable: {e.__class__.__name__}: {e}")
    if graph is None:
        raise HTTPException(404, "paper not found in graph")
    return graph


@app.get("/trends", response_model=list[schemas.TrendItem])
def get_trends(
    element_type: Literal["method", "dataset", "task", "topic"] = "method",
    label: Literal["emerging", "declining", "stable"] | None = None,
    repo: Repository = Depends(get_repo),
):
    items = repo.trends(element_type)
    return [t for t in items if label is None or t["label"] == label]


@app.get("/clusters")
def get_clusters(repo: Repository = Depends(get_repo)):
    try:
        data = repo.clusters()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    # labels and centroids are large and only needed server-side
    return {
        **{k: v for k, v in data.items() if k != "labels"},
        "clusters": [{k: v for k, v in c.items() if k != "centroid"} for c in data.get("clusters", [])],
    }


@app.get("/landscape", response_model=schemas.Landscape)
def get_landscape(repo: Repository = Depends(get_repo)):
    return {**repo.landscape(), "disclaimer": _disclaimer()}


# --- endpoints backed by Person 2's modules -------------------------------------

class SearchRequest(BaseModel):
    # contract fields
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(10, ge=1, le=100)
    year_min: int | None = None
    # optional extras, passed through to db.retrieval.search (provisional, O10)
    year_max: int | None = None
    venues: list[str] | None = None
    methods: list[str] | None = None
    datasets: list[str] | None = None
    tasks: list[str] | None = None
    match: Literal["same_experiment", "any"] = "same_experiment"
    # hide extra records of one title (the pilot corpus has duplicate OpenAlex records); off = Person 2's default
    collapse_same_title: bool = False
    # auto: vector search when a query encoder and matching paper embeddings exist, else keyword search.
    # hybrid: vector and keyword search fused by reciprocal rank fusion (year filters only; never chosen by auto)
    mode: Literal["auto", "vector", "keyword", "hybrid"] = "auto"

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("must not contain NUL characters")
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("venues", "methods", "datasets", "tasks")
    @classmethod
    def _no_nul_in_filters(cls, v):
        if v and any("\x00" in x for x in v):
            raise ValueError("must not contain NUL characters")
        return v

    @model_validator(mode="after")
    def _year_range(self):
        if self.year_min is not None and self.year_max is not None and self.year_min > self.year_max:
            raise ValueError("year_min must not be greater than year_max")
        return self


# exclude_unset: vector and keyword hits keep their original shape; only hybrid hits carry vector_rank/keyword_rank
@app.post("/search", response_model=schemas.SearchResponse, response_model_exclude_unset=True)
def search(body: SearchRequest, repo: Repository = Depends(get_repo),
           encoder: QueryEncoder | None = Depends(get_query_encoder)):
    filters = body.model_dump(exclude={"query", "top_k", "mode"})
    mode, note = body.mode, None
    if mode == "auto":
        mode = "vector" if encoder is not None else "keyword"
        if encoder is None:
            note = "query encoder not available; used keyword search"
    if mode in ("vector", "hybrid") and encoder is None:
        raise HTTPException(503, "query encoder not available (PC_QUERY_ENCODER=none or torch/transformers/adapters "
                                 "not installed); use mode=keyword")
    try:
        if mode == "hybrid":
            try:
                out = repo.hybrid_search(encoder, body.query, body.top_k, filters)
            except VectorSearchUnavailable as e:
                raise HTTPException(409, str(e))
        elif mode == "vector":
            try:
                out = repo.vector_search(encoder, body.query, body.top_k, filters)
            except VectorSearchUnavailable as e:
                if body.mode == "vector":
                    raise HTTPException(409, str(e))
                mode, note = "keyword", f"{e}; used keyword search"
                out = repo.keyword_search(body.query, body.top_k, filters)
        else:
            out = repo.keyword_search(body.query, body.top_k, filters)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if mode == "keyword" and not out["results"]:
        # PostgreSQL full-text search needs every word to match, so one unknown word empties the result
        no_hits = "no paper contains every word of the query; try fewer words, or the vector or hybrid mode"
        note = f"{note}; {no_hits}" if note else no_hits
    return {"query": body.query, "mode": mode, "note": note,
            "score_type": {"vector": "cosine_similarity", "keyword": "ts_rank", "hybrid": "rrf_fused"}[mode], **out}


@app.get("/papers/{paper_id}/related", response_model=schemas.RelatedResponse)
def related(paper_id: PaperId, top_k: int = Query(10, ge=1, le=100), year_min: int | None = None,
            year_max: int | None = None, repo: Repository = Depends(get_repo)):
    try:
        out = repo.related(paper_id, top_k, {"year_min": year_min, "year_max": year_max})
    except VectorSearchUnavailable as e:
        raise HTTPException(409, str(e))
    if out is None:
        raise HTTPException(404, "paper not found")
    return {"paper_id": paper_id, "score_type": "cosine_similarity", **out}


@app.post("/opportunities/{opportunity_id}/explain")
def explain(opportunity_id: int, repo: Repository = Depends(get_repo)):
    """{opportunity_id, evidence, summary, summary_source, summary_fallback_reason, citation_check, disclaimer};
    summary_source is "template" (default) or "llm" (PC_LLM_SUMMARY=1 and the guardrails passed), and
    summary_fallback_reason says why the template was used instead (null when it was simply the default). Shape provisional until it is in
    data-and-contracts.md (db/proposals/evidence-chain-format.md)."""
    try:
        out = repo.explain(opportunity_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if out is None:
        raise HTTPException(404, "opportunity not found")
    return {**out, "disclaimer": _disclaimer()}


@app.post("/rag/query")
def rag_query():
    raise HTTPException(501, "not implemented yet: needs an LLM client (open decision O5)")
