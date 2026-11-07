"""Paper clusters from embeddings (plan section 11; method is open decision O8, default HDBSCAN).

    python -m graph.clusters --pg-dsn ... --out graph/out/clusters.json

There is no cluster table in the schema, so results are written to a JSON
file that the API serves. Moving them into PostgreSQL would be a schema change
and needs a team decision.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np

NOISE = -1


def cluster_embeddings(vectors: np.ndarray, min_cluster_size: int = 15, min_samples: int | None = None) -> np.ndarray:
    """HDBSCAN on L2-normalized vectors (Euclidean distance on unit vectors orders like cosine).

    Returns one label per row; NOISE (-1) for points in no cluster.
    """
    from sklearn.cluster import HDBSCAN

    if len(vectors) == 0:
        return np.array([], dtype=int)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("zero-length embedding")
    unit = vectors / norms
    return HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, copy=True).fit_predict(unit)


def centroids(vectors: np.ndarray, labels: Sequence[int]) -> dict[int, np.ndarray]:
    labels = np.asarray(labels)
    return {int(c): vectors[labels == c].mean(axis=0) for c in sorted(set(labels.tolist())) if c != NOISE}


def summarize(
    paper_ids: Sequence[str],
    labels: Sequence[int],
    years: dict[str, int | None],
    elements: dict[str, list[str]],
    top_n: int = 5,
) -> list[dict]:
    """Per cluster: size, year range and the most frequent research elements.

    elements maps paper_id -> names (methods, tasks, topics) for that paper.
    """
    members: dict[int, list[str]] = {}
    for pid, c in zip(paper_ids, labels):
        if c != NOISE:
            members.setdefault(int(c), []).append(pid)
    out = []
    for c, pids in sorted(members.items()):
        ys = [years[p] for p in pids if years.get(p) is not None]
        counts = Counter(name for p in pids for name in set(elements.get(p, [])))
        out.append(
            {
                "cluster_id": c,
                "size": len(pids),
                "year_min": min(ys) if ys else None,
                "year_max": max(ys) if ys else None,
                "top_elements": [{"name": n, "n_papers": k} for n, k in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]],
                "paper_ids": sorted(pids),
            }
        )
    return out


def load_embeddings(pg_conn, embedding_model: str | None = None) -> tuple[list[str], np.ndarray]:
    """Paper IDs and embeddings. Pass embedding_model to avoid mixing vectors from different models."""
    sql = "SELECT paper_id, embedding::text FROM paper WHERE embedding IS NOT NULL"
    params: tuple = ()
    if embedding_model:
        sql += " AND embedding_model = %s"
        params = (embedding_model,)
    with pg_conn.cursor() as cur:
        cur.execute(sql + " ORDER BY paper_id", params)
        rows = cur.fetchall()
    ids = [r[0] for r in rows]
    vecs = np.array([json.loads(r[1]) for r in rows], dtype=float) if rows else np.zeros((0, 0))
    return ids, vecs


def load_paper_context(pg_conn) -> tuple[dict[str, int | None], dict[str, list[str]]]:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT paper_id, year FROM paper")
        years = dict(cur.fetchall())
        cur.execute(
            """SELECT e.paper_id, m.canonical_name FROM experiment e JOIN method m USING (method_id)
               UNION SELECT e.paper_id, t.canonical_name FROM experiment e JOIN task t USING (task_id)
               UNION SELECT pt.paper_id, tp.name FROM paper_topic pt JOIN topic tp USING (topic_id)"""
        )
        elements: dict[str, list[str]] = {}
        for pid, name in cur.fetchall():
            elements.setdefault(pid, []).append(name)
    return years, elements


def main() -> None:
    import psycopg

    ap = argparse.ArgumentParser(description="Cluster papers by embedding (HDBSCAN)")
    ap.add_argument("--pg-dsn", required=True)
    ap.add_argument("--out", default=str(Path(__file__).parent / "out" / "clusters.json"))
    ap.add_argument("--min-cluster-size", type=int, default=15)
    ap.add_argument("--embedding-model", default=None)
    args = ap.parse_args()

    with psycopg.connect(args.pg_dsn) as pg:
        ids, vecs = load_embeddings(pg, args.embedding_model)
        labels = cluster_embeddings(vecs, args.min_cluster_size)
        years, elements = load_paper_context(pg)
    summaries = summarize(ids, labels, years, elements)
    cents = centroids(vecs, labels) if len(ids) else {}
    for s in summaries:
        s["centroid"] = cents[s["cluster_id"]].tolist()
    result = {
        "method": "hdbscan",
        "min_cluster_size": args.min_cluster_size,
        "embedding_model": args.embedding_model,
        "n_papers": len(ids),
        "n_noise": int(np.sum(labels == NOISE)),
        "labels": dict(zip(ids, labels.tolist())),
        "clusters": summaries,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{len(result['clusters'])} clusters, {result['n_noise']} noise papers -> {out}")


if __name__ == "__main__":
    main()
