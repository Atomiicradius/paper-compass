"""Weighted score over normalized signals (plan section 8.3).

Score = 100 * sum(w_i * s_i), sum(w_i) = 1, each s_i in [0, 1].
The weights below are the documented starting values, not tuned results
(open decision O6). Every stored opportunity records its weights_version.
"""

from __future__ import annotations

from typing import Mapping

SIGNAL_NAMES = (
    "sparsity",
    "semantic_compatibility",
    "temporal_activity",
    "graph_bridge_strength",
    "method_compatibility",
)

WEIGHTS: dict[str, dict[str, float]] = {
    "v1-three-signal": {
        "sparsity": 0.40,
        "semantic_compatibility": 0.35,
        "temporal_activity": 0.25,
    },
    "v2-five-signal": {
        "sparsity": 0.30,
        "semantic_compatibility": 0.25,
        "temporal_activity": 0.20,
        "graph_bridge_strength": 0.15,
        "method_compatibility": 0.10,
    },
}

DEFAULT_WEIGHTS_VERSION = "v1-three-signal"


def validate_weights(weights: Mapping[str, float]) -> None:
    unknown = set(weights) - set(SIGNAL_NAMES)
    if unknown:
        raise ValueError(f"unknown signals: {sorted(unknown)}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must be non-negative")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1")


def score(signals: Mapping[str, float | None], weights: Mapping[str, float]) -> float:
    """Score in [0, 100]. Every weighted signal must be present and in [0, 1]."""
    validate_weights(weights)
    total = 0.0
    for name, w in weights.items():
        s = signals.get(name)
        if s is None:
            raise ValueError(f"signal {name!r} is weighted but missing")
        if not 0.0 <= s <= 1.0:
            raise ValueError(f"signal {name!r} = {s} is outside [0, 1]")
        total += w * s
    return 100.0 * total
