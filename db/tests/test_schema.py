"""Schema tests. All data here is made up for the test and lives only in a throwaway database."""
import psycopg
import pytest

MATVIEWS = [
    "mv_method_count", "mv_dataset_count", "mv_task_count",
    "mv_method_dataset", "mv_method_task", "mv_dataset_task",
    "mv_method_count_md", "mv_method_count_mt", "mv_dataset_count_dt", "mv_task_count_dt",
    "mv_universe_size", "mv_method_dataset_task",
]


def add_named(conn, table, column, names):
    """Insert vocabulary rows and return {name: id}."""
    ids = {}
    for name in names:
        ids[name] = conn.execute(
            f"INSERT INTO {table} ({column}) VALUES (%s) RETURNING {table}_id", (name,)
        ).fetchone()[0]
    return ids


# --- 1. experiment uniqueness with NULLs -------------------------------------------------------

def test_experiment_unique_rejects_duplicate_with_null_dataset_and_task(conn):
    conn.execute("INSERT INTO paper (paper_id, title) VALUES ('T_P1', 'test paper')")
    m = add_named(conn, "method", "canonical_name", ["M1", "M2"])["M1"]
    insert = ("INSERT INTO experiment (paper_id, method_id, dataset_id, task_id, setting_id) "
              "VALUES ('T_P1', %s, NULL, NULL, NULL)")
    conn.execute(insert, (m,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (m,))


def test_experiment_unique_allows_rows_that_differ(conn):
    conn.execute("INSERT INTO paper (paper_id, title) VALUES ('T_P1', 'test paper')")
    methods = add_named(conn, "method", "canonical_name", ["M1", "M2"])
    d1 = add_named(conn, "dataset", "canonical_name", ["D1"])["D1"]
    insert = ("INSERT INTO experiment (paper_id, method_id, dataset_id, task_id) "
              "VALUES ('T_P1', %s, %s, NULL)")
    conn.execute(insert, (methods["M1"], None))
    conn.execute(insert, (methods["M1"], d1))      # same method, dataset now set: allowed
    conn.execute(insert, (methods["M2"], None))    # other method: allowed
    n = conn.execute("SELECT count(*) FROM experiment").fetchone()[0]
    assert n == 3


def test_experiment_unique_rejects_duplicate_with_dataset_set_and_task_null(conn):
    conn.execute("INSERT INTO paper (paper_id, title) VALUES ('T_P1', 'test paper')")
    m = add_named(conn, "method", "canonical_name", ["M1"])["M1"]
    d = add_named(conn, "dataset", "canonical_name", ["D1"])["D1"]
    insert = ("INSERT INTO experiment (paper_id, method_id, dataset_id, task_id) "
              "VALUES ('T_P1', %s, %s, NULL)")
    conn.execute(insert, (m, d))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (m, d))


# --- 2. same-universe view counts on a hand-computed dataset -----------------------------------
#
# Experiments (paper, method, dataset, task):
#   e1: P1 M1 D1 T1
#   e2: P1 M1 D2 T1     (P1 has two experiments with the same method: counted once per paper)
#   e3: P2 M1 D1 -
#   e4: P2 M2 -  T2
#   e5: P3 M2 D1 T1
#   e6: P4 M1 -  -
EXPERIMENTS = [
    ("P1", "M1", "D1", "T1"),
    ("P1", "M1", "D2", "T1"),
    ("P2", "M1", "D1", None),
    ("P2", "M2", None, "T2"),
    ("P3", "M2", "D1", "T1"),
    ("P4", "M1", None, None),
]

