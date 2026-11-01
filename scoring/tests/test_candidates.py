import pytest

from scoring.candidates import generate_candidates
from scoring.counts import PairCounts


def counts():
    # MOCK counts. Expected: (1,10)=10, (1,11)=6, (2,10)=5, (2,11)=3; element 3 is below support.
    return PairCounts(
        pair_type="method_task",
        n_total=100,
        n_a={1: 20, 2: 10, 3: 2},
        n_b={10: 50, 11: 30},
        observed={(1, 10): 3, (1, 11): 6, (2, 10): 5},
    )


def test_keeps_only_underrepresented_supported_pairs():
    cands = generate_candidates(counts(), min_support=5)
    keys = [(c.a_id, c.b_id) for c in cands]
    # (1,11) and (2,10) have observed == expected; element 3 is below support
    assert keys == [(2, 11), (1, 10)]          # sorted by lift: 0/3 then 3/10


def test_candidate_values():
    by_key = {(c.a_id, c.b_id): c for c in generate_candidates(counts(), min_support=5)}
    c = by_key[(1, 10)]
    assert (c.observed, c.expected) == (3, 10.0)
    assert c.sparsity == pytest.approx(7 / 11)
    assert c.confidence == 1.0
    c = by_key[(2, 11)]
    assert (c.observed, c.expected) == (0, 3.0)
    assert c.sparsity == pytest.approx(0.75)
    assert c.confidence == pytest.approx(0.6)


def test_min_expected_filter():
    keys = [(c.a_id, c.b_id) for c in generate_candidates(counts(), min_support=5, min_expected=4)]
    assert keys == [(1, 10)]


def test_neighborhood_restriction():
    keys = [(c.a_id, c.b_id) for c in generate_candidates(counts(), min_support=5, neighborhood_a={1})]
    assert keys == [(1, 10)]


def test_empty_universe():
    assert generate_candidates(PairCounts("method_task", 0), min_support=1) == []
