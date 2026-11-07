import pytest

from scoring.holdout import average_precision, evaluate_holdout, future_pairs, precision_at_k
from scoring.ranking import ScoredCandidate
from scoring.tests.fixtures import MOCK_ROWS


def test_precision_and_ap():
    ranked = ["a", "b", "c"]
    assert precision_at_k(ranked, {"a", "c"}, 2) == 0.5
    assert average_precision(ranked, {"a", "c"}) == pytest.approx((1 + 2 / 3) / 2)
    assert average_precision(ranked, set()) == 0.0
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_future_pairs():
    future = [r for r in MOCK_ROWS if r["year"] > 2022]
    assert future_pairs(future, "method_task") == {(2, 1), (2, 2)}
    assert future_pairs(future, "method_task", min_papers=2) == set()


def _scored(key, sparsity, semantic, score):
    s = ScoredCandidate.__new__(ScoredCandidate)
    s.candidate = type("C", (), {"pair_type": key[0], "a_id": key[1], "b_id": key[2]})()
    s.signals = {"sparsity": sparsity, "semantic_compatibility": semantic}
    s.score = score
    s.weights_version = "test"
    return s


def test_evaluate_holdout_baselines():
    scored = [
        _scored(("mt", 1, 1), 0.2, 0.9, 90),
        _scored(("mt", 2, 2), 0.9, 0.1, 50),
        _scored(("mt", 3, 3), 0.5, 0.5, 10),
    ]
    res = {r.ranking: r for r in evaluate_holdout(scored, appeared={("mt", 1, 1)}, k=1, random_seeds=50)}
    assert res["full_score"].precision_at_k == 1.0
    assert res["sparsity_only"].precision_at_k == 0.0
    assert res["semantic_only"].precision_at_k == 1.0
    assert 0.0 <= res["random"].precision_at_k <= 1.0
    assert res["sparsity_only"].average_precision == pytest.approx(1 / 3)
