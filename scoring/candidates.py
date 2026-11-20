"""Candidate generation for pairs (plan section 8.1, steps 4-6).

Pairs only; triples are a stretch goal. To avoid all-versus-all explosion,
callers can restrict A and B to the query neighborhood (entities found in the
retrieved papers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from scoring.counts import PairCounts
from scoring.signals import confidence, expected_count, sparsity


@dataclass(frozen=True)
class Candidate:
    pair_type: str
    a_id: int
    b_id: int
    n_a: int
    n_b: int
    n_total: int
    observed: int
    expected: float
    sparsity: float
    confidence: float


def generate_candidates(
    counts: PairCounts,
    min_support: int,
    min_expected: float = 1.0,
    k: float = 5.0,
    neighborhood_a: Collection[int] | None = None,
    neighborhood_b: Collection[int] | None = None,
) -> list[Candidate]:
    """Pairs whose elements each have support >= min_support and observed < expected.

    Pairs with expected < min_expected are dropped: they are rare for structural
    reasons, so a low observed count says nothing. Result is sorted by lift
    (most underrepresented first), ties broken by IDs for a stable order.
    """
    if counts.n_total <= 0:
        return []
    a_ids = [a for a, n in counts.n_a.items() if n >= min_support]
    b_ids = [b for b, n in counts.n_b.items() if n >= min_support]
    if neighborhood_a is not None:
        a_ids = [a for a in a_ids if a in neighborhood_a]
    if neighborhood_b is not None:
        b_ids = [b for b in b_ids if b in neighborhood_b]

    out = []
    for a in a_ids:
        for b in b_ids:
            exp = expected_count(counts.n_a[a], counts.n_b[b], counts.n_total)
            obs = counts.observed.get((a, b), 0)
            if exp < min_expected or obs >= exp:
                continue
            out.append(
                Candidate(
                    pair_type=counts.pair_type,
                    a_id=a,
                    b_id=b,
                    n_a=counts.n_a[a],
                    n_b=counts.n_b[b],
                    n_total=counts.n_total,
                    observed=obs,
                    expected=exp,
                    sparsity=sparsity(obs, exp),
                    confidence=confidence(exp, k),
                )
            )
    out.sort(key=lambda c: (c.observed / c.expected, c.a_id, c.b_id))
    return out
