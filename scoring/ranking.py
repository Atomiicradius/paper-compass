"""Turn candidates plus raw signal inputs into scored, ranked opportunities.

Raw inputs (cosine similarity, recent share, trend slope) are on different
scales, so each is rescaled by percentile rank across the candidate set before
weighting. Signals not computed are left as None, never omitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from scoring.candidates import Candidate
from scoring.score import DEFAULT_WEIGHTS_VERSION, SIGNAL_NAMES, WEIGHTS, score
from scoring.signals import percentile_rank

PairKey = tuple[str, int, int]          # (pair_type, a_id, b_id)
ElementKey = tuple[str, int]            # (element column, id), e.g. ("method_id", 3)


@dataclass
class TemporalFeatures:
    recent_share: float
    slope: float


@dataclass
class ScoredCandidate:
    candidate: Candidate
    signals: dict[str, float | None] = field(default_factory=dict)
    score: float = 0.0
    weights_version: str = DEFAULT_WEIGHTS_VERSION

    @property
    def key(self) -> PairKey:
        c = self.candidate
        return (c.pair_type, c.a_id, c.b_id)


def candidate_key(c: Candidate) -> PairKey:
    return (c.pair_type, c.a_id, c.b_id)


def element_keys(c: Candidate) -> tuple[ElementKey, ElementKey]:
    from scoring.counts import PAIR_TYPES

    col_a, col_b = PAIR_TYPES[c.pair_type]
    return (col_a, c.a_id), (col_b, c.b_id)


def temporal_activity(
    candidates: Sequence[Candidate],
    features: Mapping[ElementKey, TemporalFeatures],
) -> dict[PairKey, float]:
    """Per pair: mean over both elements of mean(percentile(recent_share), percentile(slope)).

    Percentiles are taken over the distinct elements that appear in `candidates`.
    """
    elements = sorted({e for c in candidates for e in element_keys(c)})
    missing = [e for e in elements if e not in features]
    if missing:
        raise KeyError(f"temporal features missing for {missing[:5]}")
    share_pr = percentile_rank([features[e].recent_share for e in elements])
    slope_pr = percentile_rank([features[e].slope for e in elements])
    activity = {e: (s + t) / 2 for e, s, t in zip(elements, share_pr, slope_pr)}
    out = {}
    for c in candidates:
        ea, eb = element_keys(c)
        out[candidate_key(c)] = (activity[ea] + activity[eb]) / 2
    return out


def rank(
    candidates: Sequence[Candidate],
    semantic_raw: Mapping[PairKey, float],
    temporal: Mapping[PairKey, float],
    weights_version: str = DEFAULT_WEIGHTS_VERSION,
    extra_signals: Mapping[PairKey, Mapping[str, float]] | None = None,
    min_semantic: float | None = None,
) -> list[ScoredCandidate]:
    """Score and sort candidates, highest score first.

    semantic_raw: cosine similarity between the A and B centroids, per pair.
    temporal: already-normalized temporal activity per pair (see temporal_activity).
    extra_signals: optional normalized phase 2 signals per pair.
    min_semantic: drop pairs whose normalized semantic compatibility is below this
                  (plan step 7). None keeps every pair; the threshold is open (O6).
    """
    weights = WEIGHTS[weights_version]
    keys = [candidate_key(c) for c in candidates]
    sem = dict(zip(keys, percentile_rank([semantic_raw[k] for k in keys])))

    scored = []
    for c, k in zip(candidates, keys):
        if min_semantic is not None and sem[k] < min_semantic:
            continue
        signals: dict[str, float | None] = {name: None for name in SIGNAL_NAMES}
        signals["sparsity"] = c.sparsity
        signals["semantic_compatibility"] = sem[k]
        signals["temporal_activity"] = temporal[k]
        if extra_signals and k in extra_signals:
            signals.update(extra_signals[k])
        scored.append(
            ScoredCandidate(c, signals, score(signals, weights), weights_version)
        )
    scored.sort(key=lambda s: (-s.score, s.key))
    return scored


def rescore(scored: Sequence[ScoredCandidate], weights: Mapping[str, float]) -> list[ScoredCandidate]:
    """Re-rank existing scored candidates under different weights (sensitivity check)."""
    out = [
        ScoredCandidate(s.candidate, s.signals, score(s.signals, weights), "custom")
        for s in scored
    ]
    out.sort(key=lambda s: (-s.score, s.key))
    return out
