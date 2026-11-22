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


class QueryEncoderLikeSpecter2(VecEncoder):
    """Like the real query encoder: its own model_string (the adhoc_query adapter), but it queries the paper space."""

    def __init__(self, i, paper_model_string):
        super().__init__(i, model_string="MOCK-base+adhoc_query")
        self.paper_model_string = paper_model_string


def test_vector_search_compares_the_paper_side_model_not_the_query_adapter_name(repo):
    r, papers, _ = repo
    out = r.vector_search(QueryEncoderLikeSpecter2(0, "MOCK"), "anything", 3, {})
    assert out["model"] == "MOCK-base+adhoc_query"            # reports what encoded the query
    assert out["results"][0]["paper_id"] == papers[0]
    with pytest.raises(VectorSearchUnavailable):                # the paper space differs: refuse
        r.vector_search(QueryEncoderLikeSpecter2(0, "SOME-OTHER-MODEL"), "anything", 3, {})


def test_hybrid_search_fuses_vector_and_keyword_and_keeps_entities(repo):
    r, papers, _ = repo
    out = r.hybrid_search(VecEncoder(0), "mock", 5, {"year_min": None, "year_max": None})
    ids = [h["paper_id"] for h in out["results"]]
    assert len(ids) == 5 and len(set(ids)) == 5
    top = out["results"][0]
    assert top["paper_id"] == papers[0]                         # best vector rank, and in the keyword list too
    assert top["vector_rank"] == 1 and top["keyword_rank"] is not None
    assert top["score"] == pytest.approx(1 / 61 + 1 / (60 + top["keyword_rank"]))   # reciprocal rank fusion, k = 60
    assert [h["score"] for h in out["results"]] == sorted((h["score"] for h in out["results"]), reverse=True)
    assert {"methods", "datasets", "tasks"} <= set(top)
    # a query with no keyword hit still returns the vector side
    only_vec = r.hybrid_search(VecEncoder(1), "zzzznotaword", 3, {})
    assert only_vec["results"][0]["paper_id"] == papers[1] and only_vec["results"][0]["keyword_rank"] is None


def test_hybrid_search_refuses_other_model_and_unsupported_filters(repo):
    r, _, _ = repo
    with pytest.raises(VectorSearchUnavailable):
        r.hybrid_search(VecEncoder(0, model_string="OTHER"), "mock", 3, {})
    for bad in ({"methods": ["MOCK method 1"]}, {"venues": ["x"]}, {"datasets": ["d"]}, {"tasks": ["t"]}):
        with pytest.raises(ValueError, match="hybrid"):
            r.hybrid_search(VecEncoder(0), "mock", 3, bad)


def test_clusters_are_computed_once_when_the_file_is_missing_then_read_from_it(repo, tmp_path):
    r, _, _ = repo
    r.clusters_path = tmp_path / "out" / "clusters.json"
    assert not r.clusters_path.exists()
    first = r.clusters()                                   # computes, writes the file
    assert r.clusters_path.exists()
    assert {"method", "n_papers", "n_noise", "clusters", "labels", "min_cluster_size", "pca_dims"} <= set(first)
    assert first["n_papers"] == 5 and first["min_cluster_size"] == 15 and first["pca_dims"] == 20
    assert first["clusters"] == [] and first["n_noise"] == 5   # 5 mock papers are too few for a 15-paper cluster
    r.clusters_path.write_text('{"marker": 1}', encoding="utf-8")
    assert r.clusters() == {"marker": 1}                  # an existing file is used as it is


def test_clusters_without_any_embedding_says_what_to_run(repo, tmp_path):
    r, _, c = repo
    r.clusters_path = tmp_path / "clusters.json"
    c.execute("UPDATE paper SET embedding = NULL, embedding_model = NULL")
    with pytest.raises(FileNotFoundError, match="graph.clusters"):
        r.clusters()


def test_health_reports_counts_and_what_to_run_when_something_is_missing(repo):
    r, papers, _ = repo
    h = r.health()
    assert h["postgres"] == {"ok": True, "papers": 5, "with_embeddings": 5, "experiments": h["postgres"]["experiments"],
                             "opportunities": 0}
    assert h["neo4j"] == {"configured": False, "ok": None}
    assert any("api.prepare_demo" in n for n in h["notes"])         # no opportunities: says what to run


def test_health_with_nothing_embedded_says_so(repo):
    r, _, c = repo
    c.execute("UPDATE paper SET embedding = NULL, embedding_model = NULL")
    h = r.health()
    assert h["postgres"]["with_embeddings"] == 0
    assert any("embed" in n.lower() for n in h["notes"])


def test_health_when_postgres_is_unreachable_does_not_raise_or_leak_the_password():
    bad = PostgresRepository("postgresql://someone:s3cretpw@127.0.0.1:1/none?connect_timeout=2")
    h = bad.health()
    assert h["postgres"]["ok"] is False and "s3cretpw" not in str(h)
    assert any("PostgreSQL" in n for n in h["notes"])


def test_prepare_scores_once_and_skips_when_opportunities_exist(repo):
    from api.prepare_demo import prepare_scoring

    r, _, _ = repo
    import psycopg
    with psycopg.connect(r.pg_dsn) as conn:
        first = prepare_scoring(conn, pair_type="method_dataset", min_support=1, min_sparsity=0.0, k=5.0)
        conn.commit()
        assert first["action"] == "scored" and first["stored"] == 1
        second = prepare_scoring(conn, pair_type="method_dataset", min_support=1, min_sparsity=0.0, k=5.0)
        assert second["action"] == "kept" and second["existing"] == 1
        forced = prepare_scoring(conn, pair_type="method_dataset", min_support=1, min_sparsity=0.0, k=5.0, force=True)
        conn.commit()
        assert forced["action"] == "scored" and conn.execute("SELECT COUNT(*) FROM opportunity").fetchone()[0] == 1
