import pytest
from fastapi.testclient import TestClient

from api.main import app, get_repo
from api.mock_data import MockRepository


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


@pytest.mark.parametrize("method,path", [
    ("post", "/search"), ("get", "/papers/X/related"), ("post", "/opportunities/1/explain"), ("post", "/rag/query"),
])
def test_person2_endpoints_not_ready(client, method, path):
    kwargs = {"json": {"query": "q"}} if path == "/search" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 501
