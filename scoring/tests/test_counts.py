from scoring.counts import pair_counts_from_rows
from scoring.tests.fixtures import MOCK_ROWS


def test_method_dataset_same_universe():
    c = pair_counts_from_rows(MOCK_ROWS, "method_dataset")
    # universe: papers with a dataset = P1, P2, P4. P5 uses method 1 but has no dataset, so it is excluded.
    assert c.n_total == 3
    assert c.n_a == {1: 2, 2: 1}
    assert c.n_b == {1: 2, 2: 2}
    assert c.observed == {(1, 1): 2, (1, 2): 1, (2, 2): 1}


def test_method_task_same_universe():
    c = pair_counts_from_rows(MOCK_ROWS, "method_task")
    assert c.n_total == 3                       # P1, P3, P4
    assert c.n_a == {1: 1, 2: 2}                # P1 counted once despite two experiments
    assert c.n_b == {1: 2, 2: 1}
    assert c.observed == {(1, 1): 1, (2, 1): 1, (2, 2): 1}


def test_dataset_task_same_universe():
    c = pair_counts_from_rows(MOCK_ROWS, "dataset_task")
    assert c.n_total == 2                       # P1, P4
    assert c.n_a == {1: 1, 2: 2}
    assert c.n_b == {1: 1, 2: 1}
    assert c.observed == {(1, 1): 1, (2, 1): 1, (2, 2): 1}


def test_cutoff_filtering_by_caller():
    early = [r for r in MOCK_ROWS if r["year"] <= 2022]
    c = pair_counts_from_rows(early, "method_dataset")
    assert c.n_total == 2                       # P1, P2
    assert c.n_a == {1: 2}
