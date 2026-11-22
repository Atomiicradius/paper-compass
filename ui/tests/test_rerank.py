import pytest

from ui.rerank import normalize_weights, rerank


def _opp(i, sp, sem, tmp, score):
    return {"opportunity_id": i, "score": score,
            "signals": {"sparsity": sp, "semantic_compatibility": sem, "temporal_activity": tmp,
                        "graph_bridge_strength": None, "method_compatibility": None}}


def test_normalize_weights():
    assert normalize_weights({"a": 2, "b": 2}) == {"a": 0.5, "b": 0.5}
    with pytest.raises(ValueError):
        normalize_weights({"a": 0, "b": 0})
    with pytest.raises(ValueError):
        normalize_weights({"a": -1, "b": 2})


def test_rerank_reproduces_stored_v1_score():
    # Values of opportunity 14 on pc_pilot: 100 * (0.40*0.84447473 + 0.35*0.75 + 0.25*0.5480769) = 73.73
    opp = _opp(14, 0.84447473, 0.75, 0.5480769, 73.73091)
    out = rerank([opp], {"sparsity": 0.40, "semantic_compatibility": 0.35, "temporal_activity": 0.25})
    assert out[0]["custom_score"] == pytest.approx(73.73091, abs=1e-4)


def test_rerank_orders_by_custom_score_and_keeps_inputs():
    a, b = _opp(1, 1.0, 0.0, 0.0, 50), _opp(2, 0.0, 1.0, 0.0, 60)
    out = rerank([a, b], {"sparsity": 3, "semantic_compatibility": 1})       # unnormalized on purpose
    assert [o["opportunity_id"] for o in out] == [1, 2]
    assert out[0]["custom_score"] == pytest.approx(75.0) and out[1]["custom_score"] == pytest.approx(25.0)
    assert out[0]["custom_rank"] == 1 and out[1]["custom_rank"] == 2
    assert "custom_score" not in a                                             # input not mutated


def test_rerank_ties_break_on_id():
    out = rerank([_opp(5, 0.5, 0.5, 0.5, 1), _opp(3, 0.5, 0.5, 0.5, 1)], {"sparsity": 1})
    assert [o["opportunity_id"] for o in out] == [3, 5]


def test_rerank_missing_signal_raises():
    with pytest.raises(ValueError):
        rerank([_opp(1, 0.5, 0.5, 0.5, 1)], {"graph_bridge_strength": 1})
