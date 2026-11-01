"""summarize_evidence: a deterministic template, no LLM. The evidence dicts here are hand-made, plus one
integration test on a synthetic database."""
import copy
import re

import pytest

import rag_helpers as h
from rag_helpers import M1, T1, standard_world
from rag.citations import extract_paper_ids, verify_citations
from rag.evidence import LIMITATIONS, build_evidence, collect_paper_ids
from rag.summary import summarize_evidence

# phrases AGENTS.md says to avoid (checked in lower case)
FORBIDDEN = ["definitely unexplored", "guaranteed research gap", "guaranteed gap", "guaranteed", "nobody has done this",
             "ai discovered a new research area", "no one has", "never been done"]
HEADINGS = ["What the corpus shows", "What the system infers", "Closest existing work", "Limitations"]


def entry(pid, year, tier="exact", similarity=None, sentence="We combine them.", extractor="ex-1", title=None,
          uses=None):
    return {"paper_id": pid, "title": title or f"Title {pid}", "year": year, "venue": None,
            "source_sentence": sentence, "extractor": extractor, "tier": tier, "similarity": similarity,
            "uses": uses or ("both" if tier == "exact" else "a")}


def make_evidence(n=11, n_a=7, n_b=6, observed=2, nearest=None, years=None):
    nearest = [entry("W1", 2020), entry("W2", 2019, "close", 0.8123, sentence=None, extractor=None)] \
        if nearest is None else nearest
    return {
        "pair": {"a": {"kind": "method", "id": 1, "name": "Method One"},
                 "b": {"kind": "task", "id": 2, "name": "Task One"}},
        "corpus": {"cutoff_year": 2024, "universe_size": n, "n_a": n_a, "n_b": n_b, "observed": observed,
                   "expected": (n_a * n_b / n) if n else 0.0},
        "yearly": years if years is not None else [{"year": y, "a": 1, "b": 1, "both": 0} for y in (2022, 2023, 2024)],
        "roles": {"supports_A": [], "supports_B": [], "bridge": [], "nearest_existing": nearest},
        "limitations": list(LIMITATIONS),
    }


def section(text, heading):
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))[heading].strip()


# --- structure ---------------------------------------------------------------------------------

def test_the_four_sections_appear_in_order():
    text = summarize_evidence(make_evidence())
    positions = [text.index(f"## {h_}") for h_ in HEADINGS]
    assert positions == sorted(positions)
    assert re.findall(r"^## (.+)$", text, flags=re.M) == HEADINGS


def test_what_the_corpus_shows_states_the_counts_as_observations():
    shows = section(summarize_evidence(make_evidence()), "What the corpus shows")
    assert "2024" in shows and "11 papers" in shows
    assert "Method One" in shows and "Task One" in shows
    assert re.search(r"\b7 papers\b", shows) and re.search(r"\b6 papers\b", shows)
    assert re.search(r"together in 2 papers", shows) and "3.8" in shows            # 7 * 6 / 11 = 3.818...
    assert "2022" in shows and "2024" in shows                                        # the recent years


def test_singular_and_plural_are_handled():
    shows = section(summarize_evidence(make_evidence(n=1, n_a=1, n_b=1, observed=1)), "What the corpus shows")
    assert "1 paper " in shows or "1 paper." in shows
    assert "1 papers" not in shows


def test_the_inference_is_one_clear_sentence_for_a_weakly_represented_pair():
    infers = section(summarize_evidence(make_evidence()), "What the system infers")   # observed 2 < expected 3.8
    assert len(re.findall(r"\.(?:\s|$)", infers)) == 1 and "\n" not in infers      # one sentence (3.8 is a number)
    assert "potentially underexplored" in infers
    assert "analyzed corpus" in infers
    assert "candidate" in infers and "review" in infers and "not a proven" in infers
    assert "2 observed" in infers and "3.8" in infers


def test_a_well_represented_pair_is_not_called_underexplored():
    infers = section(summarize_evidence(make_evidence(observed=6, n_a=7, n_b=6)), "What the system infers")  # 6 >= 3.8
    assert "underexplored" not in infers.lower()
    assert "not weakly represented" in infers and "not flagged" in infers


def test_exactly_as_many_as_expected_is_not_flagged():
    infers = section(summarize_evidence(make_evidence(n=4, n_a=2, n_b=2, observed=1)), "What the system infers")
    assert "underexplored" not in infers.lower()                                       # expected 1.0, observed 1


@pytest.mark.parametrize("kwargs", [dict(n=0, n_a=0, n_b=0, observed=0), dict(n_a=0, observed=0),
                                    dict(n_b=0, observed=0)])
def test_too_little_data_gives_no_inference(kwargs):
    infers = section(summarize_evidence(make_evidence(**kwargs)), "What the system infers")
    assert "too little" in infers and "underexplored" not in infers.lower()


# --- closest existing work and citations -------------------------------------------------------

