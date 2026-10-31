"""Tests for the SQL search layer (db/retrieval). All papers and vectors are synthetic, in throwaway
databases. No model is used; real embeddings do not exist yet."""
import json
import math
import random
from types import SimpleNamespace

import psycopg
import pytest

from retrieval import cli, search as search_module
from retrieval.search import keyword_search, search

DIM = 768
HOSTILE = "x'; DROP TABLE paper; --"


def make_vector(rng):
    return [round(rng.gauss(0, 1), 6) for _ in range(DIM)]


def literal(vector):
    return "[" + ",".join(repr(x) for x in vector) + "]"


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# --- a small synthetic corpus with known structure ---------------------------------------------

@pytest.fixture
def corpus(conn):
    rng = random.Random(7)
    venue_ids = {}
    for name, kind in (("Venue A", "conference"), ("Venue B", "journal")):
        venue_ids[name] = conn.execute("INSERT INTO venue (name, type) VALUES (%s, %s) RETURNING venue_id",
                                       (name, kind)).fetchone()[0]

    def vocab(table, column, name):
        return conn.execute(f"INSERT INTO {table} ({column}) VALUES (%s) RETURNING {table}_id", (name,)).fetchone()[0]

    ids = {"M1": vocab("method", "canonical_name", "Method One"), "M2": vocab("method", "canonical_name", "Method Two"),
           "D1": vocab("dataset", "canonical_name", "Dataset One"), "T1": vocab("task", "canonical_name", "Task One")}
    conn.execute("INSERT INTO method_alias (alias, method_id) VALUES ('m-one', %s)", (ids["M1"],))
    names = {"M1": "Method One", "M2": "Method Two", "D1": "Dataset One", "T1": "Task One"}

    meta = {}

    def add_paper(i, with_vector):
        pid = f"S_{i:02d}"
        year = 2015 + i % 10 if i < 40 else 2020
        venue = None if (i < 40 and i % 7 == 0) else ("Venue A" if i % 2 == 0 else "Venue B")
        vector = make_vector(rng) if with_vector else None
        conn.execute(
            "INSERT INTO paper (paper_id, title, abstract, year, venue_id, embedding) VALUES (%s, %s, %s, %s, %s, %s)",
            (pid, f"Synthetic paper {i}", f"Synthetic abstract {i}", year, venue_ids.get(venue),
             literal(vector) if vector else None))
        experiments = {0: [("M1", "D1", "T1")], 1: [("M2", "D1", None)], 2: [("M1", None, "T1")], 3: []}[i % 4]
        if i == 3:  # no single experiment has M2 and T1, but the paper has both across two experiments
            experiments = [("M2", "D1", None), ("M1", None, "T1")]
        if i >= 40:
            experiments = [("M1", "D1", "T1")]
        for m, d, t in experiments:
            conn.execute("INSERT INTO experiment (paper_id, method_id, dataset_id, task_id) VALUES (%s, %s, %s, %s)",
                         (pid, ids[m], ids.get(d), ids.get(t)))
        meta[pid] = {"year": year, "venue": venue, "vec": vector,
                     "experiments": [(names[m], names.get(d), names.get(t)) for m, d, t in experiments],
                     "methods": {names[m] for m, _, _ in experiments},
                     "datasets": {names[d] for _, d, _ in experiments if d},
                     "tasks": {names[t] for _, _, t in experiments if t}}

    for i in range(40):
        add_paper(i, True)
    for i in range(40, 45):
        add_paper(i, False)   # no embedding: must never be returned by vector search
    return SimpleNamespace(meta=meta, query=make_vector(random.Random(99)))


def brute(corpus, predicate=lambda m: True):
    ranked = sorted(((cosine(corpus.query, m["vec"]), pid) for pid, m in corpus.meta.items()
                     if m["vec"] is not None and predicate(m)), reverse=True)
    return [pid for _, pid in ranked], {pid: sim for sim, pid in ranked}


def ids_of(results):
    return [r["paper_id"] for r in results]


def same_experiment(m, methods=None, datasets=None, tasks=None):
    """True if ONE experiment of the paper satisfies every supplied filter (values within a filter are OR)."""
    return any((methods is None or e[0] in methods) and (datasets is None or e[1] in datasets)
               and (tasks is None or e[2] in tasks) for e in m["experiments"])


