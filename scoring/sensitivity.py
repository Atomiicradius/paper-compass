"""Weight sensitivity check (plan section 8.3).

For each signal, shift its weight up and down by `delta`, rescale the other
weights so the total stays 1, re-rank, and report how much the top-k changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scoring.ranking import ScoredCandidate, rescore


@dataclass
class SensitivityRow:
    signal: str
    delta: float
    weights: dict[str, float]
    top_k_overlap: float        # |top_k(base) ∩ top_k(perturbed)| / k
    rank_changes: int           # positions in the top-k whose candidate changed


def perturb(weights: Mapping[str, float], signal: str, delta: float) -> dict[str, float]:
    """Move `signal` by delta (clipped to [0, 1]) and rescale the rest proportionally."""
    if signal not in weights:
        raise KeyError(signal)
    new_w = min(1.0, max(0.0, weights[signal] + delta))
    rest = {k: v for k, v in weights.items() if k != signal}
    rest_total = sum(rest.values())
    remaining = 1.0 - new_w
    if rest_total == 0:
        if remaining > 1e-12:
            raise ValueError("cannot rescale: all other weights are zero")
        scaled = {k: 0.0 for k in rest}
    else:
        scaled = {k: v * remaining / rest_total for k, v in rest.items()}
    return {**scaled, signal: new_w}


def sensitivity(
    scored: Sequence[ScoredCandidate],
    weights: Mapping[str, float],
    k: int = 10,
    deltas: Sequence[float] = (-0.1, 0.1),
) -> list[SensitivityRow]:
    base = [s.key for s in rescore(scored, weights)[:k]]
    k_eff = len(base)
    rows = []
    for signal in weights:
        for d in deltas:
            w = perturb(weights, signal, d)
            top = [s.key for s in rescore(scored, w)[:k]]
            overlap = len(set(base) & set(top)) / k_eff if k_eff else 1.0
            changes = sum(1 for a, b in zip(base, top) if a != b)
            rows.append(SensitivityRow(signal, d, w, overlap, changes))
    return rows
