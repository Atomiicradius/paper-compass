"""Live re-ranking for the weight sliders (stretch goal in build-plan.md).

Uses the same formula as scoring.score: 100 * sum(w_i * s_i) over normalized
signals. The stored score and weights_version are never changed; the custom
score is a view-only what-if for the reader.
"""

from __future__ import annotations

from typing import Mapping, Sequence


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must be non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return {k: v / total for k, v in weights.items()}


def rerank(opportunities: Sequence[Mapping], weights: Mapping[str, float]) -> list[dict]:
    """Copies of the opportunities with custom_score and custom_rank, best first (ties by opportunity_id)."""
    w = normalize_weights(weights)
    out = []
    for o in opportunities:
        total = 0.0
        for name, wi in w.items():
            if wi == 0:
                continue
            s = o["signals"].get(name)
            if s is None:
                raise ValueError(f"signal {name!r} is not available for opportunity {o['opportunity_id']}")
            total += wi * s
        out.append({**o, "custom_score": 100.0 * total})
    out.sort(key=lambda o: (-o["custom_score"], o["opportunity_id"]))
    for i, o in enumerate(out, start=1):
        o["custom_rank"] = i
    return out