def any_experiment(m, methods=None, datasets=None, tasks=None):
    """True if each supplied filter is satisfied by SOME experiment (possibly different ones)."""
    return all(values is None or any(e[index] in values for e in m["experiments"])
               for index, values in enumerate((methods, datasets, tasks)))


# --- ordering, basic output -------------------------------------------------------------------

def test_order_and_similarity_match_a_brute_force_cosine_ranking(conn, corpus):
    expected, sims = brute(corpus)
    results = search(conn, corpus.query, top_k=10)
    assert ids_of(results) == expected[:10]
    for r in results:
        assert r["similarity"] == pytest.approx(sims[r["paper_id"]], abs=1e-5)
    assert [r["similarity"] for r in results] == sorted((r["similarity"] for r in results), reverse=True)


def test_result_dicts_have_exactly_the_documented_keys(conn, corpus):
    r = search(conn, corpus.query, top_k=1)[0]
    assert set(r) == {"paper_id", "title", "year", "venue", "similarity"}
    assert r["title"].startswith("Synthetic paper") and isinstance(r["similarity"], float)


def test_papers_without_embeddings_are_excluded(conn, corpus):
    results = search(conn, corpus.query, top_k=100)
    assert len(results) == 40
    assert not {f"S_{i}" for i in range(40, 45)} & set(ids_of(results))


def test_top_k_and_offset(conn, corpus):
    expected, _ = brute(corpus)
    assert ids_of(search(conn, corpus.query, top_k=5)) == expected[:5]
    assert ids_of(search(conn, corpus.query, top_k=5, offset=5)) == expected[5:10]
    assert ids_of(search(conn, corpus.query, top_k=10, offset=35)) == expected[35:40]
    assert search(conn, corpus.query, top_k=10, offset=40) == []


# --- filters ----------------------------------------------------------------------------------

def check_filter(conn, corpus, predicate, **filters):
    expected, _ = brute(corpus, predicate)
    assert expected, "the test filter must match something"
    got = ids_of(search(conn, corpus.query, top_k=100, **filters))
    assert got == expected


def test_year_filters(conn, corpus):
    check_filter(conn, corpus, lambda m: m["year"] >= 2020, year_min=2020)
    check_filter(conn, corpus, lambda m: m["year"] <= 2017, year_max=2017)
    check_filter(conn, corpus, lambda m: 2017 <= m["year"] <= 2019, year_min=2017, year_max=2019)


def test_venue_filter_is_case_and_space_insensitive_and_multiple_values_mean_or(conn, corpus):
    check_filter(conn, corpus, lambda m: m["venue"] == "Venue A", venues=["Venue A"])
    check_filter(conn, corpus, lambda m: m["venue"] == "Venue A", venues=["  venue   a "])
    check_filter(conn, corpus, lambda m: m["venue"] in ("Venue A", "Venue B"), venues=["Venue A", "venue b"])
    assert search(conn, corpus.query, top_k=100, venues=["No Such Venue"]) == []


def test_method_dataset_task_filters_resolve_aliases(conn, corpus):
    check_filter(conn, corpus, lambda m: "Method One" in m["methods"], methods=["Method One"])
    check_filter(conn, corpus, lambda m: "Method One" in m["methods"], methods=["m-one"])      # alias
    check_filter(conn, corpus, lambda m: "Method One" in m["methods"], methods=["  M-ONE "])   # alias, other case
    check_filter(conn, corpus, lambda m: "Dataset One" in m["datasets"], datasets=["dataset one"])
    check_filter(conn, corpus, lambda m: "Task One" in m["tasks"], tasks=["Task One"])


def test_several_values_in_one_filter_mean_or(conn, corpus):
    check_filter(conn, corpus, lambda m: bool(m["methods"] & {"Method One", "Method Two"}),
                 methods=["Method One", "Method Two"])


