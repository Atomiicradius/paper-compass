import pytest

from ui.ids import paper_id_from_node, normalize_paper_id


@pytest.mark.parametrize("raw, expected", [
    ("W3028876793", "W3028876793"),
    ("Paper:W3028876793", "W3028876793"),          # graph node id
    ("  Paper:W3028876793  ", "W3028876793"),
    ("  W3028876793\n", "W3028876793"),
    ("paper:W3028876793", "W3028876793"),          # prefix case
    ("https://openalex.org/W3028876793", "W3028876793"),
    ("", ""),
    ("   ", ""),
])
def test_normalize_paper_id(raw, expected):
    assert normalize_paper_id(raw) == expected


def test_normalize_leaves_other_prefixes_alone():
    assert normalize_paper_id("Method:3") == "Method:3"      # not a paper id; the API will say 404


def test_paper_id_from_node():
    assert paper_id_from_node({"id": "Paper:W1", "label": "Paper"}) == "W1"
    assert paper_id_from_node({"id": "W1", "label": "Paper"}) == "W1"