# Counts worked out by hand from the table above (distinct papers).
EXPECTED = {
    "mv_method_count":     {("M1",): 3, ("M2",): 2},                 # M1: P1,P2,P4  M2: P2,P3
    "mv_dataset_count":    {("D1",): 3, ("D2",): 1},                 # D1: P1,P2,P3  D2: P1
    "mv_task_count":       {("T1",): 2, ("T2",): 1},                 # T1: P1,P3     T2: P2
    "mv_method_dataset":   {("M1", "D1"): 2, ("M1", "D2"): 1, ("M2", "D1"): 1},
    "mv_method_task":      {("M1", "T1"): 1, ("M2", "T2"): 1, ("M2", "T1"): 1},
    "mv_dataset_task":     {("D1", "T1"): 2, ("D2", "T1"): 1},
    "mv_method_count_md":  {("M1",): 2, ("M2",): 1},                 # only papers with a dataset
    "mv_method_count_mt":  {("M1",): 1, ("M2",): 2},                 # only papers with a task
    "mv_dataset_count_dt": {("D1",): 2, ("D2",): 1},                 # only papers with both
    "mv_task_count_dt":    {("T1",): 2},
    "mv_universe_size":    {("method_dataset",): 3, ("method_task",): 3, ("dataset_task",): 2},
    "mv_method_dataset_task": {("M1", "D1", "T1"): 1, ("M1", "D2", "T1"): 1, ("M2", "D1", "T1"): 1},
}

# Each view: its key columns, and the extra WHERE conditions that define its universe,
# used to build an independent raw-SQL count (see raw_count).
VIEW_KEYS = {
    "mv_method_count":     (["method_id"], []),
    "mv_dataset_count":    (["dataset_id"], ["dataset_id IS NOT NULL"]),
    "mv_task_count":       (["task_id"], ["task_id IS NOT NULL"]),
    "mv_method_dataset":   (["method_id", "dataset_id"], ["dataset_id IS NOT NULL"]),
    "mv_method_task":      (["method_id", "task_id"], ["task_id IS NOT NULL"]),
    "mv_dataset_task":     (["dataset_id", "task_id"], ["dataset_id IS NOT NULL", "task_id IS NOT NULL"]),
    "mv_method_count_md":  (["method_id"], ["dataset_id IS NOT NULL"]),
    "mv_method_count_mt":  (["method_id"], ["task_id IS NOT NULL"]),
    "mv_dataset_count_dt": (["dataset_id"], ["dataset_id IS NOT NULL", "task_id IS NOT NULL"]),
    "mv_task_count_dt":    (["task_id"], ["dataset_id IS NOT NULL", "task_id IS NOT NULL"]),
    "mv_method_dataset_task": (["method_id", "dataset_id", "task_id"],
                               ["dataset_id IS NOT NULL", "task_id IS NOT NULL"]),
}


@pytest.fixture
def counted(conn):
    """Load the hand-computed dataset, refresh the views, and return name lookups."""
    for p in ("P1", "P2", "P3", "P4"):
        conn.execute("INSERT INTO paper (paper_id, title) VALUES (%s, %s)", (p, "test " + p))
    m = add_named(conn, "method", "canonical_name", ["M1", "M2"])
    d = add_named(conn, "dataset", "canonical_name", ["D1", "D2"])
    t = add_named(conn, "task", "canonical_name", ["T1", "T2"])
    for paper, method, dataset, task in EXPERIMENTS:
        conn.execute(
            "INSERT INTO experiment (paper_id, method_id, dataset_id, task_id) VALUES (%s, %s, %s, %s)",
            (paper, m[method], d.get(dataset), t.get(task)),
        )
    for view in MATVIEWS:
        conn.execute(f"REFRESH MATERIALIZED VIEW {view}")
    names = {"method_id": {v: k for k, v in m.items()},
             "dataset_id": {v: k for k, v in d.items()},
             "task_id": {v: k for k, v in t.items()}}
    return conn, names


def view_rows(conn, view, key_cols, names):
    """Read a view into {(name, ...): n_papers}."""
    rows = conn.execute(f"SELECT {', '.join(key_cols)}, n_papers FROM {view}").fetchall()
    return {tuple(names[c][v] for c, v in zip(key_cols, row[:-1])): row[-1] for row in rows}


def raw_count(conn, key_cols, key_vals, conditions):
    """Count papers straight from the experiment rows, written differently from the views:
    count papers that have at least one matching experiment (EXISTS), not COUNT(DISTINCT)."""
    where = " AND ".join([f"e.{c} = %s" for c in key_cols] + conditions)
    sql = ("SELECT count(*) FROM paper p WHERE EXISTS "
           f"(SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id AND {where})")
    return conn.execute(sql, key_vals).fetchone()[0]