def test_closest_existing_work_lists_papers_with_markers_in_order():
    evidence = make_evidence()
    closest = section(summarize_evidence(evidence), "Closest existing work")
    assert extract_paper_ids(closest) == ["W1", "W2"]
    lines = [line for line in closest.splitlines() if line.startswith("- ")]
    assert "[paper:W1]" in lines[0] and "Title W1" in lines[0] and "(2020)" in lines[0]
    assert "both" in lines[0] and "Method One" in lines[0] and "Task One" in lines[0]
    assert "[paper:W2]" in lines[1] and "0.81" in lines[1]                           # close tier shows its similarity
    assert 'uses "Method One" but not "Task One"' in lines[1]
    assert 'similar to papers that use "Task One"' in lines[1]


def test_a_close_paper_from_the_b_side_is_described_the_other_way_round():
    evidence = make_evidence(nearest=[entry("W9", 2021, "close", 0.5, uses="b")])
    line = [x for x in section(summarize_evidence(evidence), "Closest existing work").splitlines()
            if x.startswith("- ")][0]
    assert 'uses "Task One" but not "Method One"' in line and 'similar to papers that use "Method One"' in line


def test_source_sentences_are_quoted_verbatim_and_only_when_stored():
    closest = section(summarize_evidence(make_evidence()), "Closest existing work")
    assert 'Source sentence: "We combine them."' in closest
    assert closest.count("Source sentence:") == 1                                      # W2 has none


def test_every_marker_in_the_summary_passes_verification_against_the_evidence():
    for evidence in (make_evidence(), make_evidence(observed=6), make_evidence(nearest=[]),
                     make_evidence(nearest=[entry(f"W{i}", 2000 + i) for i in range(5)])):
        text = summarize_evidence(evidence)
        result = verify_citations(text, collect_paper_ids(evidence))
        assert result["ok"] is True and result["unknown"] == [] and result["uncited_markers_count"] == 0
        assert set(result["cited"]) == {r["paper_id"] for r in evidence["roles"]["nearest_existing"]}


def test_a_title_cannot_forge_a_citation_marker():
    evidence = make_evidence(nearest=[entry("W1", 2020, title="Trick [paper:FAKE9] title",
                                            sentence="See [paper:FAKE8] too")])
    text = summarize_evidence(evidence)
    assert extract_paper_ids(text) == ["W1"]
    assert verify_citations(text, collect_paper_ids(evidence))["ok"] is True


def test_no_nearest_papers_is_stated_without_markers():
    text = summarize_evidence(make_evidence(nearest=[]))
    assert "No closely related papers" in section(text, "Closest existing work")
    assert extract_paper_ids(text) == []


# --- wording rules -----------------------------------------------------------------------------

@pytest.mark.parametrize("evidence", [make_evidence(), make_evidence(observed=6), make_evidence(n=0, n_a=0, n_b=0,
                                                                                               observed=0),
                                      make_evidence(nearest=[]), make_evidence(observed=0)])
def test_the_summary_never_uses_forbidden_phrases(evidence):
    text = summarize_evidence(evidence).lower()
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase


def test_limitations_are_listed_verbatim():
    limitations = section(summarize_evidence(make_evidence()), "Limitations")
    for item in LIMITATIONS:
        assert f"- {item}" in limitations


def test_the_summary_is_deterministic():
    evidence = make_evidence()
    assert summarize_evidence(evidence) == summarize_evidence(copy.deepcopy(evidence))


def test_the_input_is_not_modified():
    evidence = make_evidence()
    before = copy.deepcopy(evidence)
    summarize_evidence(evidence)
    assert evidence == before


@pytest.mark.parametrize("remove", ["pair", "corpus", "yearly", "roles", "limitations"])
def test_missing_evidence_parts_are_an_error(remove):
    evidence = make_evidence()
    del evidence[remove]
    with pytest.raises(ValueError, match=remove):
        summarize_evidence(evidence)


def test_a_non_dict_is_an_error():
    with pytest.raises(ValueError):
        summarize_evidence(None)


# --- with real evidence from a database --------------------------------------------------------

def test_a_summary_of_real_evidence_passes_all_checks(conn):
    world = standard_world(conn)
    a, b = ("method", world.eid("method", M1)), ("task", world.eid("task", T1))
    evidence = build_evidence(conn, a, b, 2024)
    text = summarize_evidence(evidence)
    result = verify_citations(text, collect_paper_ids(evidence))
    assert result["ok"] is True and result["has_no_citations"] is False
    assert result["cited"] == [r["paper_id"] for r in evidence["roles"]["nearest_existing"]]
    assert all(pid in world.papers for pid in result["cited"])                        # nothing invented
    shows = section(text, "What the corpus shows")
    assert "11 papers" in shows and "7 papers" in shows and "6 papers" in shows and "3.8" in shows
    assert "potentially underexplored" in section(text, "What the system infers")      # 2 observed < 3.8 expected
    assert not [p for p in FORBIDDEN if p in text.lower()]
