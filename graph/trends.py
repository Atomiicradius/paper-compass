"""Temporal trends from yearly SQL aggregates (plan section 11).

Yearly counts are distinct papers. Growth is the least-squares slope over a
recent window divided by the mean count in that window, so elements of
different sizes are comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoring.signals import recent_share, trend_slope

# element type -> SQL returning (element_id, name, year, n_papers)
YEARLY_SQL: dict[str, str] = {
    "method": """
        SELECT m.method_id, m.canonical_name, p.year, COUNT(DISTINCT e.paper_id)
        FROM experiment e JOIN paper p USING (paper_id) JOIN method m USING (method_id)
        WHERE p.year IS NOT NULL GROUP BY m.method_id, m.canonical_name, p.year""",
    "dataset": """
        SELECT d.dataset_id, d.canonical_name, p.year, COUNT(DISTINCT e.paper_id)
        FROM experiment e JOIN paper p USING (paper_id) JOIN dataset d USING (dataset_id)
        WHERE p.year IS NOT NULL GROUP BY d.dataset_id, d.canonical_name, p.year""",
    "task": """
        SELECT t.task_id, t.canonical_name, p.year, COUNT(DISTINCT e.paper_id)
        FROM experiment e JOIN paper p USING (paper_id) JOIN task t USING (task_id)
        WHERE p.year IS NOT NULL GROUP BY t.task_id, t.canonical_name, p.year""",
    "topic": """
        SELECT t.topic_id, t.name, p.year, COUNT(DISTINCT pt.paper_id)
        FROM paper_topic pt JOIN paper p USING (paper_id) JOIN topic t USING (topic_id)
        WHERE p.year IS NOT NULL GROUP BY t.topic_id, t.name, p.year""",
}

PAPERS_PER_YEAR_SQL = "SELECT year, COUNT(*) FROM paper WHERE year IS NOT NULL GROUP BY year ORDER BY year"


@dataclass
class Trend:
    element_type: str
    element_id: int
    name: str
    yearly: dict[int, int]
    total: int
    recent_share: float
    growth: float          # slope / mean over the window; 0 when the window is empty
    label: str             # 'emerging', 'declining' or 'stable'


def growth_rate(yearly: Mapping[int, int], cutoff_year: int, window: int = 5) -> float:
    mean = sum(yearly.get(y, 0) for y in range(cutoff_year - window + 1, cutoff_year + 1)) / window
    if mean == 0:
        return 0.0
    return trend_slope(yearly, cutoff_year, window) / mean


def classify(growth: float, threshold: float = 0.1) -> str:
    if growth >= threshold:
        return "emerging"
    if growth <= -threshold:
        return "declining"
    return "stable"


def build_trends(
    rows, element_type: str, cutoff_year: int, window: int = 5, threshold: float = 0.1
) -> list[Trend]:
    """rows: iterable of (element_id, name, year, n_papers)."""
    by_id: dict[int, tuple[str, dict[int, int]]] = {}
    for eid, name, year, n in rows:
        by_id.setdefault(eid, (name, {}))[1][year] = n
    out = []
    for eid, (name, yearly) in by_id.items():
        g = growth_rate(yearly, cutoff_year, window)
        out.append(
            Trend(
                element_type=element_type,
                element_id=eid,
                name=name,
                yearly=dict(sorted(yearly.items())),
                total=sum(c for y, c in yearly.items() if y <= cutoff_year),
                recent_share=recent_share(yearly, cutoff_year),
                growth=g,
                label=classify(g, threshold),
            )
        )
    out.sort(key=lambda t: (-t.growth, t.name))
    return out


def fetch_trends(pg_conn, element_type: str, cutoff_year: int | None = None, **kw) -> list[Trend]:
    with pg_conn.cursor() as cur:
        if cutoff_year is None:
            cur.execute("SELECT MAX(year) FROM paper")
            cutoff_year = cur.fetchone()[0]
        cur.execute(YEARLY_SQL[element_type])
        return build_trends(cur.fetchall(), element_type, cutoff_year, **kw)


def fetch_papers_per_year(pg_conn) -> dict[int, int]:
    with pg_conn.cursor() as cur:
        cur.execute(PAPERS_PER_YEAR_SQL)
        return dict(cur.fetchall())
