"""Element validation. No database needed."""
import pytest

from rag import elements
from rag.elements import (COLUMNS, Element, column_for, validate_cutoff_year, validate_element, validate_limit,
                          validate_pair)

HOSTILE = "1; DROP TABLE paper; --"


def test_the_kind_to_column_mapping_is_fixed():
    assert COLUMNS == {"method": "method_id", "dataset": "dataset_id", "task": "task_id"}
    assert elements.KINDS == ("method", "dataset", "task")
    assert [column_for(k) for k in elements.KINDS] == ["method_id", "dataset_id", "task_id"]


@pytest.mark.parametrize("kind", ["setting", "Method", "METHOD", "method ", "", "method_id", "paper", HOSTILE, None, 3])
def test_unknown_kinds_are_rejected(kind):
    with pytest.raises(ValueError):
        validate_element((kind, 1))
    with pytest.raises(ValueError):
        column_for(kind)


def test_a_valid_element_becomes_an_element_tuple():
    e = validate_element(("method", 7))
    assert e == Element("method", 7) and e.kind == "method" and e.id == 7
    assert validate_element(["task", 3]) == Element("task", 3)       # a list is fine
    assert validate_element(Element("dataset", 2)) == Element("dataset", 2)


@pytest.mark.parametrize("bad_id", ["1", HOSTILE, 1.0, 1.5, None, True, False, [1], b"1"])
def test_ids_must_be_ints_so_a_string_is_a_type_error_not_sql(bad_id):
    with pytest.raises(ValueError, match="int"):
        validate_element(("method", bad_id))


@pytest.mark.parametrize("bad_shape", [None, "method", ("method",), ("method", 1, 2), 5, {"kind": "method", "id": 1}])
def test_elements_must_be_kind_id_pairs(bad_shape):
    with pytest.raises(ValueError):
        validate_element(bad_shape)


def test_the_two_kinds_must_differ():
    with pytest.raises(ValueError, match="differ"):
        validate_pair(("method", 1), ("method", 2))
    with pytest.raises(ValueError, match="differ"):
        validate_pair(("task", 1), ("task", 1))
    a, b = validate_pair(("method", 1), ("task", 1))   # the same id number is fine for different kinds
    assert (a, b) == (Element("method", 1), Element("task", 1))


def test_pair_validation_reports_which_element_is_bad():
    with pytest.raises(ValueError, match="element_b"):
        validate_pair(("method", 1), ("nonsense", 2))
    with pytest.raises(ValueError, match="element_a"):
        validate_pair(("method", HOSTILE), ("task", 2))


@pytest.mark.parametrize("bad", ["2020", 2020.0, None, True])
def test_cutoff_year_must_be_an_int(bad):
    with pytest.raises(ValueError):
        validate_cutoff_year(bad)
    assert validate_cutoff_year(2020) == 2020


@pytest.mark.parametrize("bad", [0, -1, "5", 2.5, None, True])
def test_limit_must_be_a_positive_int(bad):
    with pytest.raises(ValueError):
        validate_limit(bad)
    assert validate_limit(1) == 1 and validate_limit(50, "limit_per_role") == 50
