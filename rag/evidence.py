"""The evidence chain for a research-element combination (a pair of elements A and B).

Everything is read from PostgreSQL with parameterized SQL; nothing is invented, and every paper id in the
output exists in the paper table. Counts come from the experiment table (not from the materialized views)
because they need the cutoff year. All of them are taken over the same universe (see universe.py).
"""
from psycopg.rows import tuple_row

from .elements import element_name, validate_cutoff_year, validate_limit, validate_pair
from .nearest import nearest_existing_detailed
from .universe import universe_sql

ROLES = ("supports_A", "supports_B", "bridge", "nearest_existing")

LIMITATIONS = [
    "Counts depend on the analyzed corpus and on extraction coverage: a method, dataset or task that an "
    "abstract does not state is not counted, and extraction can contain errors.",
    "Counts are taken over papers in which both elements of the pair could be extracted (the same-universe "
    "rule) and that were published up to the cutoff year; they are not counts over the whole literature.",
    "A low observed count makes a research-element combination a candidate for human review. It is not proof "
    "of a research gap.",
    "Closest existing work is chosen from the analyzed corpus by shared experiments and embedding similarity; "
    "related work that is not in the corpus cannot be shown.",
]


def _fetch(conn, sql, params):
    cur = conn.cursor(row_factory=tuple_row)
    cur.execute(sql, params)
    return cur.fetchall()


def _paper(row):
    return {"paper_id": row[0], "title": row[1], "year": row[2], "venue": row[3]}


# --- counts and yearly series ------------------------------------------------------------------

def _counts(conn, universe, params):
    sql = f"""
    WITH {universe}
    SELECT (SELECT count(DISTINCT paper_id) FROM u),
           (SELECT count(DISTINCT paper_id) FROM u WHERE a_id = %(a)s),
           (SELECT count(DISTINCT paper_id) FROM u WHERE b_id = %(b)s),
           (SELECT count(DISTINCT paper_id) FROM u WHERE a_id = %(a)s AND b_id = %(b)s)"""
    n, n_a, n_b, observed = _fetch(conn, sql, params)[0]
    return {"cutoff_year": params["cutoff"], "universe_size": n, "n_a": n_a, "n_b": n_b, "observed": observed,
            "expected": (n_a * n_b / n) if n else 0.0}


def _yearly(conn, universe, params):
    sql = f"""
    WITH {universe}
    SELECT year,
           count(DISTINCT paper_id) FILTER (WHERE a_id = %(a)s),
           count(DISTINCT paper_id) FILTER (WHERE b_id = %(b)s),
           count(DISTINCT paper_id) FILTER (WHERE a_id = %(a)s AND b_id = %(b)s)
    FROM u GROUP BY year ORDER BY year"""
    found = {row[0]: row[1:] for row in _fetch(conn, sql, params)}
    if not found:
        return []
    return [dict(zip(("year", "a", "b", "both"), (year, *found.get(year, (0, 0, 0)))))
            for year in range(min(found), max(found) + 1)]


# --- roles -------------------------------------------------------------------------------------

def _supports(conn, universe, params, side, limit):
    """Papers that use this side's element but not the other one, newest first."""
    this, other = ("a_id", "b_id") if side == "a" else ("b_id", "a_id")
    this_param, other_param = ("a", "b") if side == "a" else ("b", "a")
    sql = f"""
    WITH {universe},
    mine AS (SELECT DISTINCT paper_id FROM u WHERE {this} = %({this_param})s),
    theirs AS (SELECT DISTINCT paper_id FROM u WHERE {other} = %({other_param})s)
    SELECT p.paper_id, p.title, p.year, v.name
    FROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id
    WHERE p.paper_id IN (SELECT paper_id FROM mine) AND p.paper_id NOT IN (SELECT paper_id FROM theirs)
    ORDER BY p.year DESC, p.paper_id ASC
    LIMIT %(n)s"""
    return [_paper(r) for r in _fetch(conn, sql, {**params, "n": limit})]


