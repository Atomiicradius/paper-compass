"""build_evidence and build_evidence_ids. Synthetic data in a throwaway database."""
import json

import pytest

import rag_helpers as h
from rag_helpers import D1, D2, M1, M2, T1, T2, World, standard_world
from rag.evidence import (LIMITATIONS, ROLES, build_evidence, build_evidence_ids, collect_paper_ids)
from rag.nearest import nearest_existing


@pytest.fixture
def world(conn):
    return standard_world(conn)


@pytest.fixture
def pair(world):
    return ("method", world.eid("method", M1)), ("task", world.eid("task", T1))


def ids(role):
    return [r["paper_id"] for r in role]


# --- pair and corpus counts ---------------------------------------------------------------------

def test_pair_has_kinds_ids_and_canonical_names(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024)
    assert ev["pair"] == {"a": {"kind": "method", "id": pair[0][1], "name": M1},
                          "b": {"kind": "task", "id": pair[1][1], "name": T1}}


def test_corpus_counts_are_hand_computed_over_the_same_universe(conn, world, pair):
    """Universe = experiments with a method AND a task, paper year known and <= 2024:
    P01 P02 P03 P04 P05 P06 P07 P09 P11 P12 P13 = 11 papers (P08 has no task, P10 has no year).
    n_a (Method One) = P01 P02 P05 P06 P07 P09 P12 = 7.  n_b (Task One) = P03 P04 P05 P06 P07 P11 = 6.
    observed (both in ONE experiment) = P05 P06 = 2 (P07 has them in different experiments).
    expected = 7 * 6 / 11."""
    c = build_evidence(conn, *pair, 2024)["corpus"]
    assert c == {"cutoff_year": 2024, "universe_size": 11, "n_a": 7, "n_b": 6, "observed": 2,
                 "expected": pytest.approx(42 / 11)}


def test_corpus_counts_respect_the_cutoff_year(conn, world, pair):
    """Cutoff 2022 removes P09 (2023) and P11 (2024): universe 9, n_a 6, n_b 5, observed 2, expected 30/9."""
    c = build_evidence(conn, *pair, 2022)["corpus"]
    assert (c["universe_size"], c["n_a"], c["n_b"], c["observed"]) == (9, 6, 5, 2)
    assert c["expected"] == pytest.approx(30 / 9)


def test_corpus_counts_match_an_independent_raw_sql_count(conn, world, pair):
    (_, a_id), (_, b_id) = pair
    for cutoff in (2024, 2022, 2019, 2015):
        c = build_evidence(conn, *pair, cutoff)["corpus"]
        raw = lambda sql, *params: conn.execute(sql, params).fetchone()[0]
        # written differently from the module: EXISTS over paper, not a CTE over experiment
        base = ("SELECT count(*) FROM paper p WHERE p.year <= %s AND EXISTS (SELECT 1 FROM experiment e "
                "WHERE e.paper_id = p.paper_id AND e.task_id IS NOT NULL")
        assert c["universe_size"] == raw(base + ")", cutoff)
        assert c["n_a"] == raw(base + " AND e.method_id = %s)", cutoff, a_id)
        assert c["n_b"] == raw(base + " AND e.task_id = %s)", cutoff, b_id)
        assert c["observed"] == raw(base + " AND e.method_id = %s AND e.task_id = %s)", cutoff, a_id, b_id)
        brute = h.counts(world, *pair, cutoff)           # and the plain-Python computation agrees too
        assert (c["universe_size"], c["n_a"], c["n_b"], c["observed"]) == (
            brute["universe_size"], brute["n_a"], brute["n_b"], brute["observed"])
        assert c["expected"] == pytest.approx(brute["expected"])


