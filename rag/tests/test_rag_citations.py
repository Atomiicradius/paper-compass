"""Citation markers [paper:ID]: extraction and verification. No database needed."""
import pytest

from rag.citations import extract_paper_ids, verify_citations


# --- extract_paper_ids -------------------------------------------------------------------------

def test_markers_are_found_in_order_of_first_appearance():
    assert extract_paper_ids("See [paper:W1] and later [paper:W2].") == ["W1", "W2"]


def test_duplicates_are_reported_once():
    assert extract_paper_ids("[paper:W1] ... again [paper:W1] and [paper:W2] and [paper:W1]") == ["W1", "W2"]


@pytest.mark.parametrize("marker_id", ["W1234567890", "MOCK_P001", "10.1234/abc-def_1", "doi:10.5555/x.y", "a:b:c", "W1.2"])
def test_ids_may_contain_punctuation_except_brackets_and_whitespace(marker_id):
    assert extract_paper_ids(f"Evidence [paper:{marker_id}].") == [marker_id]


def test_punctuation_around_the_marker_is_not_part_of_the_id():
    assert extract_paper_ids("(see [paper:W1]), [paper:W2]; and [paper:W3]!") == ["W1", "W2", "W3"]


def test_ids_are_case_sensitive():
    assert extract_paper_ids("[paper:w1] [paper:W1]") == ["w1", "W1"]


def test_a_marker_split_across_lines_is_not_a_marker():
    assert extract_paper_ids("[paper:\nW1]") == []
    assert extract_paper_ids("[paper:W1\n]") == []
    assert extract_paper_ids("[pa\nper:W1]") == []


def test_a_paper_id_without_a_marker_is_not_counted():
    # Only [paper:ID] markers count. A bare id in the prose is ignored (this is a documented limitation).
    assert extract_paper_ids("W999 and MOCK_P001 are relevant, see also paper W5.") == []


@pytest.mark.parametrize("text", ["[paper:]", "[paper: W1]", "[Paper:W1]", "[PAPER:W1]", "[paper:W1", "[paper:[W1]]",
                                  "paper:W1", "[paper W1]", "[papers:W1]", "[paper;W1]"])
def test_malformed_markers_give_no_ids(text):
    assert extract_paper_ids(text) == []


def test_empty_and_marker_free_text():
    assert extract_paper_ids("") == []
    assert extract_paper_ids("No citations here.") == []


def test_extract_requires_text():
    with pytest.raises(ValueError):
        extract_paper_ids(None)
    with pytest.raises(ValueError):
        extract_paper_ids(["[paper:W1]"])


# --- verify_citations --------------------------------------------------------------------------

def test_all_cited_ids_allowed():
    r = verify_citations("Closest work is [paper:W1] and [paper:W2].", {"W1", "W2", "W3"})
    assert r == {"ok": True, "cited": ["W1", "W2"], "unknown": [], "uncited_markers_count": 0,
                 "has_no_citations": False}


def test_an_unknown_id_makes_the_answer_not_ok():
    r = verify_citations("[paper:W1] and [paper:X9] and [paper:Y8]", {"W1"})
    assert r["ok"] is False and r["cited"] == ["W1", "X9", "Y8"] and r["unknown"] == ["X9", "Y8"]


def test_the_allowed_set_is_exact_and_case_sensitive():
    assert verify_citations("[paper:w1]", {"W1"})["unknown"] == ["w1"]
    assert verify_citations("[paper:W1]", {"W1 "})["unknown"] == ["W1"]


def test_allowed_ids_can_be_any_iterable():
    assert verify_citations("[paper:W1]", ["W1", "W2"])["ok"] is True
    assert verify_citations("[paper:W1]", (i for i in ["W1"]))["ok"] is True
    assert verify_citations("[paper:W1]", frozenset())["ok"] is False


def test_an_answer_that_names_no_papers_is_ok_but_flagged():
    r = verify_citations("The corpus shows 2 papers.", {"W1"})
    assert r["ok"] is True and r["has_no_citations"] is True and r["cited"] == [] and r["unknown"] == []


def test_empty_text_is_ok_and_flagged():
    r = verify_citations("", {"W1"})
    assert r == {"ok": True, "cited": [], "unknown": [], "uncited_markers_count": 0, "has_no_citations": True}


def test_a_bare_id_in_the_prose_is_not_counted_as_a_citation():
    r = verify_citations("W999 is mentioned without a marker.", {"W1"})
    assert r["cited"] == [] and r["unknown"] == [] and r["ok"] is True and r["has_no_citations"] is True


def test_duplicates_are_listed_once():
    r = verify_citations("[paper:W1] [paper:W1] [paper:X1] [paper:X1]", {"W1"})
    assert r["cited"] == ["W1", "X1"] and r["unknown"] == ["X1"]


def test_malformed_markers_are_counted_and_make_the_answer_not_ok():
    """A marker that cannot be read cannot be verified, so it must not pass silently."""
    for text in ("[paper:\nW1]", "[paper: W1]", "[Paper:W1]", "[paper:]", "[paper:W1"):
        r = verify_citations(text, {"W1"})
        assert r["uncited_markers_count"] == 1 and r["ok"] is False and r["has_no_citations"] is True, text


def test_valid_and_malformed_markers_are_counted_separately():
    r = verify_citations("[paper:W1] then [paper: W2] and [paper:W3]", {"W1", "W2", "W3"})
    assert r["cited"] == ["W1", "W3"] and r["uncited_markers_count"] == 1 and r["ok"] is False


def test_verify_requires_text():
    with pytest.raises(ValueError):
        verify_citations(None, {"W1"})
    with pytest.raises(ValueError):
        verify_citations("text", None)
