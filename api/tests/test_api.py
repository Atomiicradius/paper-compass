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


def test_explain(client):
    r = client.post("/opportunities/1/explain")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"opportunity_id", "evidence", "summary", "summary_source", "summary_fallback_reason",
                         "citation_check", "disclaimer"}
    assert body["summary_source"] == "template" and body["summary_fallback_reason"] is None  # the default
    assert set(body["evidence"]["roles"]) == {"supports_A", "supports_B", "bridge", "nearest_existing"}
    assert "[paper:MOCK-W5]" in body["summary"]
    assert body["citation_check"]["ok"] is True
    assert "MOCK" in body["disclaimer"]
    assert client.post("/opportunities/999/explain").status_code == 404


def test_rag_query_not_ready(client):
    assert client.post("/rag/query").status_code == 501


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
                                      "datasets": None, "tasks": None, "match": "same_experiment",
                                      "collapse_same_title": False})]


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


# --- the optional LLM explanation: off by default, never calls the network in these tests -----------------------

@pytest.fixture
def no_llm_keys(monkeypatch, tmp_path):
    """No key anywhere (environment or .env), so nothing here can reach a model."""
    from rag import llm_summary
    for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "PC_LLM_PROVIDER", "PC_LLM_MODEL", "PC_LLM_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_summary, "ENV_FILE", tmp_path / "no.env")


def test_explain_is_the_template_by_default(client, no_llm_keys):
    body = client.post("/opportunities/1/explain").json()
    assert body["summary_source"] == "template" and body["summary_fallback_reason"] is None


def test_explain_with_the_option_on_but_no_key_falls_back_to_the_same_template(client, no_llm_keys, monkeypatch):
    plain = client.post("/opportunities/1/explain").json()
    monkeypatch.setenv("PC_LLM_SUMMARY", "1")
    body = client.post("/opportunities/1/explain").json()
    assert body["summary_source"] == "template" and body["summary_fallback_reason"] == "no key"
    assert body["summary"] == plain["summary"] and body["citation_check"]["ok"] is True


def test_explain_uses_a_good_llm_text_and_checks_it_again(client, no_llm_keys, monkeypatch):
    from rag import llm_summary
    text = ("What the corpus shows\nThe pair is seen in a few papers [paper:MOCK-W5].\n\n"
            "What the system infers\nPotentially underexplored in the analyzed corpus; the counts depend on the "
            "extraction and on the analyzed corpus.")
    real = llm_summary.explanation_text
    monkeypatch.setattr("rag.llm_summary.explanation_text", lambda evidence, **kw: real(evidence, use_llm=True,
                        complete=lambda prompt: text, env={}, env_file=llm_summary.ENV_FILE))
    body = client.post("/opportunities/1/explain").json()
    assert body["summary_source"] == "llm" and body["summary"] == text
    assert body["citation_check"]["ok"] is True and body["citation_check"]["cited"] == ["MOCK-W5"]


def test_explain_falls_back_when_the_llm_cites_an_unknown_paper(client, no_llm_keys, monkeypatch):
    from rag import llm_summary
    bad = "What the corpus shows\nSee [paper:NOT-IN-THE-EVIDENCE].\n\nWhat the system infers\nPotentially underexplored."
    real = llm_summary.explanation_text
    monkeypatch.setattr("rag.llm_summary.explanation_text", lambda evidence, **kw: real(evidence, use_llm=True,
                        complete=lambda prompt: bad, env={}, env_file=llm_summary.ENV_FILE))
    body = client.post("/opportunities/1/explain").json()
    assert body["summary_source"] == "template" and body["summary_fallback_reason"] == "citation check"
    assert "NOT-IN-THE-EVIDENCE" not in body["summary"] and body["citation_check"]["ok"] is True


def test_graph_neo4j_error_is_503(monkeypatch):
    from neo4j.exceptions import AuthError

    class BrokenGraph(MockRepository):
        def paper_graph(self, paper_id, limit):
            raise AuthError("Unsupported authentication token")

    monkeypatch.setenv("PC_API_MOCK", "1")
    app.dependency_overrides[get_repo] = lambda: BrokenGraph()
    try:
        r = TestClient(app).get("/papers/MOCK-W1/graph")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "Neo4j" in r.json()["detail"]


