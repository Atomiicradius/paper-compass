"""MOCK DATA - NOT REAL. For UI development only, enabled with PC_API_MOCK=1.

Every paper ID starts with "MOCK-" and every count, signal and score below is
made up to exercise the response shapes. Never use this in the report,
evaluation or demo results.
"""

from __future__ import annotations

MOCK_NOTICE = "MOCK DATA - not real results"

_OPPORTUNITIES = [
    {
        "opportunity_id": 1,
        "elements": {"method": "Knowledge Distillation", "task": "Machine Translation", "dataset": None, "setting": None},
        "corpus": {"papers": 500, "cutoff_year": 2025},
        "observed_count": 2,
        "expected_count": 9.5,
        "signals": {"sparsity": 0.71, "semantic_compatibility": 0.88, "temporal_activity": 0.64,
                    "graph_bridge_strength": None, "method_compatibility": None},
        "confidence": 1.0,
        "score": 75.2,
        "weights_version": "v1-three-signal",
        "evidence": {"supports_A": ["MOCK-W1", "MOCK-W2"], "supports_B": ["MOCK-W3"],
                     "bridge": ["MOCK-W4"], "nearest_existing": ["MOCK-W5"]},
    },
    {
        "opportunity_id": 2,
        "elements": {"method": "Back-translation", "task": None, "dataset": "FLORES-200", "setting": None},
        "corpus": {"papers": 500, "cutoff_year": 2025},
        "observed_count": 0,
        "expected_count": 3.1,
        "signals": {"sparsity": 0.76, "semantic_compatibility": 0.52, "temporal_activity": 0.40,
                    "graph_bridge_strength": None, "method_compatibility": None},
        "confidence": 0.62,
        "score": 58.6,
        "weights_version": "v1-three-signal",
        "evidence": {"supports_A": ["MOCK-W2"], "supports_B": ["MOCK-W6"], "bridge": [], "nearest_existing": ["MOCK-W2"]},
    },
]

_PAPERS = {
    f"MOCK-W{i}": {
        "paper_id": f"MOCK-W{i}", "title": f"MOCK paper {i}", "year": 2019 + i, "abstract": "MOCK abstract.",
        "doi": None, "venue": "MOCK venue", "authors": ["MOCK Author"], "topics": [], "methods": [],
        "datasets": [], "tasks": [], "cites": [], "cited_by": [],
    }
    for i in range(1, 7)
}


class MockRepository:
    def list_opportunities(self, limit, offset, cutoff_year, weights_version, min_confidence):
        items = [o for o in _OPPORTUNITIES
                 if (cutoff_year is None or o["corpus"]["cutoff_year"] == cutoff_year)
                 and (weights_version is None or o["weights_version"] == weights_version)
                 and (min_confidence is None or o["confidence"] >= min_confidence)]
        return len(items), items[offset:offset + limit]

    def get_opportunity(self, opportunity_id):
        return next((o for o in _OPPORTUNITIES if o["opportunity_id"] == opportunity_id), None)

    def get_paper(self, paper_id):
        return _PAPERS.get(paper_id)

    def paper_graph(self, paper_id, limit):
        if paper_id not in _PAPERS:
            return None
        center = f"Paper:{paper_id}"
        return {
            "center": center,
            "nodes": [{"id": center, "label": "Paper", "name": _PAPERS[paper_id]["title"], "year": _PAPERS[paper_id]["year"]},
                      {"id": "Method:1", "label": "Method", "name": "Knowledge Distillation", "year": None}],
            "edges": [{"source": center, "target": "Method:1", "type": "USES_METHOD"}],
        }

    def trends(self, element_type):
        return []

    def clusters(self):
        return {"method": "mock", "n_papers": 0, "n_noise": 0, "clusters": []}

    def landscape(self):
        return {"corpus": {"papers": 500, "cutoff_year": 2025}, "papers_per_year": {}, "n_clusters": 0,
                "emerging": [], "declining": [], "weakly_connected_cluster_pairs": [], "bridge_papers": []}

    # --- search (made-up scores, ordered by paper number) ---------------------

    def _hits(self, top_k, exclude=None):
        papers = [p for pid, p in _PAPERS.items() if pid != exclude][:top_k]
        return [{"paper_id": p["paper_id"], "title": p["title"], "year": p["year"], "venue": p["venue"],
                 "score": round(0.9 - 0.1 * i, 2), "methods": [], "datasets": [], "tasks": []}
                for i, p in enumerate(papers)]

    def vector_search(self, encoder, text, top_k, filters):
        return {"model": "MOCK", "results": self._hits(top_k)}

    def keyword_search(self, text, top_k, filters):
        return {"model": None, "results": self._hits(top_k)}

    def related(self, paper_id, top_k, filters):
        if paper_id not in _PAPERS:
            return None
        return {"model": "MOCK", "results": self._hits(top_k, exclude=paper_id)}
