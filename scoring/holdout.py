"""Temporal holdout and baselines (plan section 12.3).

Build candidates from papers up to cutoff year Y, then check which flagged
pairs are used together in papers from Y+1 onward. This shows predictive
signal only: a pair can appear later for reasons unrelated to our signals,
and absence from the corpus does not mean absence from research.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from scoring.counts import PAIR_TYPES
from scoring.ranking import PairKey, ScoredCandidate


def future_pairs(rows: Iterable[Mapping], pair_type: str, min_papers: int = 1) -> set[tuple[int, int]]:
    """Pairs used together in at least `min_papers` distinct papers among `rows` (the post-cutoff rows)."""
    col_a, col_b = PAIR_TYPES[pair_type]
    papers: dict[tuple[int, int], set] = {}
    for r in rows:
        a, b = r[col_a], r[col_b]
        if a is None or b is None:
            continue
        papers.setdefault((a, b), set()).add(r["paper_id"])
    return {k for k, v in papers.items() if len(v) >= min_papers}


def precision_at_k(ranked: Sequence[PairKey], relevant: set[PairKey], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for x in top if x in relevant) / len(top)


def average_precision(ranked: Sequence[PairKey], relevant: set[PairKey]) -> float:
    """Mean of precision@i over the positions i of relevant items (0 if none are relevant)."""
    hits = 0
    total = 0.0
    for i, x in enumerate(ranked, start=1):
        if x in relevant:
            hits += 1
            total += hits / i
    return total / hits if hits else 0.0


@dataclass
class HoldoutResult:
    ranking: str
    precision_at_k: float
    average_precision: float


def evaluate_holdout(
    scored: Sequence[ScoredCandidate],
    appeared: set[PairKey],
    k: int = 10,
    random_seeds: int = 100,
) -> list[HoldoutResult]:
    """Compare the full score with random, sparsity-only and semantic-only orderings."""
    def by(signal: str) -> list[PairKey]:
        return [s.key for s in sorted(scored, key=lambda s: (-s.signals[signal], s.key))]

    orderings = {
        "full_score": [s.key for s in scored],
        "sparsity_only": by("sparsity"),
        "semantic_only": by("semantic_compatibility"),
    }
    results = [
        HoldoutResult(name, precision_at_k(o, appeared, k), average_precision(o, appeared))
        for name, o in orderings.items()
    ]

    keys = [s.key for s in scored]
    p_sum = ap_sum = 0.0
    for seed in range(random_seeds):
        shuffled = keys[:]
        random.Random(seed).shuffle(shuffled)
        p_sum += precision_at_k(shuffled, appeared, k)
        ap_sum += average_precision(shuffled, appeared)
    results.append(HoldoutResult("random", p_sum / random_seeds, ap_sum / random_seeds))
    return results
