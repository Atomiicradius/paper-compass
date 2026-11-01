"""nearest_existing: exact tier, close tier, cutoff, limits. Synthetic data in a throwaway database."""
import pytest

import rag_helpers as h
from rag_helpers import D1, M1, M2, T1, T2, World, standard_world
from rag.nearest import nearest_existing, nearest_existing_detailed

HOSTILE = "1; DROP TABLE paper; --"


@pytest.fixture
def world(conn):
    return standard_world(conn)


@pytest.fixture
def pair(world):
    return ("method", world.eid("method", M1)), ("task", world.eid("task", T1))


# Hand-worked facts for the standard world, A = Method One, B = Task One, cutoff 2024:
#   exact (A and B in one experiment): P05 (2019), P06 (2020)  -> year DESC: P06, P05
#   P07 has A and B in different experiments: neither exact nor "A only" nor "B only"
#   P10 has no year, P08 has no task: both outside the universe

def test_exact_only_when_the_limit_is_covered(conn, world, pair):
    assert nearest_existing(conn, *pair, 2024, limit=2) == ["P06", "P05"]
    assert nearest_existing(conn, *pair, 2024, limit=1) == ["P06"]


def test_exact_results_come_first_ordered_by_year_desc_then_id(conn):
    w = World(conn)
    for i, year in enumerate((2019, 2021, 2021, 2018)):
        w.paper(f"E{i}", year, [(M1, D1, T1)])
    a, b = ("method", w.eid("method", M1)), ("task", w.eid("task", T1))
    assert nearest_existing(conn, a, b, 2030, limit=10) == ["E1", "E2", "E0", "E3"]   # 2021 (E1, E2), 2019, 2018


def test_exact_plus_close_matches_brute_force(conn, world, pair):
    got = nearest_existing_detailed(conn, *pair, 2024, limit=5)
    expected = h.nearest(world, pair[0], pair[1], 2024, 5)
    assert [r["paper_id"] for r in got] == [pid for pid, _, _ in expected]
    assert [r["tier"] for r in got] == [t for _, t, _ in expected]
    assert [r["tier"] for r in got][:2] == ["exact", "exact"] and all(r["tier"] == "close" for r in got[2:])
    assert len(got) == 5
    for r, (_, _, sim) in zip(got, expected):
        if sim is None:
            assert r["similarity"] is None
        else:
            assert r["similarity"] == pytest.approx(sim, abs=1e-4)


def test_close_only_when_no_experiment_has_both(conn):
    w = World(conn)
    w.paper("A1", 2019, [("Mx", D1, "Other task")])
    w.paper("A2", 2020, [("Mx", D1, "Other task")])
    w.paper("A3", 2021, [("Mx", D1, "Other task")])
    w.paper("B1", 2018, [("Other method", D1, "Ty")])
    w.paper("B2", 2022, [("Other method", D1, "Ty")])
    a, b = ("method", w.eid("method", "Mx")), ("task", w.eid("task", "Ty"))
    got = nearest_existing_detailed(conn, a, b, 2030, limit=4)
    expected = h.nearest(w, a, b, 2030, 4)
    assert [r["paper_id"] for r in got] == [pid for pid, _, _ in expected]
    assert {r["tier"] for r in got} == {"close"} and all(isinstance(r["similarity"], float) for r in got)
    sims = [r["similarity"] for r in got]
    assert sims == sorted(sims, reverse=True)                    # merged by similarity, best first
    assert {r["uses"] for r in got} == {"a", "b"}                # candidates from both sides are merged


def test_limit_caps_the_total_including_the_close_tier(conn, world, pair):
    for limit in (1, 2, 3, 4, 5, 8):
        got = nearest_existing(conn, *pair, 2024, limit=limit)
        assert len(got) == min(limit, 2 + 6)                      # 2 exact + 6 close candidates with embeddings
        assert got == [pid for pid, _, _ in h.nearest(world, pair[0], pair[1], 2024, limit)]
        assert len(set(got)) == len(got)                          # no duplicates


def test_cutoff_year_excludes_later_papers_and_papers_without_a_year(conn, world, pair):
    # cutoff 2019: P06 (2020) is out, P10 (no year, A and B together) never counts
    assert nearest_existing(conn, *pair, 2019, limit=1) == ["P05"]
    assert "P06" not in nearest_existing(conn, *pair, 2019, limit=20)
    for cutoff in (2024, 2022, 2020, 2019, 2016, 2014):
        got = nearest_existing(conn, *pair, cutoff, limit=20)
        assert "P10" not in got
        assert all(world.papers[pid]["year"] <= cutoff for pid in got)
        assert got == [pid for pid, _, _ in h.nearest(world, pair[0], pair[1], cutoff, 20)]


def test_papers_without_embeddings_are_skipped_in_the_close_tier(conn, world, pair):
    # P12 uses A (Method One, with a task) but has no embedding: never returned as a close paper
    assert "P12" not in nearest_existing(conn, *pair, 2024, limit=20)


