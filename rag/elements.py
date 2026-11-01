"""Research elements and their validation.

An element is a (kind, id) pair: kind is "method", "dataset" or "task"; id is the integer primary key in
the matching vocabulary table. The experiment column for each kind comes ONLY from the fixed mapping
COLUMNS below, never from a caller-supplied string, so no SQL is ever built from user input.
"""
from typing import NamedTuple

KINDS = ("method", "dataset", "task")

# kind -> column of the experiment table. The only source of column names in this package.
COLUMNS = {"method": "method_id", "dataset": "dataset_id", "task": "task_id"}

# kind -> (table, id column, name column), used to look up canonical names.
VOCABULARY = {
    "method": ("method", "method_id", "canonical_name"),
    "dataset": ("dataset", "dataset_id", "canonical_name"),
    "task": ("task", "task_id", "canonical_name"),
}


class Element(NamedTuple):
    kind: str
    id: int


def column_for(kind):
    """The experiment column for a kind. Raises ValueError for anything that is not a known kind."""
    if not isinstance(kind, str) or kind not in COLUMNS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")
    return COLUMNS[kind]


def validate_element(element, label="element"):
    """Return the element as Element(kind, id).

    Accepts a (kind, id) tuple or list. Raises ValueError if the shape is wrong, the kind is not one of
    method/dataset/task, or the id is not an int (a numeric string, a float, a bool or text such as
    "1; DROP TABLE paper" is rejected, so ids can never carry SQL).
    """
    if not isinstance(element, (tuple, list)) or len(element) != 2:
        raise ValueError(f"{label} must be a (kind, id) pair, got {element!r}")
    kind, element_id = element
    try:
        column_for(kind)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from None
    if isinstance(element_id, bool) or not isinstance(element_id, int):
        raise ValueError(f"{label}: id must be an int, got {type(element_id).__name__} {element_id!r}")
    return Element(kind, element_id)


def validate_pair(element_a, element_b):
    """Validate both elements and require that their kinds differ. Returns (Element, Element).

    A pair is two different kinds, for example (method, task); the same id number may appear in both
    kinds because the ids belong to different tables.
    """
    a = validate_element(element_a, "element_a")
    b = validate_element(element_b, "element_b")
    if a.kind == b.kind:
        raise ValueError(f"the two elements must be of different kinds, got two of kind {a.kind!r}")
    return a, b


def validate_cutoff_year(cutoff_year):
    """The cutoff year as an int. Raises ValueError for anything else (text, float, bool, None)."""
    if isinstance(cutoff_year, bool) or not isinstance(cutoff_year, int):
        raise ValueError(f"cutoff_year must be an int, got {cutoff_year!r}")
    return cutoff_year


def validate_limit(limit, name="limit"):
    """A positive int. Raises ValueError for 0, negatives, text, floats, bools and None."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"{name} must be an int of at least 1, got {limit!r}")
    return limit


def element_name(conn, element):
    """The canonical name of an element, or None if no such id exists in its vocabulary table."""
    kind, element_id = validate_element(element)
    table, id_column, name_column = VOCABULARY[kind]
    row = conn.execute(f"SELECT {name_column} FROM {table} WHERE {id_column} = %s", (element_id,)).fetchone()
    return row[0] if row else None
