"""Tests for search_hybrid (vector + keyword fused with reciprocal rank fusion) and the CLI --mode option.

All papers and vectors are synthetic, in a throwaway database. The query vector is the unit vector e0; a paper's
vector is a*e0 + b*e1, so its cosine to the query is a / sqrt(a*a + b*b) and the vector ranking is known exactly.
The keyword ranking is controlled by how often the word "alpha" occurs in the abstract (ts_rank grows with it).
"""
import json
import math

import psycopg
import pytest

from retrieval import cli
from retrieval.search import keyword_search, search, search_hybrid

DIM = 768
K = 60


def vec(a, b=0.0):
    v = [0.0] * DIM
    v[0], v[1] = a, b
    return v


def literal(v):
    return "[" + ",".join(repr(x) for x in v) + "]"


QUERY = vec(1.0)


def add(conn, paper_id, title, abstract="", year=2020, embedding=None):
    conn.execute("INSERT INTO paper (paper_id, title, abstract, year, embedding) VALUES (%s, %s, %s, %s, %s)",
                 (paper_id, title, abstract, year, literal(embedding) if embedding is not None else None))


def ids_of(results):
    return [r["paper_id"] for r in results]


def rrf(*ranks):
    return sum(1.0 / (K + r) for r in ranks if r is not None)


@pytest.fixture
def fixture(conn):
    """Vector order A, B, C, D (E has no embedding). Keyword order C, A, E (B and D never say 'alpha')."""
    add(conn, "A", "Paper A", "alpha alpha", embedding=vec(1.0, 0.1))
    add(conn, "B", "Paper B", "nothing here", embedding=vec(1.0, 0.5))
    add(conn, "C", "Paper C", "alpha alpha alpha alpha", embedding=vec(1.0, 1.0))
    add(conn, "D", "Paper D", "nothing either", embedding=vec(1.0, 2.0))
    add(conn, "E", "Paper E", "alpha", embedding=None)


# --- fusion order, ranks and scores -------------------------------------------------------------------------

def test_fusion_order_ranks_and_scores_on_a_small_fixture(conn, fixture):
    assert ids_of(search(conn, QUERY, top_k=10)) == ["A", "B", "C", "D"]
    assert ids_of(keyword_search(conn, "alpha", top_k=10)) == ["C", "A", "E"]
    results = search_hybrid(conn, "alpha", QUERY, top_k=10)
    assert ids_of(results) == ["A", "C", "B", "E", "D"]
    by_id = {r["paper_id"]: r for r in results}
    assert [(by_id[p]["vector_rank"], by_id[p]["keyword_rank"]) for p in "ABCDE"] == [
        (1, 2), (2, None), (3, 1), (4, None), (None, 3)]
    assert by_id["A"]["fused_score"] == pytest.approx(rrf(1, 2))
    assert by_id["C"]["fused_score"] == pytest.approx(rrf(3, 1))
    assert by_id["E"]["fused_score"] == pytest.approx(rrf(None, 3))
    assert [r["fused_score"] for r in results] == sorted((r["fused_score"] for r in results), reverse=True)


def test_result_keys(conn, fixture):
    row = search_hybrid(conn, "alpha", QUERY, top_k=1)[0]
    assert set(row) == {"paper_id", "title", "year", "venue", "vector_rank", "keyword_rank", "fused_score",
                        "vector_similarity", "keyword_score"}
    assert row["vector_similarity"] == pytest.approx(1.0 / math.sqrt(1.0 + 0.01), abs=1e-5)


def test_a_paper_found_by_only_one_method_still_appears(conn, fixture):
    results = search_hybrid(conn, "alpha", QUERY, top_k=10)
    by_id = {r["paper_id"]: r for r in results}
    assert by_id["E"]["vector_rank"] is None and by_id["E"]["vector_similarity"] is None   # keyword only
    assert by_id["B"]["keyword_rank"] is None and by_id["B"]["keyword_score"] is None      # vector only


