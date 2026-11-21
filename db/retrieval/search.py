"""Vector search and keyword search over the paper table, each as one parameterized SQL statement.

User-supplied values (names, ids, numbers, the query vector, the search text) only ever travel as
query parameters. The SQL text is assembled from fixed fragments in this file, never from user strings.
"""
import math
import re

from psycopg.rows import tuple_row
from psycopg.types.numeric import Float4

EXPECTED_DIM = 768
ITERATIVE_SCAN_MODES = ("strict_order", "relaxed_order", "off")
MATCH_MODES = ("same_experiment", "any")

# (filter name, entity table, alias table or None, id column) - fixed, not user input
ENTITY_FILTERS = (
    ("methods", "method", "method_alias", "method_id", "canonical_name"),
    ("datasets", "dataset", "dataset_alias", "dataset_id", "canonical_name"),
    ("tasks", "task", "task_alias", "task_id", "canonical_name"),
)

ENTITY_COLUMNS = """,
    (SELECT coalesce(array_agg(DISTINCT m.canonical_name ORDER BY m.canonical_name), '{}')
       FROM experiment e JOIN method m ON m.method_id = e.method_id WHERE e.paper_id = p.paper_id) AS methods,
    (SELECT coalesce(array_agg(DISTINCT d.canonical_name ORDER BY d.canonical_name), '{}')
       FROM experiment e JOIN dataset d ON d.dataset_id = e.dataset_id WHERE e.paper_id = p.paper_id) AS datasets,
    (SELECT coalesce(array_agg(DISTINCT t.canonical_name ORDER BY t.canonical_name), '{}')
       FROM experiment e JOIN task t ON t.task_id = e.task_id WHERE e.paper_id = p.paper_id) AS tasks"""


# --- validation -------------------------------------------------------------------------------

def _int(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}, got {value}")
    return value


def _names(values, label):
    """A list of names, normalized for matching: whitespace collapsed, lower case."""
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError(f"{label} must be a list of names, got {values!r}")
    names = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must contain only non-empty strings, got {value!r}")
        names.append(" ".join(value.split()).lower())
    return names


def _checked_numbers(vector):
    """The query vector as a list of floats after checking it. Raises ValueError."""
    try:
        values = list(vector)
    except TypeError:
        raise ValueError(f"the query vector must be a sequence of {EXPECTED_DIM} numbers") from None
    if len(values) != EXPECTED_DIM:
        raise ValueError(f"the query vector must have {EXPECTED_DIM} dimensions, got {len(values)}")
    try:
        numbers = [float(x) for x in values]
    except (TypeError, ValueError):
        raise ValueError("the query vector must contain only numbers") from None
    if not all(math.isfinite(x) for x in numbers):
        raise ValueError("the query vector contains NaN or infinite values (it must be finite)")
    if not any(numbers):
        raise ValueError("the query vector is all zeros; cosine similarity is undefined for a zero vector")
    return numbers


def check_query_vector(vector):
    """Return the query vector as a pgvector text literal after checking it. Raises ValueError."""
    return "[" + ",".join(repr(x) for x in _checked_numbers(vector)) + "]"


def vector_parameter(vector):
    """The checked query vector as a list of float4 values. psycopg sends it in BINARY format as a real[] (about
    3 KB). The text literal above is about 8.5 KB, and on a Windows host talking to the Docker container a
    parameter over about 8 KB added about 44 ms to every query. Use it as %b::real[]::vector."""
    return [Float4(x) for x in _checked_numbers(vector)]


# --- TEMPORARY WORKAROUND: collapse records with the same title ---------------------------------
# The corpus has records that are the same paper under several OpenAlex ids and DOIs (51 titles occur more than
# once in pc_pilot). collapse_same_title=True hides the extra ones at search time. It does not delete or merge any
# row. Remove it once ingest de-duplicates (Person 1; see extraction/accuracy_report.md, Limitations).
MAX_COLLAPSE_CANDIDATES = 5000  # most rows fetched to find enough distinct titles


def normalize_title(title):
    """Lowercase, punctuation stripped (hyphens included, so 'Low-Resource' becomes 'lowresource'), whitespace
    collapsed."""
    return " ".join(re.sub(r"[^\w\s]|_", "", title.lower()).split())


def _check_collapse(collapse_same_title):
    if not isinstance(collapse_same_title, bool):
        raise ValueError(f"collapse_same_title must be True or False, got {collapse_same_title!r}")


