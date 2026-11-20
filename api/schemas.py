"""Response models. The Opportunity shape is the contract in data-and-contracts.md
section 4. The other shapes are provisional until open decision O10 is agreed
with the UI owner; once agreed they are copied into data-and-contracts.md.
"""

from __future__ import annotations

from pydantic import BaseModel


class Elements(BaseModel):
    method: str | None = None
    task: str | None = None
    dataset: str | None = None
    setting: str | None = None


class Corpus(BaseModel):
    papers: int
    cutoff_year: int


class Signals(BaseModel):
    sparsity: float | None = None
    semantic_compatibility: float | None = None
    temporal_activity: float | None = None
    graph_bridge_strength: float | None = None
    method_compatibility: float | None = None


class Evidence(BaseModel):
    supports_A: list[str] = []
    supports_B: list[str] = []
    bridge: list[str] = []
    nearest_existing: list[str] = []


class Opportunity(BaseModel):
    opportunity_id: int
    elements: Elements
    corpus: Corpus
    observed_count: int
    expected_count: float
    signals: Signals
    confidence: float | None
    score: float | None
    weights_version: str | None
    evidence: Evidence


class OpportunityList(BaseModel):
    total: int
    items: list[Opportunity]
    disclaimer: str


# --- provisional (O10) -----------------------------------------------------

class PaperSummary(BaseModel):
    paper_id: str
    title: str
    year: int | None = None


class Paper(PaperSummary):
    abstract: str | None = None
    doi: str | None = None
    venue: str | None = None
    authors: list[str] = []
    topics: list[str] = []
    methods: list[str] = []
    datasets: list[str] = []
    tasks: list[str] = []
    cites: list[str] = []
    cited_by: list[str] = []


class GraphNode(BaseModel):
    id: str
    label: str
    name: str | None = None
    year: int | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class PaperGraph(BaseModel):
    center: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class TrendItem(BaseModel):
    element_type: str
    element_id: int
    name: str
    yearly: dict[int, int]
    total: int
    recent_share: float
    growth: float
    label: str


class Landscape(BaseModel):
    corpus: Corpus
    papers_per_year: dict[int, int]
    n_clusters: int
    emerging: list[TrendItem]
    declining: list[TrendItem]
    weakly_connected_cluster_pairs: list[dict]
    bridge_papers: list[dict]
    disclaimer: str


class SearchHit(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    score: float
    methods: list[str] = []
    datasets: list[str] = []
    tasks: list[str] = []


class SearchResponse(BaseModel):
    query: str
    mode: str                  # "vector" or "keyword": the mode actually used
    score_type: str            # "cosine_similarity" (vector) or "ts_rank" (keyword)
    model: str | None          # embedding model of the query vector; null for keyword search
    note: str | None = None    # set when auto mode fell back to keyword search
    results: list[SearchHit]


class RelatedResponse(BaseModel):
    paper_id: str
    score_type: str
    model: str | None
    results: list[SearchHit]
