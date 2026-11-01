"""Data access for the API. PostgreSQL is the source of truth; Neo4j serves the graph view.

Returns plain dicts shaped like api.schemas so a mock repository can stand in
for UI work before real data exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from graph import queries
from graph.bridges import bridge_papers, cluster_pairs
from graph.trends import fetch_papers_per_year, fetch_trends

ROLES = ("supports_A", "supports_B", "bridge", "nearest_existing")
SIGNAL_COLS = ("sparsity", "semantic_compatibility", "temporal_activity", "graph_bridge_strength", "method_compatibility")

_OPP_SELECT = """
SELECT o.opportunity_id, m.canonical_name, t.canonical_name, d.canonical_name, s.name,
       o.corpus_cutoff_year, o.observed_count, o.expected_count,
       o.sparsity, o.semantic_compatibility, o.temporal_activity, o.graph_bridge_strength, o.method_compatibility,
       o.confidence, o.score, o.weights_version,
       (SELECT COUNT(*) FROM paper p WHERE p.year <= o.corpus_cutoff_year) AS corpus_papers
FROM opportunity o
LEFT JOIN method  m ON m.method_id  = o.method_id
LEFT JOIN task    t ON t.task_id    = o.task_id
LEFT JOIN dataset d ON d.dataset_id = o.dataset_id
LEFT JOIN setting s ON s.setting_id = o.setting_id
"""


class Repository(Protocol):
    def list_opportunities(self, limit: int, offset: int, cutoff_year: int | None,
                           weights_version: str | None, min_confidence: float | None) -> tuple[int, list[dict]]: ...
    def get_opportunity(self, opportunity_id: int) -> dict | None: ...
    def get_paper(self, paper_id: str) -> dict | None: ...
    def paper_graph(self, paper_id: str, limit: int) -> dict | None: ...
    def trends(self, element_type: str) -> list[dict]: ...
    def clusters(self) -> dict: ...
    def landscape(self) -> dict: ...


class PostgresRepository:
    def __init__(self, pg_dsn: str, neo4j_driver=None, clusters_path: str | Path | None = None):
        self.pg_dsn = pg_dsn
        self.neo4j = neo4j_driver
        self.clusters_path = Path(clusters_path) if clusters_path else None

    def _conn(self):
        import psycopg

        return psycopg.connect(self.pg_dsn)

    # --- opportunities ------------------------------------------------------

    def _opportunity(self, cur, row) -> dict:
        (opp_id, method, task, dataset, setting, cutoff, observed, expected, *rest) = row
        signals = dict(zip(SIGNAL_COLS, rest[:5]))
        confidence, score, weights_version, corpus_papers = rest[5:]
        cur.execute("SELECT role, paper_id FROM opportunity_evidence WHERE opportunity_id = %s ORDER BY role, paper_id", (opp_id,))
        evidence = {r: [] for r in ROLES}
        for role, pid in cur.fetchall():
            evidence[role].append(pid)
        return {
            "opportunity_id": opp_id,
            "elements": {"method": method, "task": task, "dataset": dataset, "setting": setting},
            "corpus": {"papers": corpus_papers, "cutoff_year": cutoff},
            "observed_count": observed,
            "expected_count": expected,
            "signals": signals,
            "confidence": confidence,
            "score": score,
            "weights_version": weights_version,
            "evidence": evidence,
        }

    def list_opportunities(self, limit, offset, cutoff_year, weights_version, min_confidence):
        where, params = [], []
        if cutoff_year is not None:
            where.append("o.corpus_cutoff_year = %s")
            params.append(cutoff_year)
        if weights_version is not None:
            where.append("o.weights_version = %s")
            params.append(weights_version)
        if min_confidence is not None:
            where.append("o.confidence >= %s")
            params.append(min_confidence)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM opportunity o{clause}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"{_OPP_SELECT}{clause} ORDER BY o.score DESC NULLS LAST, o.opportunity_id LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            rows = cur.fetchall()
            return total, [self._opportunity(cur, r) for r in rows]

    def get_opportunity(self, opportunity_id):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(f"{_OPP_SELECT} WHERE o.opportunity_id = %s", (opportunity_id,))
            row = cur.fetchone()
            return self._opportunity(cur, row) if row else None

    # --- papers -------------------------------------------------------------

    def get_paper(self, paper_id):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT p.paper_id, p.title, p.year, p.abstract, p.doi, v.name
                   FROM paper p LEFT JOIN venue v USING (venue_id) WHERE p.paper_id = %s""",
                (paper_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            def names(sql: str) -> list[str]:
                cur.execute(sql, (paper_id,))
                return [r[0] for r in cur.fetchall()]

            return {
                "paper_id": row[0], "title": row[1], "year": row[2], "abstract": row[3], "doi": row[4], "venue": row[5],
                "authors": names("SELECT a.name FROM paper_author pa JOIN author a USING (author_id) WHERE pa.paper_id = %s ORDER BY pa.author_order"),
                "topics": names("SELECT t.name FROM paper_topic pt JOIN topic t USING (topic_id) WHERE pt.paper_id = %s ORDER BY t.name"),
                "methods": names("SELECT DISTINCT m.canonical_name FROM experiment e JOIN method m USING (method_id) WHERE e.paper_id = %s ORDER BY 1"),
                "datasets": names("SELECT DISTINCT d.canonical_name FROM experiment e JOIN dataset d USING (dataset_id) WHERE e.paper_id = %s ORDER BY 1"),
                "tasks": names("SELECT DISTINCT t.canonical_name FROM experiment e JOIN task t USING (task_id) WHERE e.paper_id = %s ORDER BY 1"),
                "cites": names("SELECT cited_paper_id FROM citation WHERE citing_paper_id = %s ORDER BY 1"),
                "cited_by": names("SELECT citing_paper_id FROM citation WHERE cited_paper_id = %s ORDER BY 1"),
            }

    def paper_graph(self, paper_id, limit):
        if self.neo4j is None:
            raise RuntimeError("Neo4j is not configured")
        with self.neo4j.session() as session:
            return queries.paper_neighborhood(session, paper_id, limit)

    # --- landscape ----------------------------------------------------------

    def trends(self, element_type):
        with self._conn() as conn:
            return [t.__dict__ for t in fetch_trends(conn, element_type)]

    def clusters(self):
        if self.clusters_path is None or not self.clusters_path.exists():
            raise FileNotFoundError("clusters have not been computed; run python -m graph.clusters")
        return json.loads(self.clusters_path.read_text(encoding="utf-8"))

    def landscape(self):
        import numpy as np

        with self._conn() as conn:
            per_year = fetch_papers_per_year(conn)
            topic_trends = fetch_trends(conn, "topic") or fetch_trends(conn, "method")
            with conn.cursor() as cur:
                cur.execute("SELECT citing_paper_id, cited_paper_id FROM citation")
                citations = cur.fetchall()
                cur.execute("SELECT MAX(year), COUNT(*) FROM paper")
                max_year, n_papers = cur.fetchone()
        try:
            cl = self.clusters()
        except FileNotFoundError:
            cl = None
        pairs, bridges = [], []
        if cl:
            labels = cl["labels"]
            cents = {c["cluster_id"]: np.array(c["centroid"]) for c in cl["clusters"] if "centroid" in c}
            pairs = [p.__dict__ for p in cluster_pairs(labels, citations, cents) if p.weakly_connected][:10]
            bridges = [b.__dict__ for b in bridge_papers(labels, citations)[:10]]
        return {
            "corpus": {"papers": n_papers, "cutoff_year": max_year},
            "papers_per_year": per_year,
            "n_clusters": len(cl["clusters"]) if cl else 0,
            "emerging": [t.__dict__ for t in topic_trends if t.label == "emerging"][:10],
            "declining": [t.__dict__ for t in topic_trends if t.label == "declining"][:10],
            "weakly_connected_cluster_pairs": pairs,
            "bridge_papers": bridges,
        }