def test_different_filters_combine_with_and(conn, corpus):
    check_filter(conn, corpus,
                 lambda m: "Method One" in m["methods"] and m["year"] >= 2020 and m["venue"] == "Venue A",
                 methods=["Method One"], year_min=2020, venues=["Venue A"])
    check_filter(conn, corpus, lambda m: same_experiment(m, datasets={"Dataset One"}, tasks={"Task One"}),
                 datasets=["Dataset One"], tasks=["Task One"])
    check_filter(conn, corpus, lambda m: any_experiment(m, datasets={"Dataset One"}, tasks={"Task One"}),
                 datasets=["Dataset One"], tasks=["Task One"], match="any")


# --- match="same_experiment" (default) versus match="any" -------------------------------------
# S_03 has two experiments: (Method Two, Dataset One, -) and (Method One, -, Task One).

def test_same_experiment_is_the_default_and_needs_one_experiment_to_satisfy_all_filters(conn, corpus):
    """Method Two AND Task One: S_03 has each, but in different experiments."""
    default = ids_of(search(conn, corpus.query, top_k=100, methods=["Method Two"], tasks=["Task One"]))
    explicit = ids_of(search(conn, corpus.query, top_k=100, methods=["Method Two"], tasks=["Task One"],
                             match="same_experiment"))
    any_mode = ids_of(search(conn, corpus.query, top_k=100, methods=["Method Two"], tasks=["Task One"], match="any"))
    assert default == explicit == []
    assert any_mode == ["S_03"]
    assert brute(corpus, lambda m: same_experiment(m, {"Method Two"}, None, {"Task One"}))[0] == []
    assert brute(corpus, lambda m: any_experiment(m, {"Method Two"}, None, {"Task One"}))[0] == ["S_03"]


def test_both_modes_accept_a_paper_whose_single_experiment_has_everything(conn, corpus):
    for mode in ("same_experiment", "any"):
        got = ids_of(search(conn, corpus.query, top_k=100, methods=["Method One"], tasks=["Task One"], match=mode))
        assert "S_03" in got                         # its second experiment is (Method One, -, Task One)
        assert "S_00" in got and "S_02" in got       # i % 4 == 0 and 2


def test_three_filters_must_meet_in_one_experiment_by_default(conn, corpus):
    kwargs = dict(methods=["Method One"], datasets=["Dataset One"], tasks=["Task One"])
    default = ids_of(search(conn, corpus.query, top_k=100, **kwargs))
    any_mode = ids_of(search(conn, corpus.query, top_k=100, match="any", **kwargs))
    assert default == brute(corpus, lambda m: same_experiment(m, {"Method One"}, {"Dataset One"}, {"Task One"}))[0]
    assert any_mode == brute(corpus, lambda m: any_experiment(m, {"Method One"}, {"Dataset One"}, {"Task One"}))[0]
    assert "S_03" not in default and "S_03" in any_mode
    assert set(default) < set(any_mode)


def test_values_within_a_filter_stay_or_in_same_experiment_mode(conn, corpus):
    check_filter(conn, corpus,
                 lambda m: same_experiment(m, {"Method One", "Method Two"}, None, {"Task One"}),
                 methods=["Method One", "m-one", "Method Two"], tasks=["Task One"])


def test_a_single_entity_filter_is_the_same_in_both_modes(conn, corpus):
    for kwargs in ({"methods": ["Method Two"]}, {"datasets": ["Dataset One"]}, {"tasks": ["Task One"]}):
        assert ids_of(search(conn, corpus.query, top_k=100, **kwargs)) == \
            ids_of(search(conn, corpus.query, top_k=100, match="any", **kwargs))


def test_exclude_ids(conn, corpus):
    expected, _ = brute(corpus)
    results = search(conn, corpus.query, top_k=5, exclude_ids=expected[:2])
    assert ids_of(results) == expected[2:7]


# --- include_entities -------------------------------------------------------------------------

def test_include_entities_lists_distinct_sorted_names(conn, corpus):
    by_id = {r["paper_id"]: r for r in search(conn, corpus.query, top_k=100, include_entities=True)}
    assert by_id["S_03"]["methods"] == ["Method One", "Method Two"]
    assert by_id["S_03"]["datasets"] == ["Dataset One"] and by_id["S_03"]["tasks"] == ["Task One"]
    assert by_id["S_00"]["methods"] == ["Method One"]
    assert by_id["S_11"]["methods"] == [] and by_id["S_11"]["datasets"] == [] and by_id["S_11"]["tasks"] == []
    assert "methods" not in search(conn, corpus.query, top_k=1)[0]


