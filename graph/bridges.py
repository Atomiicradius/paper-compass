"""Bridges and weakly connected cluster pairs (plan section 11).

Both are signals for human review, not proof that two areas are unconnected.
Inputs are plain data so the functions can be tested without a database:
  labels:    paper_id -> cluster id (NOISE = -1 ignored)
  citations: iterable of (citing_paper_id, cited_paper_id)
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Mapping

import numpy as np

from graph.clusters import NOISE
from scoring.signals import percentile_rank


@dataclass
class BridgePaper:
    paper_id: str
    own_cluster: int
    linked_clusters: list[int]      # other clusters reached by one citation edge (either direction)


@dataclass
class ClusterPair:
    a: int
    b: int
    cross_citations: int
    citation_density: float         # cross_citations / (size_a * size_b)
    semantic_similarity: float      # cosine between cluster centroids
    weakly_connected: bool


def bridge_papers(labels: Mapping[str, int], citations: Iterable[tuple[str, str]]) -> list[BridgePaper]:
    """Papers whose direct citations reach clusters other than their own.

    A noise paper that links two or more clusters also counts as a bridge.
    """
    linked: dict[str, set[int]] = {}
    for src, dst in citations:
        cs, cd = labels.get(src, NOISE), labels.get(dst, NOISE)
        if cd != NOISE:
            linked.setdefault(src, set()).add(cd)
        if cs != NOISE:
            linked.setdefault(dst, set()).add(cs)
    out = []
    for pid, cl in linked.items():
        own = labels.get(pid, NOISE)
        others = sorted(cl - {own})
        if (own != NOISE and others) or (own == NOISE and len(others) >= 2):
            out.append(BridgePaper(pid, own, others))
    out.sort(key=lambda b: (-len(b.linked_clusters), b.paper_id))
    return out


def cluster_pairs(
    labels: Mapping[str, int],
    citations: Iterable[tuple[str, str]],
    centroids: Mapping[int, np.ndarray],
    min_similarity_pct: float = 0.75,
    max_density_pct: float = 0.25,
) -> list[ClusterPair]:
    """Every pair of clusters with cross-citation density and centroid similarity.

    weakly_connected marks pairs that rank high on similarity and low on density
    (percentile ranks across all pairs). Sorted with the weakly connected first.
    """
    sizes: dict[int, int] = {}
    for c in labels.values():
        if c != NOISE:
            sizes[c] = sizes.get(c, 0) + 1
    cross: dict[tuple[int, int], int] = {}
    for src, dst in citations:
        a, b = labels.get(src, NOISE), labels.get(dst, NOISE)
        if a == NOISE or b == NOISE or a == b:
            continue
        key = (min(a, b), max(a, b))
        cross[key] = cross.get(key, 0) + 1

    keys = [k for k in combinations(sorted(sizes), 2) if k[0] in centroids and k[1] in centroids]
    if not keys:
        return []
    density = [cross.get(k, 0) / (sizes[k[0]] * sizes[k[1]]) for k in keys]
    sim = [_cos(centroids[a], centroids[b]) for a, b in keys]
    sim_pr = percentile_rank(sim)
    den_pr = percentile_rank(density)
    out = [
        ClusterPair(a, b, cross.get((a, b), 0), d, s, sp >= min_similarity_pct and dp <= max_density_pct)
        for (a, b), d, s, sp, dp in zip(keys, density, sim, sim_pr, den_pr)
    ]
    out.sort(key=lambda p: (not p.weakly_connected, p.citation_density, -p.semantic_similarity))
    return out


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
