import math

import pytest

from scoring.candidates import Candidate
from scoring.ranking import ScoredCandidate
from scoring.tune import CutoffRun, evaluate_weights, weight_grid


def test_weight_grid_counts_and_sums():
    grid = weight_grid(("a", "b", "c"), 0.25)
    # compositions of 4 into 3 positive parts: C(3, 2) = 3
    assert len(grid) == 3
    for w in grid:
        assert math.isclose(sum(w.values()), 1.0)
        assert all(v >= 0.25 for v in w.values())
    assert {tuple(sorted(w.values())) for w in grid} == {(0.25, 0.25, 0.5)}


def test_weight_grid_step_005_size():
    # compositions of 20 into 3 positive parts: C(19, 2) = 171
    assert len(weight_grid(("a", "b", "c"), 0.05)) == 171


def test_weight_grid_rejects_bad_step():
    with pytest.raises(ValueError):
        weight_grid(("a", "b"), 0.3)


def _sc(a, sp, sem, tmp):
    c = Candidate("method_task", a, 1, 10, 10, 100, 0, 1.0, sp, 0.2)
    return ScoredCandidate(c, {"sparsity": sp, "semantic_compatibility": sem, "temporal_activity": tmp,
                               "graph_bridge_strength": None, "method_compatibility": None})


def test_evaluate_weights_hand_computed():
    # Candidate 1 wins on sparsity, candidate 2 on semantic. Only candidate 2 is a hit.
    scored = [_sc(1, 1.0, 0.0, 0.5), _sc(2, 0.0, 1.0, 0.5)]
    run = CutoffRun(2022, 2, 1, scored, {("method_task", 2, 1)})
    sparse_heavy = {"sparsity": 0.8, "semantic_compatibility": 0.1, "temporal_activity": 0.1}
    sem_heavy = {"sparsity": 0.1, "semantic_compatibility": 0.8, "temporal_activity": 0.1}
    # hit ranked 2nd: AP = 1/2, P@1 = 0
    r = evaluate_weights([run], sparse_heavy, k=1)
    assert r.mean_ap == pytest.approx(0.5) and r.mean_p_at_k == 0.0
    # hit ranked 1st: AP = 1, P@1 = 1
    r = evaluate_weights([run], sem_heavy, k=1)
    assert r.mean_ap == pytest.approx(1.0) and r.mean_p_at_k == 1.0


def test_evaluate_weights_skips_cutoffs_without_hits():
    scored = [_sc(1, 1.0, 0.0, 0.5)]
    empty = CutoffRun(2021, 1, 0, scored, set())
    hit = CutoffRun(2022, 1, 1, scored, {("method_task", 1, 1)})
    w = {"sparsity": 0.4, "semantic_compatibility": 0.35, "temporal_activity": 0.25}
    r = evaluate_weights([empty, hit], w, k=1)
    assert r.mean_ap == 1.0 and r.per_cutoff_ap == {2022: 1.0}