# --- input validation and SQL safety ----------------------------------------------------------

@pytest.mark.parametrize("bad, text", [
    ([0.1] * 384, "768"),
    ([0.1] * 767 + [float("nan")], "finite"),
    ([0.1] * 767 + [float("inf")], "finite"),
    ([0.0] * 768, "zero"),
    (["a"] * 768, "numbers"),
    ("not a vector", "768"),
])
def test_bad_query_vectors_are_rejected_before_any_query(conn, corpus, bad, text):
    with pytest.raises(ValueError, match=text):
        search(conn, bad, top_k=3)


@pytest.mark.parametrize("kwargs", [
    {"top_k": 0}, {"top_k": -1}, {"top_k": "10"}, {"offset": -1}, {"ef_search": 0}, {"ef_search": 1001},
    {"iterative_scan": "sometimes"}, {"year_min": "2020"}, {"venues": "Venue A"}, {"methods": "Method One"},
    {"exclude_ids": "S_01"}, {"match": "all"}, {"match": None},
])
def test_bad_parameters_are_rejected(conn, corpus, kwargs):
    with pytest.raises(ValueError):
        search(conn, corpus.query, **kwargs)


def test_hostile_strings_are_only_ever_data(conn, corpus):
    before = conn.execute("SELECT count(*) FROM paper").fetchone()[0]
    assert search(conn, corpus.query, venues=[HOSTILE]) == []
    assert search(conn, corpus.query, methods=[HOSTILE]) == []
    assert search(conn, corpus.query, datasets=[HOSTILE]) == []
    assert search(conn, corpus.query, tasks=[HOSTILE]) == []
    assert len(search(conn, corpus.query, top_k=100, exclude_ids=[HOSTILE])) == 40
    assert keyword_search(conn, HOSTILE) == []
    assert keyword_search(conn, "synthetic", venues=[HOSTILE]) == []
    assert conn.execute("SELECT count(*) FROM paper").fetchone()[0] == before


def test_hnsw_settings_do_not_leak_out_of_the_call(conn, corpus):
    search(conn, corpus.query, top_k=3, ef_search=77)
    assert conn.execute("SHOW hnsw.ef_search").fetchone()[0] == "40"
    assert conn.execute("SHOW hnsw.iterative_scan").fetchone()[0] == "off"


# --- HNSW with a selective filter: iterative scan ---------------------------------------------

