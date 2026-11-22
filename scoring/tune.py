"""Tune score weights and thresholds (open decision O6) with the temporal holdout.

    python -m scoring.tune --dsn postgresql://.../pc_pilot --pair-type method_task \
        --cutoffs 2021 2022 2023 --min-supports 3 5 8 10 --out scoring/out/tuning.json

For every min_support and cutoff year Y it builds candidates from papers up to Y
(same-universe counts, as in scoring.pipeline), then marks a candidate as a hit
when the pair is used together in at least one paper published after Y. Every
weight vector on a grid over the three phase-1 signals is scored by mean
average precision (AP) across the cutoffs and compared with the random,
sparsity-only and semantic-only baselines from scoring.holdout.

A hit only shows that the pair was taken up later in this corpus. It is not
proof that the pair was a research gap at Y, and a miss is not proof that it
is not one. With a small corpus the number of hits per cutoff is small, so the
report prints it next to every metric. The database is only read.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from scoring.candidates import generate_candidates
from scoring.counts import PAIR_TYPES, fetch_pair_counts
from scoring.holdout import average_precision, evaluate_holdout, precision_at_k
from scoring.ranking import PairKey, ScoredCandidate, candidate_key, rank, rescore
from scoring.score import WEIGHTS, validate_weights

PHASE1_SIGNALS = ("sparsity", "semantic_compatibility", "temporal_activity")


def weight_grid(signals: Sequence[str], step: float) -> list[dict[str, float]]:
    """Every weight vector over `signals` with entries in multiples of `step`, each >= step, summing to 1.

    Each signal keeps a weight of at least one step, so no signal is switched off
    (decision 8: the three phase-1 signals are all used).
    """
    units = round(1 / step)
    if abs(units * step - 1) > 1e-9:
        raise ValueError("1 must be a multiple of step")
    n = len(signals)
    if n == 0 or units < n:
        return []
    out: list[dict[str, float]] = []

    def rec(prefix: list[int], left: int) -> None:
        if len(prefix) == n - 1:
            if left >= 1:
                parts = prefix + [left]
                out.append({s: round(p * step, 10) for s, p in zip(signals, parts)})
            return
        for u in range(1, left - (n - len(prefix) - 1) + 1):
            rec(prefix + [u], left - u)

    rec([], units)
    for w in out:
        if abs(sum(w.values()) - 1.0) > 1e-9:
            raise AssertionError(f"grid weights do not sum to 1: {w}")
    if set(signals) <= set(PHASE1_SIGNALS):
        for w in out:
            validate_weights(w)
    return out


def appeared_after(conn, pair_type: str, cutoff_year: int, min_papers: int = 1) -> set[PairKey]:
    """Pairs used together (same experiment) in at least `min_papers` distinct papers published after the cutoff."""
    col_a, col_b = PAIR_TYPES[pair_type]
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT e.{col_a}, e.{col_b} FROM experiment e JOIN paper p ON p.paper_id = e.paper_id
                WHERE e.{col_a} IS NOT NULL AND e.{col_b} IS NOT NULL AND p.year > %s
                GROUP BY e.{col_a}, e.{col_b} HAVING COUNT(DISTINCT e.paper_id) >= %s""",
            (cutoff_year, min_papers),
        )
        return {(pair_type, a, b) for a, b in cur.fetchall()}


def scored_at_cutoff(conn, pair_type: str, cutoff_year: int, min_support: int, k: float,
                     new_only: bool = False, min_sparsity: float = 0.0) -> list[ScoredCandidate]:
    """Candidates and signals exactly as scoring.pipeline.run builds them, from papers up to cutoff_year.

    new_only keeps only candidates never used together up to the cutoff (observed == 0), so a hit
    means the pair was used together for the first time after the cutoff. Signals are still
    normalized over the full candidate set, as in the pipeline.
    """
    from scoring.pipeline import compute_inputs

    counts = fetch_pair_counts(conn, pair_type, cutoff_year)
    candidates = generate_candidates(counts, min_support=min_support, k=k, min_sparsity=min_sparsity)
    semantic, temporal = compute_inputs(conn, candidates, cutoff_year)
    usable = [c for c in candidates if candidate_key(c) in semantic and candidate_key(c) in temporal]
    scored = rank(usable, semantic, temporal, "v1-three-signal")
    if new_only:
        scored = [x for x in scored if x.candidate.observed == 0]
    return scored


@dataclass
class CutoffRun:
    cutoff_year: int
    candidates: int
    hits: int
    scored: list[ScoredCandidate]
    appeared: set[PairKey]


@dataclass
class WeightResult:
    weights: dict[str, float]
    mean_ap: float
    mean_p_at_k: float
    per_cutoff_ap: dict[int, float]