def test_equal_fused_scores_are_ordered_by_the_smaller_paper_id(conn):
    # X is vector rank 1 only, Y is keyword rank 1 only: the same fused score 1/61
    for vector_only, keyword_only in (("A_vec", "B_kw"), ("B_vec", "A_kw")):
        conn.execute("DELETE FROM paper")
        add(conn, vector_only, "vector only", "no match", embedding=vec(1.0))
        add(conn, keyword_only, "keyword only", "alpha", embedding=None)
        results = search_hybrid(conn, "alpha", QUERY, top_k=10)
        assert results[0]["fused_score"] == pytest.approx(results[1]["fused_score"])
        assert ids_of(results) == sorted(ids_of(results)), "the smaller paper_id comes first on a tie"


def test_k_results_are_returned_when_enough_candidates_exist(conn):
    for i in range(30):
        add(conn, f"V{i:02d}", f"vector paper {i}", "no keyword", embedding=vec(1.0, 0.01 * (i + 1)))
    for i in range(30):
        add(conn, f"K{i:02d}", f"keyword paper {i}", "alpha " * (i + 1), embedding=None)
    assert len(search_hybrid(conn, "alpha", QUERY, top_k=10, n_candidates=20)) == 10
    assert len(search_hybrid(conn, "alpha", QUERY, top_k=40, n_candidates=50)) == 40
    assert len(search_hybrid(conn, "alpha", QUERY, top_k=100, n_candidates=50)) == 60   # all there is


def test_only_the_top_n_of_each_method_are_fused(conn, fixture):
    results = search_hybrid(conn, "alpha", QUERY, top_k=10, n_candidates=2)
    # vector top 2 = A, B; keyword top 2 = C, A; D and E fall outside both lists
    assert set(ids_of(results)) == {"A", "B", "C"}
    assert {r["paper_id"]: r["vector_rank"] for r in results} == {"A": 1, "B": 2, "C": None}


def test_the_year_filter_applies_to_both_lists(conn, fixture):
    conn.execute("UPDATE paper SET year = 2010 WHERE paper_id IN ('A', 'D')")
    results = search_hybrid(conn, "alpha", QUERY, top_k=10, year_min=2015)
    assert set(ids_of(results)) == {"B", "C", "E"}
    assert all(r["year"] >= 2015 for r in results)
    results = search_hybrid(conn, "alpha", QUERY, top_k=10, year_max=2015)
    assert set(ids_of(results)) == {"A", "D"}


def test_same_title_collapse_keeps_the_best_fused_record_and_still_returns_k(conn):
    add(conn, "T1", "Same Title!", "alpha alpha", embedding=vec(1.0, 0.1))
    add(conn, "T2", "same title", "alpha", embedding=vec(1.0, 0.2))
    add(conn, "T3", "SAME TITLE", "alpha", embedding=vec(1.0, 0.3))
    for i in range(6):
        add(conn, f"U{i}", f"unique title {i}", "alpha", embedding=vec(1.0, 1.0 + i))
    plain = search_hybrid(conn, "alpha", QUERY, top_k=4)
    assert sum(1 for r in plain if r["title"].lower().startswith("same title")) >= 2
    collapsed = search_hybrid(conn, "alpha", QUERY, top_k=4, collapse_same_title=True)
    assert len(collapsed) == 4
    assert [r["paper_id"] for r in collapsed if r["paper_id"].startswith("T")] == ["T1"]
    assert len({r["title"].lower().strip("! ") for r in collapsed}) == 4


def test_blank_text_gives_the_vector_list_only(conn, fixture):
    results = search_hybrid(conn, "   ", QUERY, top_k=10)
    assert ids_of(results) == ["A", "B", "C", "D"] and all(r["keyword_rank"] is None for r in results)


@pytest.mark.parametrize("kwargs", [{"top_k": 0}, {"n_candidates": 0}, {"rrf_k": 0}, {"collapse_same_title": "yes"}])
def test_bad_parameters_are_rejected(conn, fixture, kwargs):
    with pytest.raises(ValueError):
        search_hybrid(conn, "alpha", QUERY, **kwargs)