def test_corpus_counts_equal_the_materialized_views_when_the_cutoff_covers_everything(conn):
    w = standard_world(conn, include_null_year=False)     # the views have no year filter, so no NULL-year papers
    a, b = ("method", w.eid("method", M1)), ("task", w.eid("task", T1))
    for (view,) in conn.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'").fetchall():
        conn.execute(f"REFRESH MATERIALIZED VIEW {view}")
    c = build_evidence(conn, a, b, 2100)["corpus"]
    views = {
        "n_a": conn.execute("SELECT n_papers FROM mv_method_count_mt WHERE method_id = %s", (a[1],)).fetchone()[0],
        "n_b": conn.execute("SELECT n_papers FROM mv_task_count WHERE task_id = %s", (b[1],)).fetchone()[0],
        "universe_size": conn.execute("SELECT n_papers FROM mv_universe_size WHERE pair_type = 'method_task'"
                                      ).fetchone()[0],
        "observed": conn.execute("SELECT n_papers FROM mv_method_task WHERE method_id = %s AND task_id = %s",
                                 (a[1], b[1])).fetchone()[0],
    }
    assert {k: c[k] for k in views} == views == {"n_a": 7, "n_b": 6, "universe_size": 11, "observed": 2}


@pytest.mark.parametrize("a_kind, a_name, b_kind, b_name, expected", [
    # dataset x task universe: rows with both; hand count N=11, n_a (Dataset One)=9, n_b (Task One)=6, observed=5
    ("dataset", D1, "task", T1, (11, 9, 6, 5)),
    # method x dataset universe: rows with a dataset; includes P08 (Method One, Dataset Two, no task); N=12,
    # n_a (Method One)=8, n_b (Dataset One)=9, observed=6
    ("method", M1, "dataset", D1, (12, 8, 9, 6)),
    # reversed kinds give the same universe and the same counts, with a and b swapped
    ("task", T1, "dataset", D1, (11, 6, 9, 5)),
])
def test_each_kind_pair_uses_its_own_universe(conn, world, a_kind, a_name, b_kind, b_name, expected):
    a, b = (a_kind, world.eid(a_kind, a_name)), (b_kind, world.eid(b_kind, b_name))
    c = build_evidence(conn, a, b, 2024)["corpus"]
    assert (c["universe_size"], c["n_a"], c["n_b"], c["observed"]) == expected
    assert c["expected"] == pytest.approx(expected[1] * expected[2] / expected[0])
    assert {k: v for k, v in c.items() if k not in ("cutoff_year", "expected")} == {
        k: v for k, v in h.counts(world, a, b, 2024).items() if k != "expected"}


# --- yearly ------------------------------------------------------------------------------------

def test_yearly_counts_are_hand_computed_with_gaps_filled(conn, world, pair):
    got = build_evidence(conn, *pair, 2024)["yearly"]
    # (year, papers using A, papers using B, papers using both in one experiment)
    assert [(y["year"], y["a"], y["b"], y["both"]) for y in got] == [
        (2015, 1, 0, 0), (2016, 1, 0, 0), (2017, 0, 1, 0), (2018, 1, 1, 0), (2019, 1, 1, 1), (2020, 1, 1, 1),
        (2021, 1, 1, 0), (2022, 0, 0, 0), (2023, 1, 0, 0), (2024, 0, 1, 0)]
    assert got == h.yearly(world, *pair, 2024)


def test_yearly_stops_at_the_cutoff(conn, world, pair):
    got = build_evidence(conn, *pair, 2019)["yearly"]
    assert [y["year"] for y in got] == [2015, 2016, 2017, 2018, 2019]
    assert got == h.yearly(world, *pair, 2019)


# --- roles -------------------------------------------------------------------------------------

def test_roles_have_exactly_the_four_keys_and_documented_fields(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024)
    assert tuple(ev["roles"]) == ROLES == ("supports_A", "supports_B", "bridge", "nearest_existing")
    first = ev["roles"]["supports_A"][0]
    assert set(first) == {"paper_id", "title", "year", "venue", "source_sentence", "extractor"}
    assert set(ev["roles"]["bridge"][0]) == {"paper_id", "title", "year", "venue"}
    assert set(ev["roles"]["nearest_existing"][0]) == {"paper_id", "title", "year", "venue", "source_sentence",
                                                       "extractor", "tier", "similarity", "uses"}
    assert [r["uses"] for r in ev["roles"]["nearest_existing"]][:2] == ["both", "both"]


