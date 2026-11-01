"""FastAPI backend (data-and-contracts.md section 5).

    uvicorn api.main:app --reload

Configuration (environment variables):
    PC_API_MOCK=1          serve clearly marked mock data, no database needed
    PC_PG_DSN              PostgreSQL connection string
    PC_NEO4J_URI / PC_NEO4J_USER / PC_NEO4J_PASSWORD
    PC_CLUSTERS_PATH       output of graph.clusters (default graph/out/clusters.json)
    PC_QUERY_ENCODER       specter2 (default) or none; see api/query_encoder.py

/search and /papers/{id}/related use Person 2's db/retrieval search layer.
/opportunities/{id}/explain and /rag/query depend on rag/ and return 501 until it exists.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from api import schemas
from api.query_encoder import QueryEncoder, get_query_encoder
from api.repository import PostgresRepository, Repository, VectorSearchUnavailable

DISCLAIMER = (
    "Candidate research opportunities are combinations weakly represented in the analyzed corpus. "
    "They are signals for human review, not proof of a research gap."
)

app = FastAPI(title="paper-compass API", version="0.1.0")


@lru_cache(maxsize=1)
def get_repo() -> Repository:
    if os.environ.get("PC_API_MOCK") == "1":
        from api.mock_data import MockRepository

        return MockRepository()
    dsn = os.environ.get("PC_PG_DSN")
    if not dsn:
        raise RuntimeError("set PC_PG_DSN, or PC_API_MOCK=1 for mock data")
    driver = None
    if os.environ.get("PC_NEO4J_URI"):
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.environ["PC_NEO4J_URI"],
            auth=(os.environ.get("PC_NEO4J_USER", "neo4j"), os.environ.get("PC_NEO4J_PASSWORD", "")),
        )
    clusters = os.environ.get("PC_CLUSTERS_PATH", str(Path(__file__).resolve().parent.parent / "graph" / "out" / "clusters.json"))
    return PostgresRepository(dsn, driver, clusters)


def _disclaimer() -> str:
    if os.environ.get("PC_API_MOCK") == "1":
        from api.mock_data import MOCK_NOTICE

        return f"{MOCK_NOTICE}. {DISCLAIMER}"
    return DISCLAIMER


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
def get_paper(paper_id: str, repo: Repository = Depends(get_repo)):
    paper = repo.get_paper(paper_id)
    if paper is None:
        raise HTTPException(404, "paper not found")
    return paper


@app.get("/papers/{paper_id}/graph", response_model=schemas.PaperGraph)
def get_paper_graph(paper_id: str, limit: int = Query(200, ge=1, le=1000), repo: Repository = Depends(get_repo)):
    try:
        graph = repo.paper_graph(paper_id, limit)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
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
    query: str = Field(min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    year_min: int | None = None
    # optional extras, passed through to db.retrieval.search (provisional, O10)
    year_max: int | None = None
    venues: list[str] | None = None
    methods: list[str] | None = None
    datasets: list[str] | None = None
    tasks: list[str] | None = None
    match: Literal["same_experiment", "any"] = "same_experiment"
    # auto: vector search when a query encoder and matching paper embeddings exist, else keyword search
    mode: Literal["auto", "vector", "keyword"] = "auto"


@app.post("/search", response_model=schemas.SearchResponse)
def search(body: SearchRequest, repo: Repository = Depends(get_repo),
           encoder: QueryEncoder | None = Depends(get_query_encoder)):
    filters = body.model_dump(exclude={"query", "top_k", "mode"})
    mode, note = body.mode, None
    if mode == "auto":
        mode = "vector" if encoder is not None else "keyword"
        if encoder is None:
            note = "query encoder not available; used keyword search"
    if mode == "vector" and encoder is None:
        raise HTTPException(503, "query encoder not available (PC_QUERY_ENCODER=none or torch/transformers/adapters "
                                 "not installed); use mode=keyword")
    try:
        if mode == "vector":
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
    return {"query": body.query, "mode": mode, "note": note,
            "score_type": "cosine_similarity" if mode == "vector" else "ts_rank", **out}


@app.get("/papers/{paper_id}/related", response_model=schemas.RelatedResponse)
def related(paper_id: str, top_k: int = Query(10, ge=1, le=100), year_min: int | None = None,
            year_max: int | None = None, repo: Repository = Depends(get_repo)):
    try:
        out = repo.related(paper_id, top_k, {"year_min": year_min, "year_max": year_max})
    except VectorSearchUnavailable as e:
        raise HTTPException(409, str(e))
    if out is None:
        raise HTTPException(404, "paper not found")
    return {"paper_id": paper_id, "score_type": "cosine_similarity", **out}


def _not_ready(owner_module: str):
    raise HTTPException(501, f"not implemented yet: depends on {owner_module} (Person 2)")


@app.post("/opportunities/{opportunity_id}/explain")
def explain(opportunity_id: int):
    _not_ready("rag/")


@app.post("/rag/query")
def rag_query():
    _not_ready("rag/")
