"""Nearest existing work for an element pair: the papers that come closest to using A and B together."""
from psycopg.rows import tuple_row

from .elements import validate_cutoff_year, validate_limit, validate_pair
from .universe import universe_sql


def _fetch(conn, sql, params):
    cur = conn.cursor(row_factory=tuple_row)
    cur.execute(sql, params)
    return cur.fetchall()


def _close_side(conn, universe, params, remaining, side):
    """Close-tier candidates from one side: papers that use this side's element but not the other, ranked by
    cosine similarity of their embedding to the centroid (mean) of the embeddings of papers that use the
    other element. side is "a" or "b". The SQL fragments below are fixed text."""
    this, other = ("a_id", "b_id") if side == "a" else ("b_id", "a_id")
    this_param, other_param = ("a", "b") if side == "a" else ("b", "a")
    sql = f"""
    WITH {universe},
    mine AS (SELECT DISTINCT paper_id FROM u WHERE {this} = %({this_param})s),
    theirs AS (SELECT DISTINCT paper_id FROM u WHERE {other} = %({other_param})s),
    centroid AS (SELECT avg(embedding) AS c FROM paper
                 WHERE paper_id IN (SELECT paper_id FROM theirs) AND embedding IS NOT NULL)
    SELECT p.paper_id, p.title, p.year, 1 - (p.embedding <=> centroid.c) AS similarity
    FROM paper p CROSS JOIN centroid
    WHERE p.paper_id IN (SELECT paper_id FROM mine) AND p.paper_id NOT IN (SELECT paper_id FROM theirs)
      AND p.embedding IS NOT NULL AND centroid.c IS NOT NULL
    ORDER BY similarity DESC, p.paper_id ASC
    LIMIT %(n)s"""
    rows = _fetch(conn, sql, {**params, "n": remaining})
    return [{"paper_id": r[0], "title": r[1], "year": r[2], "tier": "close", "similarity": float(r[3]),
             "uses": side} for r in rows]


def nearest_existing_detailed(conn, element_a, element_b, cutoff_year, limit=5):
    """The papers closest to using element A and element B together, as a list of dicts:
    paper_id, title, year, tier ("exact" or "close"), similarity (float, or None for exact), uses
    ("both", "a" or "b": which element the paper uses).

    Universe: experiment rows where BOTH columns of the pair's kinds are non-null, for papers whose year is
    known and <= cutoff_year (papers with a NULL year are excluded). This is the same-universe rule.

    Tier "exact": papers with one experiment row that has A and B together. Ordered by year DESC, then
    paper_id ASC. These always come first.

    Tier "close": only if there are fewer than `limit` exact papers. Two candidate groups: papers that use A
    but not B (anywhere in the universe), ranked by cosine similarity of their embedding to the centroid
    (mean embedding) of all papers that use B; and papers that use B but not A, ranked by similarity to the
    centroid of the papers that use A. The groups are merged by similarity DESC (ties by paper_id ASC).
    Papers without an embedding are skipped. A paper that uses A and B only in different experiments is in
    neither group.

    The total is at most `limit`. The order is deterministic and there are no duplicates. The result is
    empty if neither element has any paper (an unknown id simply has no papers). Raises ValueError for an
    invalid pair of elements (kinds must be method/dataset/task and differ, ids must be ints), for a
    non-int cutoff_year, and for a limit below 1.
    """
    a, b = validate_pair(element_a, element_b)
    cutoff = validate_cutoff_year(cutoff_year)
    limit = validate_limit(limit)
    universe = universe_sql(a.kind, b.kind)
    params = {"cutoff": cutoff, "a": a.id, "b": b.id}

    exact_sql = f"""
    WITH {universe}
    SELECT p.paper_id, p.title, p.year FROM paper p
    WHERE p.paper_id IN (SELECT paper_id FROM u WHERE a_id = %(a)s AND b_id = %(b)s)
    ORDER BY p.year DESC, p.paper_id ASC
    LIMIT %(n)s"""
    results = [{"paper_id": r[0], "title": r[1], "year": r[2], "tier": "exact", "similarity": None, "uses": "both"}
               for r in _fetch(conn, exact_sql, {**params, "n": limit})]

    remaining = limit - len(results)
    if remaining > 0:
        close = _close_side(conn, universe, params, remaining, "a") + _close_side(conn, universe, params,
                                                                                    remaining, "b")
        close.sort(key=lambda r: (-r["similarity"], r["paper_id"]))
        results += close[:remaining]
    return results


def nearest_existing(conn, element_a, element_b, cutoff_year, limit=5):
    """Paper ids from nearest_existing_detailed (same arguments, same order): exact papers first, then
    close papers by similarity. At most `limit` ids; [] if neither element has any paper."""
    return [r["paper_id"] for r in nearest_existing_detailed(conn, element_a, element_b, cutoff_year, limit)]
