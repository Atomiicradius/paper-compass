import pytest

from scoring.candidates import generate_candidates
from scoring.counts import PairCounts
from scoring.ranking import TemporalFeatures, rank, temporal_activity
from scoring.score import WEIGHTS, score, validate_weights
from scoring.sensitivity import perturb, sensitivity


def test_default_weights_are_valid():
    for w in WEIGHTS.values():
        validate_weights(w)


def test_score():
    w = WEIGHTS["v1-three-signal"]
    assert score({"sparsity": 0.5, "semantic_compatibility": 0.5, "temporal_activity": 0.5}, w) == pytest.approx(50)
    assert score({"sparsity": 1, "semantic_compatibility": 0, "temporal_activity": 0}, w) == pytest.approx(40)
    with pytest.raises(ValueError):
        score({"sparsity": 1, "semantic_compatibility": 0}, w)                      # missing signal
    with pytest.raises(ValueError):
        score({"sparsity": 1.2, "semantic_compatibility": 0, "temporal_activity": 0}, w)
    with pytest.raises(ValueError):
        validate_weights({"sparsity": 0.5, "semantic_compatibility": 0.4})          # sums to 0.9


def mock_candidates():
    c = PairCounts("method_task", 100, {1: 20, 2: 10}, {10: 50, 11: 30}, {(1, 10): 3, (1, 11): 6, (2, 10): 5})
    return generate_candidates(c, min_support=5)   # (2,11) sparsity 0.75, (1,10) sparsity 7/11


def test_temporal_activity():
    cands = mock_candidates()
    feats = {
        ("method_id", 1): TemporalFeatures(0.2, 1.0),
        ("method_id", 2): TemporalFeatures(0.8, 2.0),
        ("task_id", 10): TemporalFeatures(0.5, 0.0),
        ("task_id", 11): TemporalFeatures(0.5, 0.0),
    }
    t = temporal_activity(cands, feats)
    # elements: m1, m2, t10, t11. share pr: m1 0, m2 1, t10/t11 tie at positions 1-2 -> 1.5/3 = 0.5
    # slope pr: t10/t11 tie at positions 0-1 -> 0.5/3, m1 2/3, m2 1
    m1 = (0 + 2 / 3) / 2
    m2 = (1 + 1) / 2
    t_ = (0.5 + (0.5 / 3)) / 2
    assert t[("method_task", 1, 10)] == pytest.approx((m1 + t_) / 2)
    assert t[("method_task", 2, 11)] == pytest.approx((m2 + t_) / 2)


def test_rank():
    cands = mock_candidates()
    semantic = {("method_task", 2, 11): 0.9, ("method_task", 1, 10): 0.1}
    temporal = {("method_task", 2, 11): 0.5, ("method_task", 1, 10): 0.5}
    out = rank(cands, semantic, temporal)
    assert [s.key for s in out] == [("method_task", 2, 11), ("method_task", 1, 10)]
    assert out[0].score == pytest.approx(100 * (0.4 * 0.75 + 0.35 * 1 + 0.25 * 0.5))
    assert out[1].score == pytest.approx(100 * (0.4 * 7 / 11 + 0.35 * 0 + 0.25 * 0.5))
    # unimplemented signals are present as None, not omitted
    assert out[0].signals["graph_bridge_strength"] is None
    assert out[0].weights_version == "v1-three-signal"

    filtered = rank(cands, semantic, temporal, min_semantic=0.5)
    assert [s.key for s in filtered] == [("method_task", 2, 11)]


def test_perturb_keeps_sum_one():
    w = perturb({"a": 0.4, "b": 0.35, "c": 0.25}, "a", 0.1)
    assert w["a"] == pytest.approx(0.5)
    assert w["b"] == pytest.approx(0.35 * 0.5 / 0.6)
    assert w["c"] == pytest.approx(0.25 * 0.5 / 0.6)
    assert sum(w.values()) == pytest.approx(1.0)
    assert perturb({"a": 0.95, "b": 0.05}, "a", 0.1)["a"] == 1.0   # clipped


def test_sensitivity_rows():
    cands = mock_candidates()
    scored = rank(cands, {("method_task", 2, 11): 0.9, ("method_task", 1, 10): 0.1},
                  {("method_task", 2, 11): 0.5, ("method_task", 1, 10): 0.5})
    rows = sensitivity(scored, WEIGHTS["v1-three-signal"], k=2)
    assert len(rows) == 6                       # 3 signals x 2 deltas
    # (2,11) dominates on every signal here, so the top-2 set never changes
    assert all(r.top_k_overlap == 1.0 for r in rows)
    assert all(abs(sum(r.weights.values()) - 1) < 1e-9 for r in rows)