def test_a_paper_without_an_embedding_still_counts_as_an_exact_paper(conn):
    w = World(conn)
    w.paper("N1", 2020, [(M1, D1, T1)], embedded=False)
    a, b = ("method", w.eid("method", M1)), ("task", w.eid("task", T1))
    assert nearest_existing(conn, a, b, 2030, limit=3) == ["N1"]


def test_papers_that_use_both_elements_in_different_experiments_are_in_no_tier(conn, world, pair):
    assert "P07" not in nearest_existing(conn, *pair, 2024, limit=20)


def test_unknown_element_ids_give_an_empty_list(conn, world, pair):
    assert nearest_existing(conn, ("method", 987654), ("task", 987655), 2024) == []
    assert nearest_existing(conn, ("method", 987654), pair[1], 2024) == []     # only B exists: nothing to compare with
    assert nearest_existing(conn, pair[0], ("task", 987655), 2024) == []


def test_empty_database_gives_an_empty_list(conn):
    assert nearest_existing(conn, ("method", 1), ("task", 1), 2024) == []


def test_swapping_a_and_b_gives_the_same_papers(conn, world, pair):
    assert nearest_existing(conn, *pair, 2024, limit=6) == nearest_existing(conn, pair[1], pair[0], 2024, limit=6)


def test_results_are_deterministic(conn, world, pair):
    first = nearest_existing_detailed(conn, *pair, 2024, limit=6)
    assert first == nearest_existing_detailed(conn, *pair, 2024, limit=6)


def test_detailed_fields(conn, world, pair):
    got = nearest_existing_detailed(conn, *pair, 2024, limit=3)
    assert set(got[0]) == {"paper_id", "title", "year", "tier", "similarity", "uses"}
    assert got[0] == {"paper_id": "P06", "title": "Title P06", "year": 2020, "tier": "exact",
                      "similarity": None, "uses": "both"}
    assert got[2]["tier"] == "close" and got[2]["uses"] in ("a", "b")
    assert nearest_existing(conn, *pair, 2024, limit=3) == [r["paper_id"] for r in got]


@pytest.mark.parametrize("a_kind, a_name, b_kind, b_name", [
    ("method", M1, "dataset", D1), ("dataset", D1, "task", T1), ("task", T2, "method", M2), ("dataset", D1, "method", M1)])
def test_other_kind_pairs_match_brute_force(conn, world, a_kind, a_name, b_kind, b_name):
    a, b = (a_kind, world.eid(a_kind, a_name)), (b_kind, world.eid(b_kind, b_name))
    for cutoff in (2024, 2020):
        for limit in (2, 7):
            assert nearest_existing(conn, a, b, cutoff, limit) == \
                [pid for pid, _, _ in h.nearest(world, a, b, cutoff, limit)]


def test_matches_brute_force_over_a_grid(conn, world):
    elements = [("method", world.eid("method", M1)), ("method", world.eid("method", M2)),
                ("task", world.eid("task", T1)), ("task", world.eid("task", T2)),
                ("dataset", world.eid("dataset", D1))]
    for a in elements:
        for b in elements:
            if a[0] == b[0]:
                continue
            for cutoff in (2024, 2021, 2018):
                for limit in (1, 3, 9):
                    got = nearest_existing(conn, a, b, cutoff, limit)
                    assert got == [pid for pid, _, _ in h.nearest(world, a, b, cutoff, limit)], (a, b, cutoff, limit)


# --- validation ---------------------------------------------------------------------------------

def test_kind_validation(conn, world, pair):
    with pytest.raises(ValueError):
        nearest_existing(conn, ("method", 1), ("method", 2), 2024)
    with pytest.raises(ValueError):
        nearest_existing(conn, ("setting", 1), pair[1], 2024)


def test_a_hostile_string_in_an_id_is_rejected_before_any_sql(conn, world, pair):
    before = conn.execute("SELECT count(*) FROM paper").fetchone()[0]
    with pytest.raises(ValueError, match="int"):
        nearest_existing(conn, ("method", HOSTILE), pair[1], 2024)
    with pytest.raises(ValueError):
        nearest_existing(conn, ("method; DROP TABLE paper", 1), pair[1], 2024)
    assert conn.execute("SELECT count(*) FROM paper").fetchone()[0] == before


@pytest.mark.parametrize("kwargs", [{"cutoff_year": "2024"}, {"cutoff_year": None}, {"limit": 0}, {"limit": -3},
                                    {"limit": "5"}])
def test_cutoff_and_limit_validation(conn, world, pair, kwargs):
    args = {"cutoff_year": 2024, "limit": 5, **kwargs}
    with pytest.raises(ValueError):
        nearest_existing(conn, *pair, args["cutoff_year"], args["limit"])
