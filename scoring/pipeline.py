"""End-to-end scoring run against PostgreSQL: counts -> candidates -> signals -> score -> store.

Usage:
    python -m scoring.pipeline --dsn postgresql://... --pair-type method_task --min-support 10

Writes `opportunity` and `opportunity_evidence` rows in one transaction, so a
failed run leaves no partial output.
"""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from scoring.candidates import Candidate, generate_candidates
from scoring.counts import PAIR_TYPES, fetch_pair_counts
from scoring.ranking import (
    ElementKey,
    PairKey,
    ScoredCandidate,
    TemporalFeatures,
    candidate_key,
    element_keys,
    rank,
    temporal_activity,
)
from scoring.score import DEFAULT_WEIGHTS_VERSION
from scoring.signals import cosine_similarity, recent_share, trend_slope

EVIDENCE_LIMIT = 5


def corpus_cutoff(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(year) FROM paper")
        return cur.fetchone()[0]


def element_centroids(conn, col: str, ids: Sequence[int], universe: tuple[str, str], cutoff_year: int) -> dict[int, list[float]]:
    """Centroid of paper embeddings for each element, over papers in the pair's universe."""
    col_a, col_b = universe
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT x.{col}, AVG(p.embedding)::text
            FROM (SELECT DISTINCT e.{col}, e.paper_id FROM experiment e
                  WHERE e.{col_a} IS NOT NULL AND e.{col_b} IS NOT NULL
                    AND e.{col} = ANY(%s)) x
            JOIN paper p ON p.paper_id = x.paper_id
            WHERE p.embedding IS NOT NULL AND p.year <= %s
            GROUP BY x.{col}
            """,
            (list(ids), cutoff_year),
        )
        return {i: json.loads(v) for i, v in cur.fetchall()}


def element_yearly(conn, col: str, ids: Sequence[int], cutoff_year: int) -> dict[int, dict[int, int]]:
    """Distinct papers per year for each element, up to the cutoff."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.{col}, p.year, COUNT(DISTINCT e.paper_id)
            FROM experiment e JOIN paper p ON p.paper_id = e.paper_id
            WHERE e.{col} = ANY(%s) AND p.year <= %s
            GROUP BY e.{col}, p.year
            """,
            (list(ids), cutoff_year),
        )
        out: dict[int, dict[int, int]] = {}
        for i, year, n in cur.fetchall():
            out.setdefault(i, {})[year] = n
        return out


def compute_inputs(conn, candidates: Sequence[Candidate], cutoff_year: int) -> tuple[dict[PairKey, float], dict[PairKey, float]]:
    """Raw semantic similarity and normalized temporal activity for each candidate."""
    if not candidates:
        return {}, {}
    pair_type = candidates[0].pair_type
    col_a, col_b = PAIR_TYPES[pair_type]
    a_ids = sorted({c.a_id for c in candidates})
    b_ids = sorted({c.b_id for c in candidates})

    cent_a = element_centroids(conn, col_a, a_ids, (col_a, col_b), cutoff_year)
    cent_b = element_centroids(conn, col_b, b_ids, (col_a, col_b), cutoff_year)
    semantic = {}
    for c in candidates:
        if c.a_id in cent_a and c.b_id in cent_b:
            semantic[candidate_key(c)] = cosine_similarity(cent_a[c.a_id], cent_b[c.b_id])

    features: dict[ElementKey, TemporalFeatures] = {}
    for col, ids in ((col_a, a_ids), (col_b, b_ids)):
        for i, yearly in element_yearly(conn, col, ids, cutoff_year).items():
            features[(col, i)] = TemporalFeatures(recent_share(yearly, cutoff_year), trend_slope(yearly, cutoff_year))
    temporal = temporal_activity([c for c in candidates if all(e in features for e in element_keys(c))], features)
    return semantic, temporal


def evidence(conn, c: Candidate, cutoff_year: int) -> dict[str, list[str]]:
    """Paper IDs per evidence role, within the pair's universe and the cutoff.

    nearest_existing: papers already using A and B together; if there are none,
    papers using A whose embedding is closest to B's centroid. This is an interim
    lookup; the evidence owner (Person 2) may replace it.
    """
    col_a, col_b = PAIR_TYPES[c.pair_type]
    params = {"a": c.a_id, "b": c.b_id, "cutoff": cutoff_year, "lim": EVIDENCE_LIMIT}

    def paper_set(cond: str, e: str = "e", p: str = "p") -> str:
        return (
            f"SELECT {e}.paper_id FROM experiment {e} JOIN paper {p} ON {p}.paper_id = {e}.paper_id "
            f"WHERE {e}.{col_a} IS NOT NULL AND {e}.{col_b} IS NOT NULL AND {p}.year <= %(cutoff)s AND "
            + cond.format(e=e)
        )

    with conn.cursor() as cur:
        def ids(sql: str) -> list[str]:
            cur.execute(sql, params)
            return [r[0] for r in cur.fetchall()]

        a_set = paper_set(f"{{e}}.{col_a} = %(a)s")
        b_set = paper_set(f"{{e}}.{col_b} = %(b)s")
        both = paper_set(f"{{e}}.{col_a} = %(a)s AND {{e}}.{col_b} = %(b)s")
        b_set_inner = paper_set(f"{{e}}.{col_b} = %(b)s", e="e2", p="p2")

        def recent(paper_set: str) -> str:
            return f"SELECT p.paper_id FROM paper p WHERE p.paper_id IN ({paper_set}) ORDER BY p.year DESC NULLS LAST, p.paper_id LIMIT %(lim)s"

        out = {
            "supports_A": ids(recent(f"{a_set} EXCEPT {both}")),
            "supports_B": ids(recent(f"{b_set} EXCEPT {both}")),
            # papers that cite into both sets, or an A paper citing a B paper
            "bridge": ids(recent(
                f"""SELECT c1.citing_paper_id FROM citation c1 JOIN citation c2 USING (citing_paper_id)
                    WHERE c1.cited_paper_id IN ({a_set}) AND c2.cited_paper_id IN ({b_set})
                    UNION
                    SELECT citing_paper_id FROM citation
                    WHERE (citing_paper_id IN ({a_set}) AND cited_paper_id IN ({b_set}))
                       OR (citing_paper_id IN ({b_set}) AND cited_paper_id IN ({a_set}))"""
            )),
            "nearest_existing": ids(recent(both)),
        }
        if not out["nearest_existing"]:
            out["nearest_existing"] = ids(
                f"""SELECT p.paper_id FROM paper p
                    WHERE p.paper_id IN ({a_set}) AND p.embedding IS NOT NULL
                    ORDER BY p.embedding <=> (SELECT AVG(p3.embedding) FROM paper p3
                                              WHERE p3.paper_id IN ({b_set_inner}))
                    LIMIT %(lim)s"""
            )
    return out


def store(conn, scored: Sequence[ScoredCandidate], cutoff_year: int, evidence_by_key: dict[PairKey, dict[str, list[str]]]) -> list[int]:
    """Insert opportunities and their evidence. Caller controls the transaction."""
    ids = []
    with conn.cursor() as cur:
        for s in scored:
            c = s.candidate
            col_a, col_b = PAIR_TYPES[c.pair_type]
            cur.execute(
                f"""INSERT INTO opportunity ({col_a}, {col_b}, corpus_cutoff_year, observed_count, expected_count,
                        sparsity, semantic_compatibility, temporal_activity, graph_bridge_strength,
                        method_compatibility, confidence, score, weights_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING opportunity_id""",
                (
                    c.a_id, c.b_id, cutoff_year, c.observed, c.expected,
                    s.signals["sparsity"], s.signals["semantic_compatibility"], s.signals["temporal_activity"],
                    s.signals["graph_bridge_strength"], s.signals["method_compatibility"],
                    c.confidence, s.score, s.weights_version,
                ),
            )
            opp_id = cur.fetchone()[0]
            ids.append(opp_id)
            for role, paper_ids in evidence_by_key.get(s.key, {}).items():
                for pid in paper_ids:
                    cur.execute(
                        "INSERT INTO opportunity_evidence (opportunity_id, paper_id, role) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (opp_id, pid, role),
                    )
    return ids


def run(conn, pair_type: str, min_support: int, k: float, cutoff_year: int | None,
        weights_version: str = DEFAULT_WEIGHTS_VERSION, top_n: int = 50) -> list[int]:
    cutoff = cutoff_year if cutoff_year is not None else corpus_cutoff(conn)
    counts = fetch_pair_counts(conn, pair_type, cutoff_year)
    candidates = generate_candidates(counts, min_support=min_support, k=k)
    semantic, temporal = compute_inputs(conn, candidates, cutoff)
    usable = [c for c in candidates if candidate_key(c) in semantic and candidate_key(c) in temporal]
    scored = rank(usable, semantic, temporal, weights_version)[:top_n]
    ev = {s.key: evidence(conn, s.candidate, cutoff) for s in scored}
    with conn.transaction():
        return store(conn, scored, cutoff, ev)


def main() -> None:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--pair-type", choices=sorted(PAIR_TYPES), default="method_task")
    ap.add_argument("--min-support", type=int, default=10)
    ap.add_argument("--k", type=float, default=5.0, help="confidence constant")
    ap.add_argument("--cutoff-year", type=int, default=None)
    ap.add_argument("--weights-version", default=DEFAULT_WEIGHTS_VERSION)
    ap.add_argument("--top-n", type=int, default=50)
    args = ap.parse_args()
    with psycopg.connect(args.dsn) as conn:
        ids = run(conn, args.pair_type, args.min_support, args.k, args.cutoff_year, args.weights_version, args.top_n)
    print(f"stored {len(ids)} opportunities")


if __name__ == "__main__":
    main()