def evaluate_weights(runs: Sequence[CutoffRun], weights: dict[str, float], k: int) -> WeightResult:
    """Mean AP and P@k over the cutoffs that have at least one candidate and one hit."""
    aps, pks, per = [], [], {}
    for r in runs:
        if not r.scored or not r.hits:
            continue
        order = [s.key for s in rescore(r.scored, weights)]
        ap = average_precision(order, r.appeared)
        aps.append(ap)
        pks.append(precision_at_k(order, r.appeared, k))
        per[r.cutoff_year] = ap
    if not aps:
        return WeightResult(weights, 0.0, 0.0, per)
    return WeightResult(weights, statistics.fmean(aps), statistics.fmean(pks), per)


def baselines(runs: Sequence[CutoffRun], k: int) -> dict[str, dict[str, float]]:
    """Mean AP and P@k of the scoring.holdout baselines (random averaged over 100 seeds) across cutoffs."""
    acc: dict[str, dict[str, list[float]]] = {}
    for r in runs:
        if not r.scored or not r.hits:
            continue
        for res in evaluate_holdout(r.scored, r.appeared, k=k):
            if res.ranking == "full_score":
                continue
            d = acc.setdefault(res.ranking, {"ap": [], "p_at_k": []})
            d["ap"].append(res.average_precision)
            d["p_at_k"].append(res.precision_at_k)
    return {name: {"mean_ap": statistics.fmean(v["ap"]), "mean_p_at_k": statistics.fmean(v["p_at_k"])}
            for name, v in acc.items()}


def tune(conn, pair_type: str, cutoffs: Sequence[int], min_supports: Sequence[int], k_conf: float,
         step: float, top_k: int, new_only: bool = False, floor: float = 0.2,
         min_sparsity: float = 0.0) -> dict:
    grid = weight_grid(PHASE1_SIGNALS, step)
    report: dict = {"pair_type": pair_type, "cutoffs": list(cutoffs), "confidence_k": k_conf,
                    "grid_step": step, "top_k": top_k, "new_only": new_only, "floor": floor, "min_sparsity": min_sparsity,
                    "by_min_support": []}
    for ms in min_supports:
        runs = []
        for y in cutoffs:
            scored = scored_at_cutoff(conn, pair_type, y, ms, k_conf, new_only, min_sparsity)
            appeared = appeared_after(conn, pair_type, y)
            hits = sum(1 for s in scored if s.key in appeared)
            runs.append(CutoffRun(y, len(scored), hits, scored, appeared))
        results = sorted((evaluate_weights(runs, w, top_k) for w in grid),
                         key=lambda r: (-r.mean_ap, -r.mean_p_at_k, tuple(-r.weights[s] for s in PHASE1_SIGNALS)))
        named = {name: asdict(evaluate_weights(runs, dict(w), top_k))
                 for name, w in WEIGHTS.items() if set(w) <= set(PHASE1_SIGNALS)}
        report["by_min_support"].append({
            "min_support": ms,
            "cutoffs": [{"cutoff_year": r.cutoff_year, "candidates": r.candidates, "hits": r.hits} for r in runs],
            "named_weights": named,
            "baselines": baselines(runs, top_k),
            "best": [asdict(r) for r in results[:5]],
            # best vector in which every signal keeps at least `floor` of the weight
            "best_with_floor": [asdict(r) for r in results
                                if min(r.weights.values()) >= floor - 1e-9][:3],
            "worst": asdict(results[-1]) if results else None,
            "grid_size": len(grid),
        })
    return report


def main() -> None:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--pair-type", choices=sorted(PAIR_TYPES), default="method_task")
    ap.add_argument("--cutoffs", type=int, nargs="+", default=[2021, 2022, 2023])
    ap.add_argument("--min-supports", type=int, nargs="+", default=[3, 5, 8, 10])
    ap.add_argument("--k", type=float, default=5.0, help="confidence constant")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--new-only", action="store_true",
                    help="only candidates with observed == 0 at the cutoff (hit = first use after it)")
    ap.add_argument("--min-sparsity", type=float, default=0.0)
    ap.add_argument("--floor", type=float, default=0.2, help="minimum weight per signal for best_with_floor")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    with psycopg.connect(args.dsn) as conn:
        conn.read_only = True
        report = tune(conn, args.pair_type, args.cutoffs, args.min_supports, args.k, args.step, args.top_k,
                      args.new_only, args.floor, args.min_sparsity)
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    for block in report["by_min_support"]:
        print(f"\nmin_support={block['min_support']}  cutoffs={block['cutoffs']}")
        for name, r in block["named_weights"].items():
            print(f"  {name:<22} AP={r['mean_ap']:.3f} P@{args.top_k}={r['mean_p_at_k']:.3f}")
        for name, r in block["baselines"].items():
            print(f"  {name:<22} AP={r['mean_ap']:.3f} P@{args.top_k}={r['mean_p_at_k']:.3f}")
        for r in block["best"][:2]:
            print(f"  best {r['weights']} AP={r['mean_ap']:.3f} P@{args.top_k}={r['mean_p_at_k']:.3f}")
        for r in block["best_with_floor"][:2]:
            print(f"  floor {r['weights']} AP={r['mean_ap']:.3f} P@{args.top_k}={r['mean_p_at_k']:.3f}")


if __name__ == "__main__":
    main()