@pytest.mark.parametrize("view", sorted(VIEW_KEYS))
def test_view_counts_match_hand_computed_and_raw_sql(counted, view):
    conn, names = counted
    key_cols, conditions = VIEW_KEYS[view]
    from_view = view_rows(conn, view, key_cols, names)
    assert from_view == EXPECTED[view], "view disagrees with the hand-computed counts"

    # Independent check: every row (and the absence of other rows) against raw SQL on experiment.
    ids = {c: {name: i for i, name in names[c].items()} for c in names}
    for key, n in from_view.items():
        key_vals = [ids[c][k] for c, k in zip(key_cols, key)]
        assert raw_count(conn, key_cols, key_vals, conditions) == n, f"{view} {key}"


def test_universe_sizes_match_raw_sql(counted):
    conn, _ = counted
    raw = {
        "method_dataset": "SELECT count(*) FROM paper p WHERE EXISTS "
                          "(SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id AND e.dataset_id IS NOT NULL)",
        "method_task": "SELECT count(*) FROM paper p WHERE EXISTS "
                       "(SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id AND e.task_id IS NOT NULL)",
        "dataset_task": "SELECT count(*) FROM paper p WHERE EXISTS "
                        "(SELECT 1 FROM experiment e WHERE e.paper_id = p.paper_id "
                        "AND e.dataset_id IS NOT NULL AND e.task_id IS NOT NULL)",
    }
    from_view = dict(conn.execute("SELECT pair_type, n_papers FROM mv_universe_size").fetchall())
    assert from_view == {"method_dataset": 3, "method_task": 3, "dataset_task": 2}
    for pair_type, sql in raw.items():
        assert conn.execute(sql).fetchone()[0] == from_view[pair_type]


def test_subset_method_counts_differ_from_all_paper_count(counted):
    """M1 is in 3 papers overall, but only 2 of them name a dataset. The pair views must use 2."""
    conn, names = counted
    m1 = {n: i for i, n in names["method_id"].items()}["M1"]
    overall = conn.execute("SELECT n_papers FROM mv_method_count WHERE method_id = %s", (m1,)).fetchone()[0]
    in_md = conn.execute("SELECT n_papers FROM mv_method_count_md WHERE method_id = %s", (m1,)).fetchone()[0]
    assert (overall, in_md) == (3, 2)


# --- 3. REFRESH ... CONCURRENTLY on every view -------------------------------------------------

def test_there_are_twelve_materialized_views(conn):
    found = {r[0] for r in conn.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'")}
    assert found == set(MATVIEWS)


@pytest.mark.parametrize("view", MATVIEWS)
def test_refresh_concurrently_works_on_empty_views(conn, view):
    conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")


@pytest.mark.parametrize("view", MATVIEWS)
def test_refresh_concurrently_works_with_data(counted, view):
    conn, _ = counted
    before = conn.execute(f"SELECT count(*) FROM {view}").fetchone()[0]
    conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
    assert conn.execute(f"SELECT count(*) FROM {view}").fetchone()[0] == before > 0


# --- 4. hybrid query: year filter + vector similarity -------------------------------------------
# The vectors below are synthetic and exist only in the throwaway test database. They are not
# embeddings from any model (open decision O3); real paper embeddings stay NULL.

def vec(*leading):
    values = list(leading) + [0.0] * (768 - len(leading))
    return "[" + ",".join(str(v) for v in values) + "]"


def test_hybrid_query_year_filter_and_vector_similarity(conn):
    papers = [
        ("H_A", 2018, vec(1.0, 0.0)),     # closest to the query, but too old
        ("H_B", 2021, vec(0.9, 0.1)),
        ("H_C", 2022, vec(0.0, 1.0)),
        ("H_D", 2023, vec(-1.0, 0.0)),    # opposite direction
    ]
    for pid, year, v in papers:
        conn.execute("INSERT INTO paper (paper_id, title, year, embedding) VALUES (%s, %s, %s, %s::vector)",
                     (pid, "test " + pid, year, v))
    query = vec(1.0, 0.0)

    unfiltered = conn.execute(
        "SELECT paper_id FROM paper ORDER BY embedding <=> %s::vector LIMIT 1", (query,)).fetchone()[0]
    assert unfiltered == "H_A"

    hybrid = [r[0] for r in conn.execute(
        "SELECT paper_id FROM paper WHERE year >= %s ORDER BY embedding <=> %s::vector LIMIT 3",
        (2020, query))]
    assert hybrid == ["H_B", "H_C", "H_D"]
