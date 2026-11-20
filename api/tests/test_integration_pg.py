"""PostgresRepository search methods against a real PostgreSQL with pgvector, using Person 2's
db/retrieval search layer. Skipped unless PC_TEST_PG_DSN is set (see scoring/tests/test_integration_pg.py).

Same throwaway schema and MOCK rows as the scoring integration tests: papers MOCK-P*, all embedded
with model 'MOCK', paper i's vector peaking at dimension i.
"""

from __future__ import annotations

import os
import uuid

import pytest

from api.repository import PostgresRepository, VectorSearchUnavailable
from scoring.tests.test_integration_pg import _load_mock, _vec, contract_sql

DSN = os.environ.get("PC_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="PC_TEST_PG_DSN not set")


class VecEncoder:
    """Returns the stored vector of paper index i, so the nearest paper is known."""

    def __init__(self, i: int, model_string: str = "MOCK"):
        self.i, self.model_string = i, model_string

    def embed(self, texts):
        return [[float(x) for x in _vec(self.i).strip("[]").split(",")] for _ in texts]


@pytest.fixture
def repo():
    psycopg = pytest.importorskip("psycopg")
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    schema = f"pc_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}, public")
        c.execute(contract_sql())
        _load_mock(c)
        papers = [r[0] for r in c.execute("SELECT paper_id FROM paper ORDER BY paper_id").fetchall()]
        dsn = make_conninfo(**{**conninfo_to_dict(DSN), "options": f"-csearch_path={schema},public"})
        try:
            yield PostgresRepository(dsn), papers, c
        finally:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


def test_vector_search_finds_the_matching_paper(repo):
    r, papers, _ = repo
    out = r.vector_search(VecEncoder(0), "anything", 3, {})
    assert out["model"] == "MOCK"
    assert out["results"][0]["paper_id"] == papers[0]
    assert out["results"][0]["score"] == pytest.approx(1.0)
    assert [h["score"] for h in out["results"]] == sorted((h["score"] for h in out["results"]), reverse=True)
    assert {"methods", "datasets", "tasks"} <= set(out["results"][0])


def test_vector_search_refuses_other_model(repo):
    r, _, _ = repo
    with pytest.raises(VectorSearchUnavailable):
        r.vector_search(VecEncoder(0, model_string="OTHER"), "anything", 3, {})


def test_vector_search_without_embeddings(repo):
    r, _, c = repo
    c.execute("UPDATE paper SET embedding = NULL, embedding_model = NULL")
    with pytest.raises(VectorSearchUnavailable):
        r.vector_search(VecEncoder(0), "anything", 3, {})


def test_keyword_search(repo):
    r, papers, _ = repo
    out = r.keyword_search("mock", 10, {"year_min": None, "year_max": None})
    assert out["model"] is None
    assert {h["paper_id"] for h in out["results"]} == set(papers)


def test_related_excludes_the_paper(repo):
    r, papers, c = repo
    out = r.related(papers[1], 10, {})
    ids = [h["paper_id"] for h in out["results"]]
    assert papers[1] not in ids and set(ids) == set(papers) - {papers[1]}
    # paper i's vector shares dimension i+1 with paper i+1 and dimension i with paper i-1
    assert ids[0] in (papers[0], papers[2])
    assert r.related("MOCK-NOPE", 10, {}) is None
    c.execute("UPDATE paper SET embedding = NULL WHERE paper_id = %s", (papers[1],))
    with pytest.raises(VectorSearchUnavailable):
        r.related(papers[1], 10, {})


def test_explain_uses_rag_evidence(repo):
    from scoring.pipeline import run

    r, _, c = repo
    # same scenario as scoring's pipeline test: one opportunity, (m1, d2), observed 1 (P1), expected 4/3
    (opp_id,) = run(c, "method_dataset", min_support=1, k=5.0, cutoff_year=None)
    out = r.explain(opp_id)
    corpus = out["evidence"]["corpus"]
    assert (corpus["universe_size"], corpus["n_a"], corpus["n_b"], corpus["observed"]) == (3, 2, 2, 1)
    assert corpus["expected"] == pytest.approx(4 / 3)
    # scoring's counts and rag's counts agree (same-universe rule)
    observed, expected = c.execute("SELECT observed_count, expected_count FROM opportunity WHERE opportunity_id = %s",
                                   (opp_id,)).fetchone()
    assert (observed, expected) == (corpus["observed"], pytest.approx(corpus["expected"]))
    assert [p["paper_id"] for p in out["evidence"]["roles"]["nearest_existing"]][:1] == ["MOCK-P1"]
    assert "[paper:MOCK-P1]" in out["summary"]
    assert out["citation_check"]["ok"] is True
    assert r.explain(10**9) is None


def test_explain_rejects_non_pair_opportunity(repo):
    from scoring.pipeline import run

    r, _, c = repo
    (opp_id,) = run(c, "method_dataset", min_support=1, k=5.0, cutoff_year=None)
    c.execute("UPDATE opportunity SET task_id = 1 WHERE opportunity_id = %s", (opp_id,))
    with pytest.raises(ValueError):
        r.explain(opp_id)