def test_missing_configuration_is_503_with_reason(monkeypatch):
    monkeypatch.delenv("PC_PG_DSN", raising=False)
    monkeypatch.delenv("PC_API_MOCK", raising=False)
    monkeypatch.setattr("api.main._settings_from_env_file", lambda *a, **k: {})   # no db/.env fallback
    get_repo.cache_clear()
    try:
        r = TestClient(app).get("/opportunities")
    finally:
        get_repo.cache_clear()
    assert r.status_code == 503
    assert "PC_PG_DSN" in r.json()["detail"]


def test_dsn_falls_back_to_db_env_file(tmp_path, monkeypatch):
    from api.main import _settings_from_env_file

    env = tmp_path / ".env"
    env.write_text("POSTGRES_USER=u\nPOSTGRES_PASSWORD=p w\nPOSTGRES_PORT=55432\nNEO4J_USER=neo4j\nNEO4J_PASSWORD=n\n")
    monkeypatch.delenv("PC_PG_DBNAME", raising=False)
    s = _settings_from_env_file(env)
    assert s["PC_PG_DSN"] == "postgresql://u:p%20w@127.0.0.1:55432/pc_pilot"
    assert s["PC_NEO4J_URI"] == "bolt://127.0.0.1:7687" and s["PC_NEO4J_PASSWORD"] == "n"
    monkeypatch.setenv("PC_PG_DBNAME", "other")
    assert _settings_from_env_file(env)["PC_PG_DSN"].endswith("/other")


def test_env_file_missing_gives_nothing(tmp_path):
    from api.main import _settings_from_env_file

    assert _settings_from_env_file(tmp_path / "nope.env") == {}


# --- hostile / malformed input must give 4xx, never 500 ---------------------------------

@pytest.mark.parametrize("path", [
    "/papers/W%00x", "/papers/W%00x/graph", "/papers/W%00x/related",
])
def test_nul_in_paper_id_is_rejected(client, path):
    assert client.get(path).status_code == 422


def test_overlong_paper_id_is_rejected(client):
    assert client.get("/papers/" + "A" * 500).status_code == 422


@pytest.mark.parametrize("body", [
    {"query": "a\u0000b"},
    {"query": "   "},
    {"query": "\t\n"},
    {"query": "x", "venues": ["a\u0000b"]},
    {"query": "x", "methods": ["a\u0000b"]},
    {"query": "x", "datasets": ["a\u0000b"]},
    {"query": "x", "tasks": ["a\u0000b"]},
    {"query": "x", "year_min": 2025, "year_max": 2020},
    {"query": "x" * 5001},
])
def test_bad_search_bodies_are_422(client, body):
    assert client.post("/search", json={**body, "mode": "keyword"}).status_code == 422


def test_good_search_bodies_still_work(client):
    r = client.post("/search", json={"query": "  back-translation ", "year_min": 2020, "year_max": 2020, "mode": "keyword"})
    assert r.status_code == 200
    assert client.post("/search", json={"query": "机器翻译 ñ é", "mode": "keyword"}).status_code == 200


def test_collapse_same_title_is_passed_through_to_the_repository(monkeypatch):
    seen = {}

    class Spy(MockRepository):
        def keyword_search(self, text, top_k, filters):
            seen.update(filters)
            return {"model": None, "results": []}

    monkeypatch.setenv("PC_API_MOCK", "1")
    app.dependency_overrides[get_repo] = lambda: Spy()
    try:
        c = TestClient(app)
        assert c.post("/search", json={"query": "x", "mode": "keyword"}).status_code == 200
        assert seen["collapse_same_title"] is False                      # default unchanged
        assert c.post("/search", json={"query": "x", "mode": "keyword", "collapse_same_title": True}).status_code == 200
        assert seen["collapse_same_title"] is True
        assert c.post("/search", json={"query": "x", "collapse_same_title": "maybe"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
