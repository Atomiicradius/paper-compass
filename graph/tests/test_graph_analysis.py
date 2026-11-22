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


def test_cluster_embeddings_with_pca_separates_blobs_and_is_deterministic():
    rng = np.random.default_rng(1)
    centers = np.eye(10)
    blobs = [rng.normal(centers[i], 0.01, size=(20, 10)) for i in range(3)]
    x = np.vstack(blobs)
    labels = cluster_embeddings(x, min_cluster_size=5, min_samples=3, pca_dims=4)
    for i in range(3):
        assert len(set(labels[20 * i:20 * (i + 1)])) == 1
    assert len({labels[0], labels[20], labels[40]}) == 3
    again = cluster_embeddings(x, min_cluster_size=5, min_samples=3, pca_dims=4)
    assert (labels == again).all()


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


def test_too_few_papers_for_a_cluster_means_everything_is_noise_not_a_crash():
    x = np.random.default_rng(0).normal(size=(6, 8))
    labels = cluster_embeddings(x, min_cluster_size=15, min_samples=5, pca_dims=20)
    assert labels.tolist() == [NOISE] * 6
    assert cluster_embeddings(np.zeros((0, 0))).tolist() == []


def test_pilot_settings_are_the_ones_chosen_in_decision_33():
    from graph.clusters import PILOT_SETTINGS

    assert PILOT_SETTINGS == {"min_cluster_size": 15, "min_samples": 5, "pca_dims": 20, "selection": "eom"}


def _six_cluster_world():
    # 6 clusters of 2 papers; clusters 0 and 1 have almost the same centroid; only three pairs cite each other
    labels = {f"P{c}{i}": c for c in range(6) for i in range(2)}
    cites = [("P20", "P30"), ("P40", "P50"), ("P21", "P41")]
    angles = [0.00, 0.02, 0.9, 1.3, 1.7, 2.1]
    cents = {c: np.array([np.cos(a), np.sin(a)]) for c, a in enumerate(angles)}
    return labels, cites, cents


def test_pairs_with_zero_cross_citations_can_be_weakly_connected_with_the_default_thresholds():
    # Regression: 12 of 15 pairs tie at density 0, so a tie-averaged percentile (about 0.39) was above the 0.25
    # threshold and a pair with the lowest possible density could never be flagged. The most similar pair (0, 1)
    # has no citations at all and must be flagged.
    labels, cites, cents = _six_cluster_world()
    pairs = cluster_pairs(labels, cites, cents)
    flagged = {(p.a, p.b) for p in pairs if p.weakly_connected}
    assert (0, 1) in flagged
    assert pairs[0].weakly_connected and (pairs[0].a, pairs[0].b) == (0, 1)       # weakly connected sorted first
    # a pair that does cite, however similar, is not "weakly connected"
    assert all(p.cross_citations == 0 for p in pairs if p.weakly_connected and p.citation_density == 0)
    assert not any(p.weakly_connected for p in pairs if p.cross_citations > 0 and p.citation_density > 0.25)


def test_density_ranking_counts_only_strictly_lower_densities():
    from graph.bridges import _share_strictly_below

    assert _share_strictly_below([0.0, 0.0, 0.0, 0.5, 1.0]) == [0.0, 0.0, 0.0, 0.75, 1.0]      # share of the 4 other values below
    assert _share_strictly_below([3.0]) == [0.0]
    assert _share_strictly_below([]) == []


def test_bridges_for_display_put_clustered_bridges_first():
    from graph.bridges import BridgePaper, bridges_for_display

    allb = [BridgePaper("N1", NOISE, [0, 1, 2, 3]), BridgePaper("N2", NOISE, [0, 1, 2]),
            BridgePaper("C1", 1, [0, 2]), BridgePaper("C2", 0, [1, 2, 3])]
    out = bridges_for_display(allb, 3)
    assert [b.paper_id for b in out] == ["C2", "C1", "N1"]          # clustered first (most clusters first), then unclustered
    assert [b.paper_id for b in bridges_for_display(allb, 10)] == ["C2", "C1", "N1", "N2"]
    assert bridges_for_display([], 5) == []


def test_graph_truncation_keeps_the_papers_own_entities_before_its_citations():
    from graph.queries import select_links

    def link(rel, node_id, year=None):
        return {"rel": rel, "out": True, "node": {"id": node_id, "year": year}}

    links = ([link("CITES", f"Paper:C{i}", 2000 + i) for i in range(50)] + [link("WROTE", "Author:1"), link("USES_METHOD", "Method:3"),
             link("SOLVES", "Task:1"), link("PUBLISHED_IN", "Venue:9"), link("EVALUATED_ON", "Dataset:2")])
    kept, total = select_links(links, limit=7)                       # limit counts nodes: the centre plus 6 neighbours
    assert total == 55 and len(kept) == 6
    kinds = [k["rel"] for k in kept]
    assert kinds.count("CITES") == 1 and {"WROTE", "USES_METHOD", "SOLVES", "PUBLISHED_IN", "EVALUATED_ON"} <= set(kinds)
    assert kept[-1]["node"]["id"] == "Paper:C49"                     # among citations, the most recent first
    again, _ = select_links(list(reversed(links)), limit=7)
    assert [k["node"]["id"] for k in again] == [k["node"]["id"] for k in kept]   # same answer whatever the input order
    allk, _ = select_links(links, limit=1000)
    assert len(allk) == 55
    none, t = select_links(links, limit=1)
    assert none == [] and t == 55
