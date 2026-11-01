import numpy as np
import pytest

from graph.bridges import bridge_papers, cluster_pairs
from graph.clusters import NOISE, centroids, cluster_embeddings, summarize
from graph.model import NODES, RELS
from graph.sync import batched, node_merge_cypher, rel_merge_cypher, sweep_cypher
from graph.trends import build_trends, classify, growth_rate

# All paper IDs below are MOCK test data.


def test_growth_and_classify():
    rising = {2021: 1, 2022: 2, 2023: 3, 2024: 4, 2025: 5}      # slope 1, mean 3
    assert growth_rate(rising, 2025) == pytest.approx(1 / 3)
    assert growth_rate({}, 2025) == 0.0
    assert classify(0.2) == "emerging"
    assert classify(-0.2) == "declining"
    assert classify(0.05) == "stable"


def test_build_trends():
    rows = [(1, "KD", 2024, 2), (1, "KD", 2025, 4), (2, "BT", 2024, 4), (2, "BT", 2025, 2)]
    trends = {t.name: t for t in build_trends(rows, "method", 2025, window=2)}
    assert trends["KD"].label == "emerging"
    assert trends["BT"].label == "declining"
    assert trends["KD"].total == 6
    assert trends["KD"].yearly == {2024: 2, 2025: 4}


def test_bridge_papers():
    labels = {"MOCK-A": 0, "MOCK-B": 0, "MOCK-C": 1, "MOCK-D": 1, "MOCK-X": NOISE}
    cites = [("MOCK-A", "MOCK-C"), ("MOCK-X", "MOCK-A"), ("MOCK-X", "MOCK-D"), ("MOCK-B", "MOCK-A")]
    out = [(b.paper_id, b.own_cluster, b.linked_clusters) for b in bridge_papers(labels, cites)]
    assert out == [
        ("MOCK-X", NOISE, [0, 1]),     # noise paper linking two clusters
        ("MOCK-A", 0, [1]),
        ("MOCK-C", 1, [0]),
    ]                                   # MOCK-B only links inside its own cluster


def test_cluster_pairs():
    labels = {"A": 0, "B": 0, "C": 1, "D": 1, "E": 2, "F": 2}
    cites = [("A", "C"), ("B", "D"), ("A", "E")]
    cents = {0: np.array([1.0, 0.0]), 1: np.array([0.0, 1.0]), 2: np.array([1.0, 0.1])}
    pairs = cluster_pairs(labels, cites, cents, min_similarity_pct=0.5, max_density_pct=0.5)
    got = [(p.a, p.b, p.cross_citations, p.weakly_connected) for p in pairs]
    assert got == [(1, 2, 0, True), (0, 2, 1, True), (0, 1, 2, False)]
    assert pairs[1].citation_density == pytest.approx(1 / 4)


def test_cluster_embeddings_separates_blobs():
    rng = np.random.default_rng(0)
    a = rng.normal([1, 0, 0], 0.01, size=(20, 3))
    b = rng.normal([0, 1, 0], 0.01, size=(20, 3))
    labels = cluster_embeddings(np.vstack([a, b]), min_cluster_size=5)
    assert len(set(labels[:20])) == 1 and len(set(labels[20:])) == 1
    assert labels[0] != labels[20]
    cents = centroids(np.vstack([a, b]), labels)
    assert len(cents) == 2


def test_summarize():
    out = summarize(
        ["MOCK-1", "MOCK-2", "MOCK-3"], [0, 0, NOISE],
        {"MOCK-1": 2020, "MOCK-2": 2023, "MOCK-3": 2024},
        {"MOCK-1": ["KD", "MT"], "MOCK-2": ["KD", "KD"]},
    )
    assert out == [{
        "cluster_id": 0, "size": 2, "year_min": 2020, "year_max": 2023,
        "top_elements": [{"name": "KD", "n_papers": 2}, {"name": "MT", "n_papers": 1}],
        "paper_ids": ["MOCK-1", "MOCK-2"],
    }]


def test_sync_uses_merge_never_create():
    for spec in NODES:
        q = node_merge_cypher(spec)
        assert "MERGE" in q and "CREATE" not in q
        assert f"{{{spec.key}: row.{spec.key}}}" in q
    for spec in RELS:
        q = rel_merge_cypher(spec)
        assert "MERGE" in q and "CREATE" not in q
    assert len(sweep_cypher()) == len(NODES) + len(RELS)


def test_batched():
    assert [len(b) for b in batched(({"i": i} for i in range(5)), size=2)] == [2, 2, 1]
