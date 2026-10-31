"""Tests for the retrieval evaluation metrics and runner. No database, no model: plain Python.

Every expected number below was worked out by hand (shown in the comments), not copied from the code.
Gain = 2^grade - 1, so grades 0, 1, 2 give gains 0, 1, 3. Discount at rank i (1-based) = 1 / log2(i + 1).
  log2(2) = 1, log2(3) = 1.5849625, log2(4) = 2, log2(5) = 2.3219281, log2(6) = 2.5849625
  discounts: rank1 = 1, rank2 = 0.6309298, rank3 = 0.5, rank4 = 0.4306766, rank5 = 0.3868528
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from retrieval.evaluation import metrics, runner
from retrieval.evaluation.metrics import (evaluate_query, mean, mean_reciprocal_rank, ndcg_at_k, precision_at_k,
                                          recall_at_k, reciprocal_rank)

DB_DIR = Path(__file__).resolve().parents[1]

# Example A: five results; a is highly relevant (2), c, e, f relevant (1), b judged not relevant (0).
# f is relevant but never retrieved. d is not judged at all (counts as 0).
RANKED_A = ["a", "b", "c", "d", "e"]
JUDGED_A = {"a": 2, "b": 0, "c": 1, "e": 1, "f": 1}      # 4 relevant papers: a, c, e, f


# --- precision, recall -------------------------------------------------------------------------

def test_precision_at_k_hand_computed():
    # top 3 = a, b, c -> relevant a, c -> 2/3.  top 5 adds d (unjudged), e -> relevant a, c, e -> 3/5.
    assert precision_at_k(RANKED_A, JUDGED_A, 3) == pytest.approx(2 / 3)
    assert precision_at_k(RANKED_A, JUDGED_A, 5) == pytest.approx(0.6)
    assert precision_at_k(RANKED_A, JUDGED_A, 1) == 1.0       # top 1 = a (grade 2 counts as relevant)


def test_recall_at_k_hand_computed():
    # 4 relevant papers (a, c, e, f). top 3 finds a, c -> 2/4.  top 5 finds a, c, e -> 3/4 (f never retrieved).
    assert recall_at_k(RANKED_A, JUDGED_A, 3) == pytest.approx(0.5)
    assert recall_at_k(RANKED_A, JUDGED_A, 5) == pytest.approx(0.75)


def test_fewer_results_than_k_count_as_misses_for_precision():
    # 2 results, both relevant, k = 5: precision divides by k -> 2/5. Recall: 2 of 3 relevant -> 2/3.
    ranked, judged = ["a", "b"], {"a": 1, "b": 1, "c": 1}
    assert precision_at_k(ranked, judged, 5) == pytest.approx(0.4)
    assert recall_at_k(ranked, judged, 5) == pytest.approx(2 / 3)


def test_empty_ranking():
    assert precision_at_k([], {"a": 1}, 3) == 0.0
    assert recall_at_k([], {"a": 1}, 3) == 0.0
    assert reciprocal_rank([], {"a": 1}) == 0.0
    assert ndcg_at_k([], {"a": 1}, 3) == 0.0


# --- reciprocal rank / MRR ---------------------------------------------------------------------

def test_reciprocal_rank_hand_computed():
    assert reciprocal_rank(RANKED_A, JUDGED_A) == 1.0                         # a is at rank 1
    assert reciprocal_rank(["x", "y", "z"], {"z": 1}) == pytest.approx(1 / 3)  # first relevant at rank 3
    assert reciprocal_rank(["x", "y", "z"], {"z": 1}, k=2) == 0.0              # beyond the cutoff -> 0
    assert reciprocal_rank(["x", "y", "z"], {"y": 0, "z": 2}) == pytest.approx(1 / 3)   # y is judged 0


def test_mean_reciprocal_rank_skips_queries_without_relevant_papers():
    # RR = 1, 1/2, and the third query has no relevant paper (skipped). MRR = (1 + 0.5) / 2 = 0.75
    runs = [(["a"], {"a": 1}), (["x", "y"], {"y": 1}), (["q"], {"q": 0})]
    assert mean_reciprocal_rank(runs) == pytest.approx(0.75)
    assert mean_reciprocal_rank([(["q"], {})]) is None


# --- nDCG --------------------------------------------------------------------------------------

def test_ndcg_hand_computed_with_graded_relevance():
    # Example A, k = 5. Gains by rank: a=3, b=0, c=1, d=0, e=1.
    #   DCG  = 3/1 + 0 + 1/2 + 0 + 1/2.5849625 = 3 + 0.5 + 0.3868528 = 3.8868528
    # Ideal order of the judged grades 2,1,1,1,0 -> gains 3,1,1,1,0:
    #   IDCG = 3/1 + 1/1.5849625 + 1/2 + 1/2.3219281 = 3 + 0.6309298 + 0.5 + 0.4306766 = 4.5616064
    #   nDCG@5 = 3.8868528 / 4.5616064 = 0.85208
    assert ndcg_at_k(RANKED_A, JUDGED_A, 5) == pytest.approx(0.85208, abs=1e-4)
    # k = 3: DCG = 3 + 0 + 0.5 = 3.5;  IDCG = 3 + 0.6309298 + 0.5 = 4.1309298;  3.5 / 4.1309298 = 0.84725
    assert ndcg_at_k(RANKED_A, JUDGED_A, 3) == pytest.approx(0.84725, abs=1e-4)


def test_ndcg_is_one_for_a_perfect_order_and_lower_for_the_reverse():
    judged = {"g2": 2, "g1": 1}
    assert ndcg_at_k(["g2", "g1"], judged, 2) == pytest.approx(1.0)
    # reversed: DCG = 1/1 + 3/1.5849625 = 1 + 1.8927892 = 2.8927892;  IDCG = 3 + 0.6309298 = 3.6309298
    #   2.8927892 / 3.6309298 = 0.7967
    assert ndcg_at_k(["g1", "g2"], judged, 2) == pytest.approx(0.7967, abs=1e-4)


def test_ndcg_with_fewer_results_than_k():
    # ranked a, b (both grade 1), three relevant papers in total, k = 5.
    #   DCG = 1 + 0.6309298 = 1.6309298;  IDCG = 1 + 0.6309298 + 0.5 = 2.1309298;  ratio = 0.76537
    ranked, judged = ["a", "b"], {"a": 1, "b": 1, "c": 1}
    assert ndcg_at_k(ranked, judged, 5) == pytest.approx(0.76537, abs=1e-4)


def test_ndcg_one_relevant_paper_at_rank_three():
    # DCG = 1/log2(4) = 0.5; IDCG = 1 (the single relevant paper at rank 1) -> 0.5
    assert ndcg_at_k(["x", "y", "z"], {"z": 1}, 3) == pytest.approx(0.5)
    assert ndcg_at_k(["x", "y", "z"], {"z": 1}, 2) == 0.0


# --- no relevant documents ---------------------------------------------------------------------

@pytest.mark.parametrize("judged", [{}, {"a": 0, "b": 0}])
def test_no_relevant_documents(judged):
    # Precision is well defined (nothing relevant was found: 0). Recall, reciprocal rank and nDCG have a
    # zero denominator, so they are undefined (None) and the runner leaves such queries out of the means.
    assert precision_at_k(["a", "b"], judged, 2) == 0.0
    assert recall_at_k(["a", "b"], judged, 2) is None
    assert reciprocal_rank(["a", "b"], judged) is None
    assert ndcg_at_k(["a", "b"], judged, 2) is None
    assert evaluate_query(["a", "b"], judged, 2)["relevant_count"] == 0


# --- duplicates --------------------------------------------------------------------------------

def test_duplicate_ids_are_counted_once_at_their_first_position():
    # a, a, b -> a, b. Precision@3 = 2/3 (not 3/3). Reciprocal rank is unchanged.
    assert precision_at_k(["a", "a", "b"], {"a": 1, "b": 1}, 3) == pytest.approx(2 / 3)
    # x, a, a -> x, a: the first relevant paper is at rank 2, not rank 2 and 3 both counting
    assert reciprocal_rank(["x", "a", "a"], {"a": 1}) == pytest.approx(0.5)
    # a, a, b with a, b relevant: DCG = 1 + 0.6309298 = IDCG -> 1.0
    assert ndcg_at_k(["a", "a", "b"], {"a": 1, "b": 1}, 3) == pytest.approx(1.0)


# --- mean and evaluate_query -------------------------------------------------------------------

def test_mean_ignores_none():
    assert mean([1.0, None, 0.0]) == 0.5
    assert mean([None, None]) is None
    assert mean([]) is None


def test_evaluate_query_collects_all_metrics():
    r = evaluate_query(RANKED_A, JUDGED_A, 5)
    assert r["precision"] == pytest.approx(0.6) and r["recall"] == pytest.approx(0.75)
    assert r["reciprocal_rank"] == 1.0 and r["ndcg"] == pytest.approx(0.85208, abs=1e-4)
    assert r["relevant_count"] == 4


# --- input validation --------------------------------------------------------------------------

@pytest.mark.parametrize("call", [
    lambda: precision_at_k(["a"], {"a": 1}, 0),
    lambda: precision_at_k(["a"], {"a": 1}, "3"),
    lambda: recall_at_k(["a"], {"a": 3}, 1),             # grades must be 0, 1 or 2
    lambda: recall_at_k(["a"], {"a": True}, 1),
    lambda: recall_at_k(["a"], {"a": 1.5}, 1),
    lambda: ndcg_at_k([1, 2], {"a": 1}, 2),               # ranked ids must be strings
    lambda: ndcg_at_k("abc", {"a": 1}, 2),
    lambda: ndcg_at_k(["a"], [("a", 1)], 2),              # judgments must be a dict
    lambda: reciprocal_rank(["a"], {"a": 1}, k=0),
])
def test_bad_inputs_are_rejected(call):
    with pytest.raises(ValueError):
        call()


# --- the runner --------------------------------------------------------------------------------

def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def files(tmp_path):
    queries = tmp_path / "queries.jsonl"
    write_jsonl(queries, [
        {"query_id": "q1", "query_text": "first", "judgments": JUDGED_A},
        {"query_id": "q2", "query_text": "second", "filters": {"year_min": 2020}, "judgments": {"z": 1}},
        {"query_id": "q3", "query_text": "nothing relevant", "judgments": {"a": 0}},
    ])
    rankings = tmp_path / "rankings.json"
    rankings.write_text(json.dumps({"q1": RANKED_A, "q2": ["x", "y", "z"], "q3": ["a"]}), encoding="utf-8")
    return queries, rankings


def test_runner_prints_per_query_metrics_and_the_mean(files, capsys):
    queries, rankings = files
    code = runner.main(["run", "--queries", str(queries), "--ranker", "keyword", "--rankings", str(rankings),
                        "-k", "5"])
    out = capsys.readouterr().out
    assert code == 0
    assert "keyword" in out and "k=5" in out
    # q1: P 0.6000, R 0.7500, RR 1.0000, nDCG 0.8521.  q2: P 0.2000, R 1.0000, RR 0.3333, nDCG 0.5000
    q1 = next(line for line in out.splitlines() if line.startswith("q1"))
    assert ["0.6000", "0.7500", "1.0000", "0.8521"] == q1.split()[1:5]
    q2 = next(line for line in out.splitlines() if line.startswith("q2"))
    assert ["0.2000", "1.0000", "0.3333", "0.5000"] == q2.split()[1:5]
    # means over q1 and q2 only: P (0.6+0.2)/2 = 0.4, R (0.75+1)/2 = 0.875, MRR (1+1/3)/2 = 0.6667,
    # nDCG (0.85208+0.5)/2 = 0.6760.  q3 has no relevant paper and is left out (and said so).
    mean_line = next(line for line in out.splitlines() if line.startswith("mean"))
    assert ["0.4000", "0.8750", "0.6667", "0.6760"] == mean_line.split()[1:5]
    assert "q3" in out and "no relevant" in out.lower()
    assert "2 of 3 queries" in out


def test_runner_default_rankings_file_is_next_to_the_queries_file(files, capsys):
    queries, rankings = files
    rankings.rename(rankings.with_name("rankings-vector.json"))
    assert runner.main(["run", "--queries", str(queries), "--ranker", "vector"]) == 0
    assert "vector" in capsys.readouterr().out


def test_runner_reports_a_missing_ranking_instead_of_scoring_zero(files, capsys):
    queries, rankings = files
    data = json.loads(rankings.read_text(encoding="utf-8"))
    del data["q2"]
    rankings.write_text(json.dumps(data), encoding="utf-8")
    assert runner.main(["run", "--queries", str(queries), "--ranker", "x", "--rankings", str(rankings)]) == 1
    assert "q2" in capsys.readouterr().err


@pytest.mark.parametrize("rows", [
    [{"query_id": "q1", "query_text": "t", "judgments": {"a": 3}}],                                  # bad grade
    [{"query_id": "q1", "query_text": "t", "judgments": {"a": 1}},
     {"query_id": "q1", "query_text": "u", "judgments": {"a": 1}}],                                  # duplicate id
    [{"query_text": "t", "judgments": {"a": 1}}],                                                    # no query_id
    [{"query_id": "q1", "query_text": "t", "judgments": [1]}],                                        # judgments not a dict
    [{"query_id": "q1", "query_text": "t", "filters": "2020", "judgments": {"a": 1}}],               # filters not a dict
])
def test_runner_rejects_a_bad_query_file(tmp_path, capsys, rows):
    queries = tmp_path / "q.jsonl"
    write_jsonl(queries, rows)
    (tmp_path / "r.json").write_text(json.dumps({"q1": ["a"]}), encoding="utf-8")
    code = runner.main(["run", "--queries", str(queries), "--ranker", "x", "--rankings", str(tmp_path / "r.json")])
    assert code == 1 and "ERROR" in capsys.readouterr().err


def test_runner_accepts_files_saved_with_a_byte_order_mark(files, capsys):
    queries, rankings = files
    for path in (queries, rankings):   # what Notepad and Windows PowerShell 5.1 produce
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert runner.main(["run", "--queries", str(queries), "--ranker", "x", "--rankings", str(rankings),
                        "-k", "5"]) == 0
    assert "mean" in capsys.readouterr().out


def test_runner_rejects_unreadable_files(tmp_path, capsys):
    assert runner.main(["run", "--queries", str(tmp_path / "missing.jsonl"), "--ranker", "x"]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_runner_and_metrics_never_import_the_database_driver_or_a_model():
    code = ("import sys, retrieval.evaluation.metrics, retrieval.evaluation.runner; "
            "print([m for m in ('psycopg', 'torch', 'transformers', 'adapters') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], cwd=DB_DIR, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