def test_bad_text_and_vector_are_rejected(conn, fixture):
    with pytest.raises(ValueError):
        search_hybrid(conn, 5, QUERY)
    with pytest.raises(ValueError):
        search_hybrid(conn, "alpha", [1.0, 2.0])


# --- existing behaviour is unchanged ---------------------------------------------------------------------------

def test_search_and_keyword_search_still_return_their_own_keys(conn, fixture):
    assert set(search(conn, QUERY, top_k=1)[0]) == {"paper_id", "title", "year", "venue", "similarity"}
    assert set(keyword_search(conn, "alpha", top_k=1)[0]) == {"paper_id", "title", "year", "venue", "score"}


@pytest.fixture
def connect_to_test_db(test_db_conninfo):
    return lambda dbname: psycopg.connect(test_db_conninfo, autocommit=True)


def run_cli(connect_to_test_db, capsys, *argv):
    code = cli.main(list(argv), connect_fn=connect_to_test_db)
    return code, capsys.readouterr()


def test_the_cli_default_mode_is_vector_and_unchanged(connect_to_test_db, conn, fixture, tmp_path, capsys):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(QUERY), encoding="utf-8")
    code, plain = run_cli(connect_to_test_db, capsys, "search", "--vector-file", str(path), "--top-k", "4")
    code2, explicit = run_cli(connect_to_test_db, capsys, "search", "--vector-file", str(path), "--top-k", "4",
                              "--mode", "vector")
    assert code == code2 == 0 and plain.out == explicit.out
    assert [line.split()[2] for line in plain.out.splitlines() if line.strip()[:1].isdigit()] == ["A", "B", "C", "D"]


def test_the_cli_keyword_mode_and_the_keyword_command_agree(connect_to_test_db, conn, fixture, capsys):
    code, via_mode = run_cli(connect_to_test_db, capsys, "search", "--mode", "keyword", "--text", "alpha")
    code2, via_command = run_cli(connect_to_test_db, capsys, "keyword", "alpha")
    assert code == code2 == 0 and via_mode.out == via_command.out


def test_the_cli_hybrid_mode_shows_ranks_and_fused_scores(connect_to_test_db, conn, fixture, tmp_path, capsys):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(QUERY), encoding="utf-8")
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "hybrid", "--vector-file", str(path),
                        "--text", "alpha", "--top-k", "5")
    assert code == 0
    lines = [line for line in out.out.splitlines() if line.strip()[:1].isdigit()]
    assert [line.split()[2] for line in lines] == ["A", "C", "B", "E", "D"]
    assert "vector rank 1" in lines[0] and "keyword rank 2" in lines[0] and "fused" in lines[0]
    assert "keyword rank -" in next(line for line in lines if " B " in line)


def test_the_cli_modes_ask_for_what_they_need(connect_to_test_db, conn, fixture, tmp_path, capsys):
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "hybrid", "--text", "alpha")
    assert code == 1 and "--vector-file" in out.err
    path = tmp_path / "q.json"
    path.write_text(json.dumps(QUERY), encoding="utf-8")
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "hybrid", "--vector-file", str(path))
    assert code == 1 and "--text" in out.err
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "keyword")
    assert code == 1 and "--text" in out.err
    code, out = run_cli(connect_to_test_db, capsys, "search")
    assert code == 1 and "--vector-file" in out.err


def test_the_cli_hybrid_mode_refuses_filters_it_does_not_apply(connect_to_test_db, conn, fixture, tmp_path, capsys):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(QUERY), encoding="utf-8")
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "hybrid", "--vector-file", str(path),
                        "--text", "alpha", "--method", "Anything")
    assert code == 1 and "--method" in out.err and "year filters" in out.err
    code, out = run_cli(connect_to_test_db, capsys, "search", "--mode", "hybrid", "--vector-file", str(path),
                        "--text", "alpha", "--year-min", "2015", "--n-candidates", "3")
    assert code == 0