def test_supports_a_and_b_are_the_papers_with_only_one_element_ordered_by_year_desc(conn, world, pair):
    roles = build_evidence(conn, *pair, 2024)["roles"]
    # A without B: P01 (2015) P02 (2016) P09 (2023) P12 (2018, no embedding is fine here); not P07 (has both)
    assert ids(roles["supports_A"]) == ["P09", "P12", "P02", "P01"]
    # B without A: P03 (2017) P04 (2018) P11 (2024)
    assert ids(roles["supports_B"]) == ["P11", "P04", "P03"]
    s = h.sets(world, *pair, 2024)
    assert set(ids(roles["supports_A"])) == s["supports_a"] and set(ids(roles["supports_B"])) == s["supports_b"]


def test_bridge_papers_cite_into_both_sets_or_between_them(conn, world, pair):
    """P13 cites P02 (A only) and P03 (B only); P06 cites P01 and P04; P09 (A only) cites P04 (B only);
    P11 (B only) cites P01 (A only); P12 (A only) cites P03 (B only). P05 cites only the A set, P07 only the
    B set, and P10 (no year) is outside the corpus."""
    roles = build_evidence(conn, *pair, 2024)["roles"]
    assert ids(roles["bridge"]) == ["P11", "P09", "P06", "P13", "P12"]
    assert set(ids(roles["bridge"])) == h.bridge(world, *pair, 2024)


def test_bridge_respects_the_cutoff(conn, world, pair):
    roles = build_evidence(conn, *pair, 2022)["roles"]
    assert ids(roles["bridge"]) == ["P06", "P13", "P12"]          # P09 (2023) and P11 (2024) are after the cutoff
    assert set(ids(roles["bridge"])) == h.bridge(world, *pair, 2022)


def test_nearest_existing_role_equals_the_lookup(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024, limit_per_role=5)
    assert ids(ev["roles"]["nearest_existing"]) == nearest_existing(conn, *pair, 2024, limit=5)
    assert [r["tier"] for r in ev["roles"]["nearest_existing"]][:2] == ["exact", "exact"]


def test_limit_per_role_caps_every_role(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024, limit_per_role=2)
    assert all(len(ev["roles"][role]) <= 2 for role in ROLES)
    assert ids(ev["roles"]["supports_A"]) == ["P09", "P12"] and ids(ev["roles"]["bridge"]) == ["P11", "P09"]
    assert ids(ev["roles"]["nearest_existing"]) == ["P06", "P05"]


def test_venue_is_the_venue_name_or_none(conn, world, pair):
    by_id = {r["paper_id"]: r for r in build_evidence(conn, *pair, 2024)["roles"]["supports_B"]}
    assert by_id["P11"]["venue"] == "Venue A" and by_id["P04"]["venue"] is None


# --- provenance --------------------------------------------------------------------------------

def test_source_sentences_and_extractors_are_verbatim_or_none(conn, world, pair):
    roles = build_evidence(conn, *pair, 2024)["roles"]
    a_only = {r["paper_id"]: r for r in roles["supports_A"]}
    assert (a_only["P12"]["source_sentence"], a_only["P12"]["extractor"]) == ("S P12", "ex-1")
    assert (a_only["P09"]["source_sentence"], a_only["P09"]["extractor"]) == (None, None)      # nothing stored
    near = {r["paper_id"]: r for r in roles["nearest_existing"]}
    # an exact paper shows the sentence of the experiment that has both elements
    assert (near["P06"]["source_sentence"], near["P06"]["extractor"]) == ("S P06 together", "ex-2")