def _collapse(fetch, top_k, offset, score_name):
    """fetch(n) returns the best n results in rank order. Keep the best-scored result per normalized title (when
    two records have exactly the same score, the smaller paper_id, so the choice does not change between runs),
    fetching more candidates until offset + top_k distinct titles are found or the candidates run out. offset and
    top_k then apply to the collapsed list."""
    needed = offset + top_k
    limit = max(needed * 5, 50)
    while True:
        rows = fetch(limit)
        position, kept = {}, []
        for row in rows:
            key = normalize_title(row["title"])
            if key not in position:
                position[key] = len(kept)
                kept.append(row)
            else:
                current = kept[position[key]]
                if row[score_name] == current[score_name] and row["paper_id"] < current["paper_id"]:
                    kept[position[key]] = row  # exact tie: the smaller paper_id wins
        if len(kept) >= needed or len(rows) < limit or limit >= MAX_COLLAPSE_CANDIDATES:
            return kept[offset:offset + top_k]
        limit = min(limit * 4, MAX_COLLAPSE_CANDIDATES)


# --- shared filters ---------------------------------------------------------------------------

def _entity_condition(table, alias_table, id_column, name_column, names):
    """SQL condition on experiment row e: its entity is one of the given names or aliases."""
    sql = (f"e.{id_column} IN (SELECT {id_column} FROM {table} WHERE lower({name_column}) = ANY(%s) "
           f"UNION SELECT {id_column} FROM {alias_table} WHERE lower(alias) = ANY(%s))")
    return sql, [names, names]


def _filters(year_min, year_max, venues, methods, datasets, tasks, exclude_ids, match):
    """Return (list of SQL conditions on p / v, list of parameters). Conditions are fixed text."""
    if match not in MATCH_MODES:
        raise ValueError(f"match must be one of {', '.join(MATCH_MODES)}, got {match!r}")
    clauses, params = [], []
    if year_min is not None:
        clauses.append("p.year >= %s")
        params.append(_int(year_min, "year_min"))
    if year_max is not None:
        clauses.append("p.year <= %s")
        params.append(_int(year_max, "year_max"))
    if venues:
        clauses.append("lower(v.name) = ANY(%s)")
        params.append(_names(venues, "venues"))
    conditions, condition_params = [], []
    for (label, table, alias_table, id_column, name_column), values in zip(
            ENTITY_FILTERS, (methods, datasets, tasks)):
        if values:
            sql, entity_params = _entity_condition(table, alias_table, id_column, name_column,
                                                   _names(values, label))
            conditions.append(sql)
            condition_params.append(entity_params)
    if match == "same_experiment" and conditions:
        # one EXISTS: a single experiment row must satisfy every supplied filter
        clauses.append("EXISTS (SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id AND "
                       + " AND ".join(conditions) + ")")
        for entity_params in condition_params:
            params.extend(entity_params)
    else:
        # "any": each filter gets its own EXISTS, so different experiments may satisfy different filters
        for sql, entity_params in zip(conditions, condition_params):
            clauses.append("EXISTS (SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id AND " + sql + ")")
            params.extend(entity_params)
    if exclude_ids:
        if isinstance(exclude_ids, (str, bytes)) or not all(isinstance(i, str) for i in exclude_ids):
            raise ValueError("exclude_ids must be a list of paper_id strings")
        clauses.append("NOT (p.paper_id = ANY(%s))")
        params.append(list(exclude_ids))
    return clauses, params


def _to_dicts(rows, score_name, convert_score, include_entities):
    out = []
    for row in rows:
        item = {"paper_id": row[0], "title": row[1], "year": row[2], "venue": row[3],
                score_name: convert_score(row[4])}
        if include_entities:
            item["methods"], item["datasets"], item["tasks"] = row[5], row[6], row[7]
        out.append(item)
    return out


# --- vector search ----------------------------------------------------------------------------

