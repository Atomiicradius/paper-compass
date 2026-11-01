"""The universe of an element pair (the same-universe rule of data-and-contracts.md).

For a pair of kinds, the universe is the set of experiment rows in which BOTH of the pair's columns are
non-null, for papers with a known year at or before the cutoff year. n_a, n_b, the total N and the
observed count are all taken over this one set of papers, and papers are counted once (distinct).
"""
from .elements import column_for


def universe_sql(kind_a, kind_b):
    """SQL text of a CTE named `u`, to be placed after WITH. Parameter: %(cutoff)s.

    Columns of u: experiment_id, paper_id, a_id (the value of kind_a's column), b_id (kind_b's column),
    year, source_sentence, extractor. The column names come only from the fixed mapping in elements.py.
    """
    column_a, column_b = column_for(kind_a), column_for(kind_b)
    return f"""u AS (
    SELECT e.experiment_id, e.paper_id, e.{column_a} AS a_id, e.{column_b} AS b_id, p.year,
           e.source_sentence, e.extractor
    FROM experiment e JOIN paper p ON p.paper_id = e.paper_id
    WHERE e.{column_a} IS NOT NULL AND e.{column_b} IS NOT NULL AND p.year IS NOT NULL AND p.year <= %(cutoff)s
)"""