def test_the_source_comes_from_an_experiment_that_has_the_element_preferring_a_stored_sentence(conn):
    w = World(conn)
    # X1 supports B in two experiments; the first has no sentence, so the second one is shown
    w.paper("X1", 2020, [(M2, D1, T1, None, None), (M2, D2, T1, "second row", "ex-2")])
    # X2 supports B in two experiments that both have sentences: the one stored first is shown
    w.paper("X2", 2021, [(M2, D1, T1, "first row", "ex-1"), (M2, D2, T1, "other row", "ex-9")])
    # X3 uses A in one experiment and B in another: it is in no role at all
    w.paper("X3", 2022, [(M1, D1, T2, "uses A", "ex-A"), (M2, D1, T1, "uses B", "ex-B")])
    a, b = ("method", w.eid("method", M1)), ("task", w.eid("task", T1))
    roles = build_evidence(conn, a, b, 2030)["roles"]
    assert ids(roles["supports_B"]) == ["X2", "X1"] and roles["supports_A"] == []
    shown = {r["paper_id"]: (r["source_sentence"], r["extractor"]) for r in roles["supports_B"]}
    assert shown == {"X1": ("second row", "ex-2"), "X2": ("first row", "ex-1")}
    assert "X3" not in collect_paper_ids(build_evidence(conn, a, b, 2030))


# --- safety and invented data ------------------------------------------------------------------

def test_every_paper_id_in_the_output_exists_in_the_paper_table(conn, world, pair):
    existing = {r[0] for r in conn.execute("SELECT paper_id FROM paper")}
    for cutoff in (2024, 2020):
        ev = build_evidence(conn, *pair, cutoff)
        found = collect_paper_ids(ev)
        assert found and found <= existing
        assert found == {r["paper_id"] for role in ev["roles"].values() for r in role}


def test_the_evidence_is_plain_json_with_string_ids(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024)
    assert json.loads(json.dumps(ev)) == ev
    assert all(isinstance(pid, str) for pid in collect_paper_ids(ev))


def test_limitations_are_a_fixed_list_of_strings(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024)
    assert ev["limitations"] == LIMITATIONS and len(LIMITATIONS) >= 3
    text = " ".join(LIMITATIONS).lower()
    assert "corpus" in text and "extraction" in text and "not proof" in text
    for phrase in ("definitely unexplored", "guaranteed", "nobody has done this"):
        assert phrase not in text


def test_an_empty_universe_gives_zero_counts_and_empty_roles(conn):
    w = World(conn)
    a, b = ("method", w.element("method", M1)), ("task", w.element("task", T1))
    ev = build_evidence(conn, a, b, 2024)
    assert ev["corpus"] == {"cutoff_year": 2024, "universe_size": 0, "n_a": 0, "n_b": 0, "observed": 0,
                            "expected": 0.0}
    assert ev["yearly"] == [] and all(ev["roles"][role] == [] for role in ROLES)


def test_unknown_elements_are_an_error_because_they_cannot_be_named(conn, world, pair):
    with pytest.raises(ValueError, match="unknown"):
        build_evidence(conn, ("method", 987654), pair[1], 2024)


def test_validation_errors(conn, world, pair):
    with pytest.raises(ValueError):
        build_evidence(conn, ("method", 1), ("method", 2), 2024)
    with pytest.raises(ValueError):
        build_evidence(conn, pair[0], pair[1], "2024")
    with pytest.raises(ValueError):
        build_evidence(conn, pair[0], pair[1], 2024, limit_per_role=0)
    with pytest.raises(ValueError, match="int"):
        build_evidence(conn, ("method", "1; DROP TABLE paper"), pair[1], 2024)


# --- build_evidence_ids ------------------------------------------------------------------------

def test_build_evidence_ids_returns_the_four_roles_as_lists_of_ids(conn, world, pair):
    ev = build_evidence(conn, *pair, 2024, limit_per_role=3)
    got = build_evidence_ids(conn, *pair, 2024, limit_per_role=3)
    assert list(got) == ["supports_A", "supports_B", "bridge", "nearest_existing"]
    assert got == {role: ids(ev["roles"][role]) for role in ROLES}
    assert all(isinstance(pid, str) for role in got.values() for pid in role)
    assert got["nearest_existing"] == nearest_existing(conn, *pair, 2024, limit=3)


def test_build_evidence_ids_validates_like_build_evidence(conn, world, pair):
    with pytest.raises(ValueError):
        build_evidence_ids(conn, ("method", 1), ("method", 2), 2024)
    with pytest.raises(ValueError):
        build_evidence_ids(conn, *pair, 2024, limit_per_role=-1)