def search(conn, query_vector, top_k=10, offset=0, year_min=None, year_max=None, venues=None, methods=None,
           datasets=None, tasks=None, exclude_ids=None, include_entities=False, ef_search=100,
           iterative_scan="strict_order", match="same_experiment", collapse_same_title=False):
    """Nearest papers to query_vector by cosine similarity, with optional filters.

    Returns dicts: paper_id, title, year, venue, similarity (1 - cosine distance), plus methods, datasets
    and tasks (lists of canonical names) when include_entities is true. Papers without an embedding are
    never returned.

    methods / datasets / tasks take canonical names or aliases; several values inside one filter mean OR.
    match decides how different entity filters combine:
      "same_experiment" (default): ONE experiment of the paper must satisfy all supplied filters, e.g.
          methods=A and tasks=B needs an experiment that uses A on B.
      "any": each filter may be satisfied by a different experiment of the paper.
    With a single entity filter both modes are identical. Year, venue and exclusion filters always AND.

    pgvector applies filters after the HNSW scan, so a selective filter can starve the result. Iterative
    scan (pgvector 0.8: hnsw.iterative_scan) keeps scanning until top_k rows pass the filters or
    hnsw.max_scan_tuples (default 20000) index entries were visited. The settings are applied with
    set_config(..., true), i.e. for this call's transaction only.

    collapse_same_title (default False) is a TEMPORARY WORKAROUND for duplicate records: it keeps only the
    best-scored record per normalized title (lowercase, punctuation stripped, whitespace collapsed) and still
    returns top_k results when enough distinct titles exist. offset applies to the collapsed list. No row is changed.
    """
    vector = vector_parameter(query_vector)
    _check_collapse(collapse_same_title)
    _int(top_k, "top_k", minimum=1)
    _int(offset, "offset", minimum=0)
    _int(ef_search, "ef_search", minimum=1, maximum=1000)
    if iterative_scan not in ITERATIVE_SCAN_MODES:
        raise ValueError(f"iterative_scan must be one of {', '.join(ITERATIVE_SCAN_MODES)}, got {iterative_scan!r}")
    if collapse_same_title:
        return _collapse(lambda n: search(conn, query_vector, top_k=n, offset=0, year_min=year_min, year_max=year_max,
                                          venues=venues, methods=methods, datasets=datasets, tasks=tasks,
                                          exclude_ids=exclude_ids, include_entities=include_entities,
                                          ef_search=ef_search, iterative_scan=iterative_scan, match=match),
                         top_k, offset, "similarity")
    clauses, filter_params = _filters(year_min, year_max, venues, methods, datasets, tasks, exclude_ids, match)

    sql = ("SELECT p.paper_id, p.title, p.year, v.name, p.embedding <=> %b::real[]::vector AS distance"
           + (ENTITY_COLUMNS if include_entities else "")
           + "\nFROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id"
           + "\nWHERE " + " AND ".join(["p.embedding IS NOT NULL"] + clauses)
           + "\nORDER BY distance LIMIT %s OFFSET %s")
    params = [vector] + filter_params + [top_k, offset]

    with conn.transaction():
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute("SELECT set_config('hnsw.ef_search', %s, true), set_config('hnsw.iterative_scan', %s, true)",
                    (str(ef_search), iterative_scan))
        cur.execute(sql, params)
        rows = cur.fetchall()
    return _to_dicts(rows, "similarity", lambda distance: 1.0 - float(distance), include_entities)


# --- keyword baseline -------------------------------------------------------------------------

def keyword_search(conn, text, top_k=10, offset=0, year_min=None, year_max=None, venues=None, methods=None,
                   datasets=None, tasks=None, exclude_ids=None, include_entities=False, match="same_experiment",
                   collapse_same_title=False):
    """PostgreSQL full-text search over title + abstract (English), ranked by ts_rank. Computed on the
    fly, no index. Same filters (and the same `match` modes) as search(); results carry `score` instead of
    `similarity`. Works for papers without an embedding. collapse_same_title: see search() (temporary workaround)."""
    if not isinstance(text, str):
        raise ValueError(f"text must be a string, got {text!r}")
    _check_collapse(collapse_same_title)
    _int(top_k, "top_k", minimum=1)
    _int(offset, "offset", minimum=0)
    if collapse_same_title:
        return _collapse(lambda n: keyword_search(conn, text, top_k=n, offset=0, year_min=year_min, year_max=year_max,
                                                  venues=venues, methods=methods, datasets=datasets, tasks=tasks,
                                                  exclude_ids=exclude_ids, include_entities=include_entities,
                                                  match=match), top_k, offset, "score")
    clauses, filter_params = _filters(year_min, year_max, venues, methods, datasets, tasks, exclude_ids, match)
    if not text.strip():
        return []

    sql = ("SELECT p.paper_id, p.title, p.year, v.name, ts_rank(d.doc, q.query) AS score"
           + (ENTITY_COLUMNS if include_entities else "")
           + "\nFROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id"
           + "\nCROSS JOIN LATERAL (SELECT to_tsvector('english', p.title || ' ' || coalesce(p.abstract, '')) AS doc) d"
           + "\nCROSS JOIN (SELECT plainto_tsquery('english', %s) AS query) q"
           + "\nWHERE " + " AND ".join(["d.doc @@ q.query"] + clauses)
           + "\nORDER BY score DESC, p.paper_id LIMIT %s OFFSET %s")
    params = [text] + filter_params + [top_k, offset]

    cur = conn.cursor(row_factory=tuple_row)
    cur.execute(sql, params)
    rows = cur.fetchall()
    return _to_dicts(rows, "score", float, include_entities)
