"""Normalized signals for candidate research-element combinations.

Every function here returns a value in [0, 1] (or a list of them). See
context/docs/reference/project-plan-v2.md section 8.2 for the definitions.

Counts passed in must follow the same-universe rule in
context/data-and-contracts.md: n_a, n_b, n_total and observed are all
distinct-paper counts over the papers where every element of the pair
was extracted.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from typing import Mapping, Sequence


def expected_count(n_a: int, n_b: int, n_total: int) -> float:
    """Papers expected to contain both A and B if they were independent."""
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    if n_a < 0 or n_b < 0:
        raise ValueError("counts must be non-negative")
    if n_a > n_total or n_b > n_total:
        raise ValueError("element count cannot exceed the universe size")
    return n_a * n_b / n_total


def lift(observed: int, expected: float) -> float:
    """observed / expected. Undefined (raises) when expected is 0."""
    if expected <= 0:
        raise ValueError("expected must be positive")
    return observed / expected


def sparsity(observed: int, expected: float) -> float:
    """Smoothed sparsity: 1 - (observed + 1) / (expected + 1), clipped to [0, 1].

    Chosen over 1 - min(1, lift) because it is defined when expected is 0
    and does not saturate at 1 for every pair with observed == 0. Fixed for
    the evaluation (see decisions-and-progress.md, Person 3 section).
    """
    if observed < 0 or expected < 0:
        raise ValueError("counts must be non-negative")
    return _clip01(1.0 - (observed + 1.0) / (expected + 1.0))


def confidence(expected: float, k: float = 5.0) -> float:
    """min(1, expected / k). A low observed count means little when expected is small."""
    if k <= 0:
        raise ValueError("k must be positive")
    if expected < 0:
        raise ValueError("expected must be non-negative")
    return min(1.0, expected / k)


def percentile_rank(values: Sequence[float]) -> list[float]:
    """Rank-based rescaling to [0, 1] using the distribution of `values` itself.

    Ties get the mean of their positions. A single value maps to 1.0.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    ordered = sorted(values)
    out = []
    for v in values:
        lo = bisect_left(ordered, v)
        hi = bisect_right(ordered, v) - 1
        out.append(((lo + hi) / 2) / (n - 1))
    return out


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Raw cosine similarity in [-1, 1]. Rescale with percentile_rank before scoring."""
    if len(a) != len(b):
        raise ValueError("vectors must have the same dimension")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        raise ValueError("zero vector has no direction")
    return dot / (na * nb)


def centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Mean of a non-empty list of equal-length vectors."""
    if not vectors:
        raise ValueError("need at least one vector")
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors):
        raise ValueError("vectors must have the same dimension")
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def recent_share(yearly: Mapping[int, int], cutoff_year: int, window: int = 3) -> float:
    """Fraction of an element's papers published in the last `window` years up to cutoff_year."""
    total = sum(c for y, c in yearly.items() if y <= cutoff_year)
    if total == 0:
        return 0.0
    recent = sum(c for y, c in yearly.items() if cutoff_year - window < y <= cutoff_year)
    return recent / total


def trend_slope(yearly: Mapping[int, int], cutoff_year: int, window: int = 5) -> float:
    """Least-squares slope of yearly paper counts over the last `window` years (missing years = 0).

    Raw papers-per-year, not normalized; rescale with percentile_rank before scoring.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    xs = list(range(cutoff_year - window + 1, cutoff_year + 1))
    ys = [yearly.get(x, 0) for x in xs]
    mx = sum(xs) / window
    my = sum(ys) / window
    denom = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
