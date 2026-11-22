import math

import pytest

from scoring.signals import (
    centroid,
    confidence,
    cosine_similarity,
    expected_count,
    lift,
    percentile_rank,
    recent_share,
    sparsity,
    trend_slope,
)


def test_expected_count():
    assert expected_count(10, 20, 100) == 2.0
    assert expected_count(0, 20, 100) == 0.0


@pytest.mark.parametrize("args", [(1, 1, 0), (-1, 1, 10), (11, 1, 10)])
def test_expected_count_rejects_bad_input(args):
    with pytest.raises(ValueError):
        expected_count(*args)


def test_lift():
    assert lift(3, 6.0) == 0.5
    with pytest.raises(ValueError):
        lift(1, 0)


def test_sparsity_smoothed_and_clipped():
    assert sparsity(0, 9) == pytest.approx(0.9)        # 1 - 1/10
    assert sparsity(9, 9) == 0.0                       # observed == expected
    assert sparsity(20, 9) == 0.0                      # over-represented clips to 0
    assert sparsity(0, 0) == 0.0                       # nothing expected, nothing missing
    assert sparsity(3, 10) == pytest.approx(7 / 11)


def test_confidence():
    assert confidence(2.5, k=5) == 0.5
    assert confidence(10, k=5) == 1.0
    assert confidence(0) == 0.0
    with pytest.raises(ValueError):
        confidence(1, k=0)


def test_percentile_rank():
    assert percentile_rank([10, 20, 30]) == [0.0, 0.5, 1.0]
    assert percentile_rank([30, 10, 20]) == [1.0, 0.0, 0.5]
    assert percentile_rank([1, 1, 2]) == [0.25, 0.25, 1.0]   # ties share the mean position
    assert percentile_rank([5]) == [1.0]
    assert percentile_rank([]) == []


def test_cosine_and_centroid():
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([1, 1], [2, 2]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert centroid([[0, 2], [2, 4]]) == [1.0, 3.0]
    with pytest.raises(ValueError):
        cosine_similarity([0, 0], [1, 0])


def test_recent_share():
    yearly = {2020: 2, 2023: 1, 2024: 1, 2025: 2, 2026: 5}
    # cutoff 2025, window 3 -> 2023..2025 = 4 of the 6 papers up to 2025; 2026 is after the cutoff
    assert recent_share(yearly, 2025, 3) == pytest.approx(4 / 6)
    assert recent_share({}, 2025) == 0.0


def test_trend_slope():
    linear = {y: y - 2020 for y in range(2021, 2026)}          # 1, 2, 3, 4, 5
    assert trend_slope(linear, 2025, 5) == pytest.approx(1.0)
    # missing years count as 0: ys = 0,0,0,0,5 -> slope 10/10
    assert trend_slope({2025: 5}, 2025, 5) == pytest.approx(1.0)
    assert trend_slope({y: 3 for y in range(2021, 2026)}, 2025, 5) == 0.0
    assert math.isclose(trend_slope({2024: 4, 2025: 2}, 2025, 2), -2.0)


# --- results must not depend on float summation order (or on the Python version) -------------------

def _exact_slope(yearly, cutoff, window):
    from fractions import Fraction

    xs = list(range(cutoff - window + 1, cutoff + 1))
    ys = [Fraction(yearly.get(x, 0)) for x in xs]
    mx, my = Fraction(sum(xs), window), sum(ys) / window
    return float(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs))


def test_trend_slope_is_the_exactly_rounded_value_for_many_series():
    import random

    rnd = random.Random(7)
    for _ in range(400):
        window = rnd.choice([2, 3, 5, 7])
        yearly = {y: rnd.randint(0, 40) for y in range(2015, 2027) if rnd.random() < 0.7}
        assert trend_slope(yearly, 2026, window) == _exact_slope(yearly, 2026, window)


def test_trend_slope_equal_series_give_bit_identical_slopes():
    import random

    from scoring.signals import trend_slope as slope

    rnd = random.Random(11)
    for _ in range(400):
        base = {y: rnd.randint(0, 30) for y in range(2022, 2027)}
        shifted = {y: v + 7 for y, v in base.items()}        # same slope mathematically
        assert slope(base, 2026) == slope(shifted, 2026)      # a float sum can differ here in the last bit


def test_cosine_similarity_matches_an_exactly_rounded_sum():
    import math
    import random

    rnd = random.Random(3)
    for _ in range(50):
        a = [rnd.uniform(-1, 1) for _ in range(40)]
        b = [rnd.uniform(-1, 1) for _ in range(40)]
        want = math.fsum(x * y for x, y in zip(a, b)) / math.sqrt(math.fsum(x * x for x in a) * math.fsum(y * y for y in b))
        assert cosine_similarity(a, b) == pytest.approx(want, rel=0, abs=1e-15)
