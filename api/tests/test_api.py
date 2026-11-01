import pytest
from fastapi.testclient import TestClient

from api.main import app, get_query_encoder, get_repo
from api.mock_data import MockRepository
from api.repository import VectorSearchUnavailable


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PC_API_MOCK", "1")
    app.dependency_overrides[get_repo] = lambda: MockRepository()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_opportunities_matches_contract(client):
    r = client.get("/opportunities")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert "MOCK" in body["disclaimer"]
    opp = body["items"][0]
    assert set(opp) == {"opportunity_id", "elements", "corpus", "observed_count", "expected_count",
                        "signals", "confidence", "score", "weights_version", "evidence"}
    # unimplemented signals are null, not omitted
    assert opp["signals"]["graph_bridge_strength"] is None
    assert set(opp["evidence"]) == {"supports_A", "supports_B", "bridge", "nearest_existing"}


def test_opportunity_filters(client):
    assert client.get("/opportunities", params={"min_confidence": 0.9}).json()["total"] == 1
    assert client.get("/opportunities", params={"min_confidence": 2}).status_code == 422


def test_get_opportunity(client):
    assert client.get("/opportunities/1").json()["opportunity_id"] == 1
    assert client.get("/opportunities/999").status_code == 404


def test_paper_and_graph(client):
    assert client.get("/papers/MOCK-W1").json()["title"] == "MOCK paper 1"
    assert client.get("/papers/nope").status_code == 404
    g = client.get("/papers/MOCK-W1/graph").json()
    assert g["center"] == "Paper:MOCK-W1"
    assert g["edges"][0]["type"] == "USES_METHOD"


def test_landscape_trends_clusters(client):
    assert client.get("/landscape").json()["corpus"]["papers"] == 500
    assert client.get("/trends", params={"element_type": "method"}).json() == []
    assert client.get("/trends", params={"element_type": "author"}).status_code == 422
    assert client.get("/clusters").json()["clusters"] == []


@pytest.mark.parametrize("method,path", [("post", "/opportunities/1/explain"), ("post", "/rag/query")])
def test_rag_endpoints_not_ready(client, method, path):
    assert getattr(client, method)(path).status_code == 501


# --- /search and /papers/{id}/related -------------------------------------------

class FakeEncoder:
    model_string = "MOCK-encoder"

    def embed(self, texts):
        return [[1.0] + [0.0] * 767 for _ in texts]


class StubRepo(MockRepository):
    """Records calls; vector search can be made unavailable or invalid."""

    def __init__(self, vector_error=None):
        self.vector_error = vector_error
        self.calls = []

    def vector_search(self, encoder, text, top_k, filters):
        self.calls.append(("vector", filters))
        if self.vector_error:
            raise self.vector_error
        return super().vector_search(encoder, text, top_k, filters)

    def keyword_search(self, text, top_k, filters):
        self.calls.append(("keyword", filters))
        return super().keyword_search(text, top_k, filters)


@pytest.fixture
def use(monkeypatch):
    """use(repo, encoder) installs a repository and a query encoder for one test."""
    monkeypatch.setenv("PC_API_MOCK", "1")

    def install(repo, encoder):
        app.dependency_overrides[get_repo] = lambda: repo
        app.dependency_overrides[get_query_encoder] = lambda: encoder
        return TestClient(app)

    yield install
    app.dependency_overrides.clear()


def test_search_auto_uses_vector_when_encoder_exists(use):
    repo = StubRepo()
    body = use(repo, FakeEncoder()).post("/search", json={"query": "distillation", "top_k": 3,
                                                          "year_min": 2020, "methods": ["KD"]}).json()
    assert (body["mode"], body["score_type"], body["model"], body["note"]) == ("vector", "cosine_similarity", "MOCK", None)
    assert len(body["results"]) == 3
    assert set(body["results"][0]) == {"paper_id", "title", "year", "venue", "score", "methods", "datasets", "tasks"}
    # filters reach the search layer unchanged
    assert repo.calls == [("vector", {"year_min": 2020, "year_max": None, "venues": None, "methods": ["KD"],
                                      "datasets": None, "tasks": None, "match": "same_experiment"})]


def test_search_auto_falls_back_to_keyword_without_encoder(use):
    body = use(StubRepo(), None).post("/search", json={"query": "q"}).json()
    assert (body["mode"], body["score_type"], body["model"]) == ("keyword", "ts_rank", None)
    assert "encoder not available" in body["note"]


def test_search_auto_falls_back_when_vectors_unusable(use):
    repo = StubRepo(vector_error=VectorSearchUnavailable("no paper has an embedding yet"))
    body = use(repo, FakeEncoder()).post("/search", json={"query": "q"}).json()
    assert body["mode"] == "keyword"
    assert body["note"].startswith("no paper has an embedding yet")
    assert [c[0] for c in repo.calls] == ["vector", "keyword"]


def test_search_explicit_vector_errors(use):
    assert use(StubRepo(), None).post("/search", json={"query": "q", "mode": "vector"}).status_code == 503
    repo = StubRepo(vector_error=VectorSearchUnavailable("different model"))
    assert use(repo, FakeEncoder()).post("/search", json={"query": "q", "mode": "vector"}).status_code == 409


def test_search_explicit_keyword_skips_encoder(use):
    repo = StubRepo()
    assert use(repo, FakeEncoder()).post("/search", json={"query": "q", "mode": "keyword"}).json()["mode"] == "keyword"
    assert [c[0] for c in repo.calls] == ["keyword"]


def test_search_validation(use):
    c = use(StubRepo(), None)
    assert c.post("/search", json={"query": ""}).status_code == 422
    assert c.post("/search", json={"query": "q", "top_k": 0}).status_code == 422
    assert c.post("/search", json={"query": "q", "match": "all"}).status_code == 422
    # errors raised by the search layer itself become 422
    bad = StubRepo(vector_error=ValueError("year_min must be an integer"))
    assert use(bad, FakeEncoder()).post("/search", json={"query": "q"}).status_code == 422


def test_related(client):
    body = client.get("/papers/MOCK-W1/related", params={"top_k": 3}).json()
    assert (body["paper_id"], body["score_type"]) == ("MOCK-W1", "cosine_similarity")
    ids = [r["paper_id"] for r in body["results"]]
    assert len(ids) == 3 and "MOCK-W1" not in ids
    assert client.get("/papers/nope/related").status_code == 404
    assert client.get("/papers/MOCK-W1/related", params={"top_k": 0}).status_code == 422


def test_related_without_embedding(use):
    class NoEmbedding(MockRepository):
        def related(self, paper_id, top_k, filters):
            raise VectorSearchUnavailable("this paper has no embedding")

    assert use(NoEmbedding(), None).get("/papers/MOCK-W1/related").status_code == 409