def _bridge(conn, universe, params, limit):
    """Papers (year known, <= cutoff) that cite into both the A-only and the B-only set, or that are in one of
    the two sets and cite a paper of the other."""
    sql = f"""
    WITH {universe},
    pa AS (SELECT DISTINCT paper_id FROM u WHERE a_id = %(a)s),
    pb AS (SELECT DISTINCT paper_id FROM u WHERE b_id = %(b)s),
    sa AS (SELECT paper_id FROM pa WHERE paper_id NOT IN (SELECT paper_id FROM pb)),
    sb AS (SELECT paper_id FROM pb WHERE paper_id NOT IN (SELECT paper_id FROM pa))
    SELECT p.paper_id, p.title, p.year, v.name
    FROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id
    WHERE p.year IS NOT NULL AND p.year <= %(cutoff)s AND (
        (EXISTS (SELECT 1 FROM citation c WHERE c.citing_paper_id = p.paper_id
                 AND c.cited_paper_id IN (SELECT paper_id FROM sa))
         AND EXISTS (SELECT 1 FROM citation c WHERE c.citing_paper_id = p.paper_id
                     AND c.cited_paper_id IN (SELECT paper_id FROM sb)))
        OR (p.paper_id IN (SELECT paper_id FROM sa)
            AND EXISTS (SELECT 1 FROM citation c WHERE c.citing_paper_id = p.paper_id
                        AND c.cited_paper_id IN (SELECT paper_id FROM sb)))
        OR (p.paper_id IN (SELECT paper_id FROM sb)
            AND EXISTS (SELECT 1 FROM citation c WHERE c.citing_paper_id = p.paper_id
                        AND c.cited_paper_id IN (SELECT paper_id FROM sa))))
    ORDER BY p.year DESC, p.paper_id ASC
    LIMIT %(n)s"""
    return [_paper(r) for r in _fetch(conn, sql, {**params, "n": limit})]


def _venues(conn, paper_ids):
    if not paper_ids:
        return {}
    rows = _fetch(conn, "SELECT p.paper_id, v.name FROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id "
                        "WHERE p.paper_id = ANY(%s)", (list(paper_ids),))
    return dict(rows)


def _sources(conn, universe, params, paper_ids, condition):
    """{paper_id: (source_sentence, extractor)} from one experiment per paper that matches `condition` (fixed
    text): the first stored experiment that has a sentence, else the first experiment."""
    if not paper_ids:
        return {}
    sql = f"""
    WITH {universe}
    SELECT DISTINCT ON (paper_id) paper_id, source_sentence, extractor FROM u
    WHERE paper_id = ANY(%(ids)s) AND {condition}
    ORDER BY paper_id, (source_sentence IS NULL), experiment_id"""
    return {r[0]: (r[1], r[2]) for r in _fetch(conn, sql, {**params, "ids": list(paper_ids)})}


def _attach_sources(conn, universe, params, entries, condition):
    found = _sources(conn, universe, params, [e["paper_id"] for e in entries], condition)
    for entry in entries:
        entry["source_sentence"], entry["extractor"] = found.get(entry["paper_id"], (None, None))


def _roles(conn, a, b, cutoff, limit, with_sources):
    universe = universe_sql(a.kind, b.kind)
    params = {"cutoff": cutoff, "a": a.id, "b": b.id}
    roles = {"supports_A": _supports(conn, universe, params, "a", limit),
             "supports_B": _supports(conn, universe, params, "b", limit),
             "bridge": _bridge(conn, universe, params, limit)}

    nearest = nearest_existing_detailed(conn, (a.kind, a.id), (b.kind, b.id), cutoff, limit)
    venues = _venues(conn, [r["paper_id"] for r in nearest])
    uses = {r["paper_id"]: r["uses"] for r in nearest}
    roles["nearest_existing"] = [
        {"paper_id": r["paper_id"], "title": r["title"], "year": r["year"], "venue": venues.get(r["paper_id"]),
         "tier": r["tier"], "similarity": r["similarity"], "uses": r["uses"]} for r in nearest]

    if with_sources:
        _attach_sources(conn, universe, params, roles["supports_A"], "a_id = %(a)s")
        _attach_sources(conn, universe, params, roles["supports_B"], "b_id = %(b)s")
        for side, condition in (("both", "a_id = %(a)s AND b_id = %(b)s"), ("a", "a_id = %(a)s"),
                                ("b", "b_id = %(b)s")):
            group = [e for e in roles["nearest_existing"] if uses[e["paper_id"]] == side]
            _attach_sources(conn, universe, params, group, condition)
    return {role: roles[role] for role in ROLES}


