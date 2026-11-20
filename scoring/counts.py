"""Distinct-paper counts for pairs of research elements, following the same-universe rule.

Two sources produce the same `PairCounts` structure:
  * `pair_counts_from_rows`  - pure Python over experiment rows (tests, holdout)
  * `fetch_pair_counts`      - PostgreSQL, from the materialized views in
                               data-and-contracts.md section 1.1, or from an
                               equivalent on-the-fly query when a cutoff year is given

The integration test checks that both agree on the same data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

# pair_type -> (column for element A, column for element B)
PAIR_TYPES: dict[str, tuple[str, str]] = {
    "method_dataset": ("method_id", "dataset_id"),
    "method_task": ("method_id", "task_id"),
    "dataset_task": ("dataset_id", "task_id"),
}

# pair_type -> (count view for A, count view for B, pair view)
_PAIR_VIEWS: dict[str, tuple[str, str, str]] = {
    "method_dataset": ("mv_method_count_md", "mv_dataset_count", "mv_method_dataset"),
    "method_task": ("mv_method_count_mt", "mv_task_count", "mv_method_task"),
    "dataset_task": ("mv_dataset_count_dt", "mv_task_count_dt", "mv_dataset_task"),
}


@dataclass
class PairCounts:
    pair_type: str
    n_total: int                                   # N: papers in this pair type's universe
    n_a: dict[int, int] = field(default_factory=dict)
    n_b: dict[int, int] = field(default_factory=dict)
    observed: dict[tuple[int, int], int] = field(default_factory=dict)


def pair_counts_from_rows(rows: Iterable[Mapping], pair_type: str) -> PairCounts:
    """Count distinct papers over experiment rows where both columns of the pair are present.

    Each row needs `paper_id` and the two columns named in PAIR_TYPES[pair_type].
    Filter rows by year before calling this to build a cutoff-year corpus.
    """
    col_a, col_b = PAIR_TYPES[pair_type]
    papers: set = set()
    a_papers: dict[int, set] = {}
    b_papers: dict[int, set] = {}
    ab_papers: dict[tuple[int, int], set] = {}
    for r in rows:
        a, b = r[col_a], r[col_b]
        if a is None or b is None:
            continue
        pid = r["paper_id"]
        papers.add(pid)
        a_papers.setdefault(a, set()).add(pid)
        b_papers.setdefault(b, set()).add(pid)
        ab_papers.setdefault((a, b), set()).add(pid)
    return PairCounts(
        pair_type=pair_type,
        n_total=len(papers),
        n_a={k: len(v) for k, v in a_papers.items()},
        n_b={k: len(v) for k, v in b_papers.items()},
        observed={k: len(v) for k, v in ab_papers.items()},
    )


def fetch_pair_counts(conn, pair_type: str, cutoff_year: int | None = None) -> PairCounts:
    """Load PairCounts from PostgreSQL.

    With cutoff_year=None the materialized views are used. With a cutoff year the
    same counts are computed on the fly over papers with year <= cutoff_year
    (the materialized views cover the whole corpus, so they cannot be used for
    the temporal holdout).
    """
    col_a, col_b = PAIR_TYPES[pair_type]
    with conn.cursor() as cur:
        if cutoff_year is None:
            view_a, view_b, view_ab = _PAIR_VIEWS[pair_type]
            cur.execute("SELECT n_papers FROM mv_universe_size WHERE pair_type = %s", (pair_type,))
            row = cur.fetchone()
            n_total = row[0] if row else 0
            cur.execute(f"SELECT {col_a}, n_papers FROM {view_a}")
            n_a = dict(cur.fetchall())
            cur.execute(f"SELECT {col_b}, n_papers FROM {view_b}")
            n_b = dict(cur.fetchall())
            cur.execute(f"SELECT {col_a}, {col_b}, n_papers FROM {view_ab}")
            observed = {(a, b): n for a, b, n in cur.fetchall()}
        else:
            base = (
                "FROM experiment e JOIN paper p ON p.paper_id = e.paper_id "
                f"WHERE e.{col_a} IS NOT NULL AND e.{col_b} IS NOT NULL AND p.year <= %s"
            )
            cur.execute(f"SELECT COUNT(DISTINCT e.paper_id) {base}", (cutoff_year,))
            n_total = cur.fetchone()[0]
            cur.execute(f"SELECT e.{col_a}, COUNT(DISTINCT e.paper_id) {base} GROUP BY e.{col_a}", (cutoff_year,))
            n_a = dict(cur.fetchall())
            cur.execute(f"SELECT e.{col_b}, COUNT(DISTINCT e.paper_id) {base} GROUP BY e.{col_b}", (cutoff_year,))
            n_b = dict(cur.fetchall())
            cur.execute(
                f"SELECT e.{col_a}, e.{col_b}, COUNT(DISTINCT e.paper_id) {base} GROUP BY e.{col_a}, e.{col_b}",
                (cutoff_year,),
            )
            observed = {(a, b): n for a, b, n in cur.fetchall()}
    return PairCounts(pair_type=pair_type, n_total=n_total, n_a=n_a, n_b=n_b, observed=observed)