def test_selective_filter_needs_iterative_scan(private_db, capsys):
    """2,000 synthetic vectors, a filter matching 1% of them, and only the HNSW index available.
    Prints what happens with iterative scan OFF and ON."""
    conn = private_db
    rng = random.Random(3)
    # only the HNSW index may serve the vector ordering: drop the b-tree indexes, rebuild HNSW after the load
    for index in ("idx_paper_year", "idx_paper_venue", "idx_paper_embedding_hnsw"):
        conn.execute(f"DROP INDEX {index}")
    with conn.cursor().copy("COPY paper (paper_id, title, year, embedding) FROM STDIN") as copy:
        for i in range(2000):
            copy.write_row((f"B_{i:04d}", f"Synthetic {i}", 2030 if i % 100 == 0 else 2020, literal(make_vector(rng))))
    conn.execute("CREATE INDEX idx_paper_embedding_hnsw ON paper USING hnsw (embedding vector_cosine_ops)")
    conn.execute("ANALYZE paper")
    matching = conn.execute("SELECT count(*) FROM paper WHERE year >= 2030").fetchone()[0]
    assert matching == 20

    conn.execute("SET enable_seqscan = off")   # make the planner use the HNSW index, as it would on a big table
    query = make_vector(random.Random(5))
    sql = "EXPLAIN SELECT paper_id FROM paper WHERE year >= 2030 ORDER BY embedding <=> %s::vector LIMIT 10"
    plan = "\n".join(r[0] for r in conn.execute(sql, (literal(query),)))
    assert "idx_paper_embedding_hnsw" in plan, plan

    top_k = 10
    off = search(conn, query, top_k=top_k, year_min=2030, ef_search=40, iterative_scan="off")
    strict = search(conn, query, top_k=top_k, year_min=2030, ef_search=40, iterative_scan="strict_order")
    relaxed = search(conn, query, top_k=top_k, year_min=2030, ef_search=40, iterative_scan="relaxed_order")
    default = search(conn, query, top_k=top_k, year_min=2030)
    wide = search(conn, query, top_k=50, year_min=2030)
    with capsys.disabled():
        print(f"\n[iterative scan, 2000 vectors, {matching} matching, top_k={top_k}, ef_search=40] "
              f"OFF returned {len(off)}, strict_order returned {len(strict)}, relaxed_order returned {len(relaxed)}; "
              f"search() default returned {len(default)}; top_k=50 returned {len(wide)} (only {matching} match)")
    assert len(off) < top_k, "without iterative scan the post-filter starves the result"
    assert len(strict) == min(top_k, matching)
    assert len(default) == min(top_k, matching)
    assert len(wide) == min(50, matching)
    # strict_order returns results in distance order; HNSW is approximate, so report overlap with the exact top 10
    assert [r["similarity"] for r in strict] == sorted((r["similarity"] for r in strict), reverse=True)
    conn.execute("SET enable_seqscan = on")
    conn.execute("SET enable_indexscan = off")
    exact = [r[0] for r in conn.execute(
        "SELECT paper_id FROM paper WHERE year >= 2030 ORDER BY embedding <=> %s::vector LIMIT 10", (literal(query),))]
    overlap = len(set(ids_of(strict)) & set(exact))
    with capsys.disabled():
        print(f"[strict_order result overlaps the exact top {top_k} in {overlap} of {top_k} papers]")
    assert overlap >= top_k // 2


# --- keyword baseline -------------------------------------------------------------------------

@pytest.fixture
def docs(conn):
    rows = [
        ("K_1", "Neural machine translation", "We study translation with neural models.", 2020),
        ("K_2", "A study of image segmentation", "We discuss neural translation of medical images.", 2021),
        ("K_3", "Protein folding", "Nothing about the other topics here.", 2019),
        ("K_4", "Translations of poems", None, 2022),
    ]
    for pid, title, abstract, year in rows:
        conn.execute("INSERT INTO paper (paper_id, title, abstract, year) VALUES (%s, %s, %s, %s)",
                     (pid, title, abstract, year))
    return conn


def test_keyword_search_finds_and_ranks_by_text(docs):
    results = keyword_search(docs, "neural translation")
    assert ids_of(results)[0] == "K_1"                     # in the title and the abstract
    assert set(ids_of(results)) == {"K_1", "K_2"}
    assert set(results[0]) == {"paper_id", "title", "year", "venue", "score"}
    assert results[0]["score"] > results[1]["score"] > 0


def test_keyword_search_stems_and_handles_missing_abstracts(docs):
    assert "K_4" in ids_of(keyword_search(docs, "translation"))   # title-only paper, plural in the title


def test_keyword_search_does_not_need_embeddings_and_applies_filters(docs):
    assert set(ids_of(keyword_search(docs, "translation", year_min=2021))) == {"K_2", "K_4"}
    assert ids_of(keyword_search(docs, "translation", year_max=2020)) == ["K_1"]
    assert keyword_search(docs, "translation", top_k=1, offset=1) != keyword_search(docs, "translation", top_k=1)


def test_keyword_search_blank_or_stopword_queries_return_nothing(docs):
    assert keyword_search(docs, "") == [] and keyword_search(docs, "   ") == []
    assert keyword_search(docs, "the of and") == []


def test_keyword_search_validates_arguments(docs):
    with pytest.raises(ValueError):
        keyword_search(docs, 123)
    with pytest.raises(ValueError):
        keyword_search(docs, "translation", top_k=0)
    with pytest.raises(ValueError):
        keyword_search(docs, "translation", match="all")