# --- public API --------------------------------------------------------------------------------

def build_evidence(conn, element_a, element_b, cutoff_year, limit_per_role=5):
    """The evidence chain for the combination of element A and element B, as plain JSON-able data.

    element_a / element_b are (kind, id) with kind in method/dataset/task (kinds must differ, ids must be
    ints). Papers are counted once (distinct) over the universe of the pair: experiment rows in which both
    columns are present, for papers with a known year <= cutoff_year. Returned keys:

      pair         kinds, ids and canonical names of both elements
      corpus       cutoff_year, universe_size (N), n_a, n_b, observed (papers with A and B together in one
                   experiment) and expected = n_a * n_b / N (0.0 if N is 0)
      yearly       list of {year, a, b, both}: papers per year using A, using B, and using both together,
                   from the earliest to the latest year in the universe, years without papers as zeros
                   ([] if the universe is empty)
      roles        supports_A (papers that use A but not B), supports_B, bridge (papers that cite into both
                   of those two sets, or that are in one and cite the other), nearest_existing (the lookup
                   of nearest.py: exact papers first, then close ones). Each is a list of at most
                   limit_per_role dicts {paper_id, title, year, venue}, newest first (year DESC, paper_id);
                   nearest_existing keeps its own order and adds tier ("exact"/"close"), similarity (None
                   for exact) and uses ("both", "a" or "b": which element the paper uses). supports_A/B and
                   nearest_existing also carry source_sentence and extractor, verbatim from one stored
                   experiment of that paper that has the element (None when nothing is stored)
      limitations  the fixed list LIMITATIONS

    Raises ValueError for an invalid pair, a non-int cutoff_year, limit_per_role below 1, or an element id
    that does not exist in its vocabulary table (it cannot be named, so there is nothing to report).
    """
    a, b = validate_pair(element_a, element_b)
    cutoff = validate_cutoff_year(cutoff_year)
    limit = validate_limit(limit_per_role, "limit_per_role")
    names = {}
    for label, element in (("a", a), ("b", b)):
        names[label] = element_name(conn, element)
        if names[label] is None:
            raise ValueError(f"unknown {element.kind} id {element.id}")

    universe = universe_sql(a.kind, b.kind)
    params = {"cutoff": cutoff, "a": a.id, "b": b.id}
    return {
        "pair": {"a": {"kind": a.kind, "id": a.id, "name": names["a"]},
                 "b": {"kind": b.kind, "id": b.id, "name": names["b"]}},
        "corpus": _counts(conn, universe, params),
        "yearly": _yearly(conn, universe, params),
        "roles": _roles(conn, a, b, cutoff, limit, with_sources=True),
        "limitations": list(LIMITATIONS),
    }


def build_evidence_ids(conn, element_a, element_b, cutoff_year, limit_per_role=5):
    """The four evidence roles as lists of paper ids, ready to be written to opportunity_evidence rows:
    {"supports_A": [...], "supports_B": [...], "bridge": [...], "nearest_existing": [...]}.

    Same arguments, definitions, order and limits as build_evidence (nearest_existing equals
    nearest_existing(...) with limit=limit_per_role). Does not look up names or source sentences, so an
    element id that is missing from its vocabulary table just gives empty lists. Raises ValueError for an
    invalid pair, cutoff_year or limit_per_role.
    """
    a, b = validate_pair(element_a, element_b)
    cutoff = validate_cutoff_year(cutoff_year)
    limit = validate_limit(limit_per_role, "limit_per_role")
    roles = _roles(conn, a, b, cutoff, limit, with_sources=False)
    return {role: [entry["paper_id"] for entry in roles[role]] for role in ROLES}


def collect_paper_ids(evidence):
    """The set of every paper id that appears in an evidence dict's roles. This is the allowed set for
    verify_citations: an explanation may only cite papers from it."""
    return {entry["paper_id"] for role in evidence["roles"].values() for entry in role}
