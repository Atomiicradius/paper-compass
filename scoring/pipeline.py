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

from rag.evidence import build_evidence_ids
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
from scoring.score import DEFAULT_WEIGHTS_VERSION, WEIGHTS
from scoring.signals import cosine_similarity, recent_share, trend_slope

EVIDENCE_LIMIT = 5


def check_weights_version(weights_version: str) -> None:
    """Fail early with a readable message if the weight set cannot be used yet.

    Weight sets that include signals the pipeline does not compute (graph_bridge_strength,
    method_compatibility; stretch goals) would otherwise fail deep inside scoring.
    """
    if weights_version not in WEIGHTS:
        raise ValueError(f"unknown weights version {weights_version!r}; choose one of {sorted(WEIGHTS)}")
    implemented = {"sparsity", "semantic_compatibility", "temporal_activity"}
    missing = sorted(set(WEIGHTS[weights_version]) - implemented)
    if missing:
        raise ValueError(f"weights version {weights_version!r} needs signals that are not implemented yet: "
                         f"{', '.join(missing)}")


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


# experiment column -> element kind used by rag/
_KINDS = {"method_id": "method", "dataset_id": "dataset", "task_id": "task"}


def pair_elements(c: Candidate) -> tuple[tuple[str, int], tuple[str, int]]:
    """The candidate's two elements as rag/ (kind, id) tuples, A first."""
    col_a, col_b = PAIR_TYPES[c.pair_type]
    return (_KINDS[col_a], c.a_id), (_KINDS[col_b], c.b_id)


def evidence(conn, c: Candidate, cutoff_year: int) -> dict[str, list[str]]:
    """Paper IDs per evidence role, from Person 2's rag.evidence.build_evidence_ids
    (same universe and cutoff as the counts; see db/proposals/evidence-chain-format.md)."""
    a, b = pair_elements(c)
    return build_evidence_ids(conn, a, b, cutoff_year, EVIDENCE_LIMIT)


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
        weights_version: str = DEFAULT_WEIGHTS_VERSION, top_n: int = 50,
        min_sparsity: float = 0.0, replace: bool = False) -> list[int]:
    """Score and store. replace=True first deletes this pair type's earlier opportunities
    (and their evidence) in the same transaction, so a re-run does not duplicate them. If the new run
    finds nothing to store, the old rows are kept: a mistyped threshold must not empty the table."""
    check_weights_version(weights_version)
    cutoff = cutoff_year if cutoff_year is not None else corpus_cutoff(conn)
    counts = fetch_pair_counts(conn, pair_type, cutoff_year)
    candidates = generate_candidates(counts, min_support=min_support, k=k, min_sparsity=min_sparsity)
    semantic, temporal = compute_inputs(conn, candidates, cutoff)
    usable = [c for c in candidates if candidate_key(c) in semantic and candidate_key(c) in temporal]
    scored = rank(usable, semantic, temporal, weights_version)[:top_n]
    ev = {s.key: evidence(conn, s.candidate, cutoff) for s in scored}
    if not scored:
        return []
    with conn.transaction():
        if replace:
            delete_pair_type(conn, pair_type)
        return store(conn, scored, cutoff, ev)


def delete_pair_type(conn, pair_type: str) -> int:
    """Delete stored opportunities of exactly this pair type (both columns set, the third NULL)."""
    col_a, col_b = PAIR_TYPES[pair_type]
    others = sorted({c for cols in PAIR_TYPES.values() for c in cols} - {col_a, col_b})
    null_others = "".join(f" AND {c} IS NULL" for c in others)
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM opportunity_evidence WHERE opportunity_id IN (SELECT opportunity_id FROM opportunity"
                    f" WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL{null_others})")
        cur.execute(f"DELETE FROM opportunity WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL{null_others}")
        return cur.rowcount


def main() -> None:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--pair-type", choices=sorted(PAIR_TYPES), default="method_task")
    ap.add_argument("--min-support", type=int, default=10)
    ap.add_argument("--k", type=float, default=5.0, help="confidence constant")
    ap.add_argument("--cutoff-year", type=int, default=None)
    ap.add_argument("--weights-version", default=DEFAULT_WEIGHTS_VERSION, choices=sorted(WEIGHTS))
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--min-sparsity", type=float, default=0.0,
                    help="drop pairs whose smoothed sparsity is below this (O6)")
    ap.add_argument("--replace", action="store_true",
                    help="delete earlier opportunities of this pair type in the same transaction")
    args = ap.parse_args()
    try:
        check_weights_version(args.weights_version)
    except ValueError as e:
        ap.error(str(e))
    with psycopg.connect(args.dsn) as conn:
        ids = run(conn, args.pair_type, args.min_support, args.k, args.cutoff_year, args.weights_version, args.top_n,
                  args.min_sparsity, args.replace)
    if ids:
        print(f"stored {len(ids)} opportunities")
    else:
        print("stored 0 opportunities: no candidate passed the thresholds"
              + ("; existing rows were left unchanged" if args.replace else ""))


if __name__ == "__main__":
    main()