def test_keyword_search_match_modes(conn):
    ids = {}
    for table, column, names in (("method", "canonical_name", ["Method X"]), ("dataset", "canonical_name", ["Dataset Y"]),
                                 ("task", "canonical_name", ["Task W"])):
        for name in names:
            ids[name] = conn.execute(f"INSERT INTO {table} ({column}) VALUES (%s) RETURNING {table}_id",
                                     (name,)).fetchone()[0]
    method_z = conn.execute("INSERT INTO method (canonical_name) VALUES ('Method Z') RETURNING method_id").fetchone()[0]
    for pid in ("W_SPLIT", "W_SINGLE"):
        conn.execute("INSERT INTO paper (paper_id, title, abstract) VALUES (%s, 'Alpha study', 'about alpha')", (pid,))
    # W_SPLIT: Method X in one experiment, Task W in another. W_SINGLE: both in one experiment.
    conn.execute("INSERT INTO experiment (paper_id, method_id, dataset_id) VALUES ('W_SPLIT', %s, %s)",
                 (ids["Method X"], ids["Dataset Y"]))
    conn.execute("INSERT INTO experiment (paper_id, method_id, task_id) VALUES ('W_SPLIT', %s, %s)",
                 (method_z, ids["Task W"]))
    conn.execute("INSERT INTO experiment (paper_id, method_id, task_id) VALUES ('W_SINGLE', %s, %s)",
                 (ids["Method X"], ids["Task W"]))
    kwargs = dict(methods=["Method X"], tasks=["Task W"])
    assert ids_of(keyword_search(conn, "alpha", **kwargs)) == ["W_SINGLE"]                       # default
    assert ids_of(keyword_search(conn, "alpha", match="same_experiment", **kwargs)) == ["W_SINGLE"]
    assert set(ids_of(keyword_search(conn, "alpha", match="any", **kwargs))) == {"W_SPLIT", "W_SINGLE"}


# --- command line (testing aid only) ----------------------------------------------------------

@pytest.fixture
def connect_to_test_db(test_db_conninfo):
    return lambda dbname: psycopg.connect(test_db_conninfo, autocommit=True)


def test_cli_search_from_a_json_vector_file(connect_to_test_db, conn, corpus, tmp_path, capsys):
    vector_file = tmp_path / "q.json"
    vector_file.write_text(json.dumps(corpus.query), encoding="utf-8")
    code = cli.main(["search", "--vector-file", str(vector_file), "--top-k", "3", "--year-min", "2020",
                     "--method", "m-one", "--entities"], connect_fn=connect_to_test_db)
    out = capsys.readouterr().out
    expected = brute(corpus, lambda m: m["year"] >= 2020 and "Method One" in m["methods"])[0][:3]
    assert code == 0
    positions = [out.index(pid) for pid in expected]
    assert positions == sorted(positions)
    assert "Method One" in out


def test_cli_match_option(connect_to_test_db, conn, corpus, tmp_path, capsys):
    vector_file = tmp_path / "q.json"
    vector_file.write_text(json.dumps(corpus.query), encoding="utf-8")
    args = ["search", "--vector-file", str(vector_file), "--method", "Method Two", "--task", "Task One"]
    assert cli.main(args, connect_fn=connect_to_test_db) == 0
    assert "(no results)" in capsys.readouterr().out                 # default: same experiment
    assert cli.main(args + ["--match", "any"], connect_fn=connect_to_test_db) == 0
    assert "S_03" in capsys.readouterr().out


def test_cli_search_from_an_npy_file(connect_to_test_db, conn, corpus, tmp_path, capsys):
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "q.npy"
    numpy.save(path, numpy.array([corpus.query], dtype="float32"))
    assert cli.main(["search", "--vector-file", str(path), "--top-k", "2"], connect_fn=connect_to_test_db) == 0
    assert brute(corpus)[0][0] in capsys.readouterr().out


def test_cli_rejects_a_wrong_sized_vector_file(connect_to_test_db, tmp_path, capsys):
    path = tmp_path / "q.json"
    path.write_text(json.dumps([0.1] * 10), encoding="utf-8")
    assert cli.main(["search", "--vector-file", str(path)], connect_fn=connect_to_test_db) == 1
    assert "768" in capsys.readouterr().err


def test_cli_keyword(connect_to_test_db, docs, capsys):
    assert cli.main(["keyword", "neural translation"], connect_fn=connect_to_test_db) == 0
    assert "K_1" in capsys.readouterr().out
