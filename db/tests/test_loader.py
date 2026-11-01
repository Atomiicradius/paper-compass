"""Loader tests. They run against a throwaway database and the MOCK data in db/mock."""
import json

import pytest

from loaders import cli, extractions, papers, vocabulary, views
from loaders.common import DB_DIR

MOCK = DB_DIR / "mock"
VOCAB = MOCK / "vocabulary.jsonl"
PAPERS = MOCK / "papers.jsonl"
EXTRACTIONS = MOCK / "extractions.jsonl"

DATA_TABLES = [
    "institution", "venue", "author", "paper", "paper_author", "citation",
    "method", "dataset", "task", "setting", "method_alias", "dataset_alias", "task_alias",
    "experiment",
]


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def snapshot(conn):
    return {t: count(conn, t) for t in DATA_TABLES}


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture
def rejects(tmp_path):
    return tmp_path / "rejects"


@pytest.fixture
def loaded(conn, rejects):
    """Run the whole mock load once and return the three summaries."""
    v = vocabulary.load_vocabulary(conn, VOCAB, rejects)
    p = papers.load_papers(conn, PAPERS, rejects)
    e = extractions.load_extractions(conn, EXTRACTIONS, rejects)
    return v, p, e


# --- vocabulary -------------------------------------------------------------------------------

def test_vocabulary_loads_names_and_aliases(conn, rejects):
    s = vocabulary.load_vocabulary(conn, VOCAB, rejects)
    assert (s.read, s.inserted, s.skipped, s.rejected) == (12, 12, 0, 0)
    assert [count(conn, t) for t in ("method", "dataset", "task", "setting")] == [4, 3, 3, 2]
    assert [count(conn, t) for t in ("method_alias", "dataset_alias", "task_alias")] == [3, 1, 1]
    assert conn.execute(
        "SELECT m.canonical_name FROM method_alias a JOIN method m USING (method_id) WHERE a.alias = 'MMA'"
    ).fetchone()[0] == "Mock Method Alpha"


def test_vocabulary_setting_with_aliases_is_rejected(conn, rejects, tmp_path):
    path = write_jsonl(tmp_path / "v.jsonl", [
        {"type": "setting", "canonical_name": "Mock Setting Sparse", "aliases": ["alias not allowed"]},
        {"type": "setting", "canonical_name": "Mock Setting Shifted", "aliases": []},
    ])
    s = vocabulary.load_vocabulary(conn, path, rejects)
    assert (s.inserted, s.rejected) == (1, 1)
    assert count(conn, "setting") == 1
    assert "aliases" in s.reject_reasons[0]


def test_vocabulary_matching_ignores_case_and_whitespace(conn, rejects, tmp_path):
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    path = write_jsonl(tmp_path / "v.jsonl", [
        {"type": "method", "canonical_name": "  mock   METHOD alpha ", "aliases": []},
        {"type": "setting", "canonical_name": "MOCK setting   sparse", "aliases": []},
    ])
    s = vocabulary.load_vocabulary(conn, path, rejects)
    assert (s.inserted, s.skipped) == (0, 2)
    assert (count(conn, "method"), count(conn, "setting")) == (4, 2)


def test_vocabulary_alias_that_belongs_to_another_entity_warns(conn, rejects, tmp_path):
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    path = write_jsonl(tmp_path / "v.jsonl", [
        {"type": "method", "canonical_name": "Mock Method Beta", "aliases": ["mma"]},  # MMA belongs to Alpha
    ])
    s = vocabulary.load_vocabulary(conn, path, rejects)
    assert len(s.warnings) == 1 and "mma" in s.warnings[0].lower()
    assert count(conn, "method_alias") == 3


# --- papers -----------------------------------------------------------------------------------

def test_papers_row_counts(conn, rejects):
    s = papers.load_papers(conn, PAPERS, rejects)
    assert (s.read, s.inserted, s.skipped, s.rejected) == (10, 10, 0, 0)
    assert count(conn, "paper") == 10
    assert count(conn, "venue") == 3
    assert count(conn, "institution") == 3
    assert count(conn, "author") == 5
    assert count(conn, "paper_author") == 15
    assert count(conn, "citation") == 14


def test_papers_default_venue_type_and_null_venue(conn, rejects, tmp_path):
    path = write_jsonl(tmp_path / "p.jsonl", [
        {"paper_id": "MOCK_X1", "title": "MOCK: x", "venue": "Mock Venue", "authors": [], "references": []},
        {"paper_id": "MOCK_X2", "title": "MOCK: y", "venue": None, "authors": [], "references": []},
    ])
    papers.load_papers(conn, path, rejects)
    assert conn.execute("SELECT name, type FROM venue").fetchall() == [("Mock Venue", "other")]
    assert conn.execute("SELECT venue_id FROM paper WHERE paper_id = 'MOCK_X2'").fetchone()[0] is None


def test_papers_dangling_citation_is_skipped_and_counted(conn, rejects):
    s = papers.load_papers(conn, PAPERS, rejects)
    assert s.details["citations_skipped_not_in_corpus"] == 1
    assert s.details["cited_ids_not_in_corpus"] == ["MOCK_P404"]
    assert conn.execute("SELECT count(*) FROM paper WHERE paper_id = 'MOCK_P404'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM citation WHERE cited_paper_id = 'MOCK_P404'").fetchone()[0] == 0


def test_papers_forward_reference_within_file_is_kept(conn, rejects, tmp_path):
    path = write_jsonl(tmp_path / "p.jsonl", [
        {"paper_id": "MOCK_A", "title": "MOCK: a", "authors": [], "references": ["MOCK_B"]},
        {"paper_id": "MOCK_B", "title": "MOCK: b", "authors": [], "references": []},
    ])
    s = papers.load_papers(conn, path, rejects)
    assert count(conn, "citation") == 1
    assert s.details["citations_skipped_not_in_corpus"] == 0


def test_papers_author_without_id_is_merged_by_normalized_name_with_warning(conn, rejects):
    s = papers.load_papers(conn, PAPERS, rejects)
    rows = conn.execute(
        "SELECT a.author_id, a.external_id, i.name FROM author a "
        "LEFT JOIN institution i USING (institution_id) WHERE lower(a.name) LIKE '%author four%'"
    ).fetchall()
    assert len(rows) == 1, "the two spellings must merge into one author"
    assert rows[0][1] is None
    assert rows[0][2] == "Mock Institute North", "first institution is kept"
    linked = conn.execute("SELECT count(*) FROM paper_author WHERE author_id = %s", (rows[0][0],)).fetchone()[0]
    assert linked == 2
    assert any("author four" in w.lower() and "Mock Institute South" in w for w in s.warnings), s.warnings


def test_papers_author_with_id_keeps_first_institution_and_warns(conn, rejects):
    s = papers.load_papers(conn, PAPERS, rejects)
    inst = conn.execute(
        "SELECT i.name FROM author a JOIN institution i USING (institution_id) WHERE a.external_id = 'MOCK_A002'"
    ).fetchone()[0]
    assert inst == "Mock Institute South"
    assert any("MOCK_A002" in w and "Mock Institute East" in w for w in s.warnings), s.warnings
    assert len(s.warnings) == 2  # only these two conflicts in the mock data


def test_papers_author_order_is_stored(conn, rejects):
    papers.load_papers(conn, PAPERS, rejects)
    rows = conn.execute(
        "SELECT a.external_id, pa.author_order FROM paper_author pa JOIN author a USING (author_id) "
        "WHERE pa.paper_id = 'MOCK_P001' ORDER BY pa.author_order").fetchall()
    assert rows == [("MOCK_A001", 1), ("MOCK_A002", 2)]


def test_papers_embeddings_stay_null(conn, rejects):
    papers.load_papers(conn, PAPERS, rejects)
    assert conn.execute(
        "SELECT count(*) FROM paper WHERE embedding IS NOT NULL OR embedding_model IS NOT NULL"
    ).fetchone()[0] == 0


def test_papers_duplicate_doi_and_bad_lines_are_rejected_not_fatal(conn, rejects, tmp_path):
    path = tmp_path / "p.jsonl"
    path.write_text("\n".join([
        json.dumps({"paper_id": "MOCK_1", "title": "MOCK: one", "doi": "10.0000/mock.dup", "authors": [], "references": []}),
        json.dumps({"paper_id": "MOCK_2", "title": "MOCK: two", "doi": "10.0000/mock.dup", "authors": [], "references": []}),
        json.dumps({"paper_id": "MOCK_3", "title": "MOCK: three", "year": 1800, "authors": [], "references": []}),
        "this is not json",
        json.dumps({"paper_id": "MOCK_4", "title": "MOCK: four", "authors": [], "references": []}),
    ]) + "\n", encoding="utf-8")
    s = papers.load_papers(conn, path, rejects)
    assert (s.read, s.inserted, s.rejected) == (5, 2, 3)
    ids = {r[0] for r in conn.execute("SELECT paper_id FROM paper")}
    assert ids == {"MOCK_1", "MOCK_4"}
    lines = [json.loads(x) for x in open(s.reject_file, encoding="utf-8")]
    assert len(lines) == 3 and all("reason" in x for x in lines)


def test_papers_file_is_rolled_back_on_error(conn, rejects, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure after the papers were inserted")
    monkeypatch.setattr(papers, "insert_citations", boom)
    with pytest.raises(RuntimeError):
        papers.load_papers(conn, PAPERS, rejects)
    assert snapshot(conn) == {t: 0 for t in DATA_TABLES}


# --- extractions ------------------------------------------------------------------------------

def test_extractions_exactly_three_rows_are_rejected_with_reasons(loaded):
    _, _, e = loaded
    assert (e.read, e.inserted, e.skipped, e.rejected) == (14, 11, 0, 3)
    reasons = " | ".join(e.reject_reasons)
    assert "Mock Method Unlisted" in reasons and "method" in reasons
    assert "Mock Dataset Unlisted" in reasons and "dataset" in reasons
    assert "MOCK_P999" in reasons
    rows = [json.loads(x) for x in open(e.reject_file, encoding="utf-8")]
    assert len(rows) == 3
    assert {r["row"]["paper_id"] for r in rows} == {"MOCK_P009", "MOCK_P010", "MOCK_P999"}
    assert all(r["reason"] for r in rows)
    assert e.reject_file.endswith(".jsonl") and "extractions-" in e.reject_file


def test_extractions_rejected_rows_are_not_in_the_database(loaded, conn):
    assert count(conn, "experiment") == 11
    assert conn.execute("SELECT count(*) FROM experiment WHERE paper_id IN ('MOCK_P009','MOCK_P010','MOCK_P999')"
                        ).fetchone()[0] == 0
    # nothing was added to the vocabulary by the extraction load
    assert [count(conn, t) for t in ("method", "dataset", "task", "setting")] == [4, 3, 3, 2]


def test_extractions_aliases_are_resolved_to_canonical_ids(loaded, conn):
    def canon(paper, col, table):
        return conn.execute(
            f"SELECT t.{'name' if table == 'setting' else 'canonical_name'} FROM experiment e "
            f"JOIN {table} t ON t.{table}_id = e.{col} WHERE e.paper_id = %s", (paper,)).fetchall()
    assert ("Mock Method Alpha",) in canon("MOCK_P003", "method_id", "method")   # row used "MMA"
    assert canon("MOCK_P006", "task_id", "task") == [("Mock Task X",)]           # row used "MTX"
    assert canon("MOCK_P007", "dataset_id", "dataset") == [("Mock Dataset One",)]  # row used "MD1"


def test_extractions_keep_provenance_fields_and_null_entities(loaded, conn):
    row = conn.execute(
        "SELECT confidence, source_sentence, extractor, reviewed, dataset_id, task_id, setting_id "
        "FROM experiment e JOIN method m USING (method_id) "
        "WHERE e.paper_id = 'MOCK_P008'").fetchone()
    assert row[0] == pytest.approx(0.65)
    assert row[1] == "MOCK: invented sentence for paper eight, no dataset stated."
    assert (row[2], row[3], row[4]) == ("mock-v0", False, None)


def test_extractions_setting_matches_ignoring_case_and_whitespace(conn, rejects, tmp_path):
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    papers.load_papers(conn, PAPERS, rejects)
    path = write_jsonl(tmp_path / "e.jsonl", [
        {"paper_id": "MOCK_P001", "method": "Mock Method Delta", "dataset": None, "task": None,
         "setting": "  MOCK setting   SPARSE ", "confidence": 0.5, "source_sentence": "MOCK: s", "extractor": "mock-v0"},
    ])
    s = extractions.load_extractions(conn, path, rejects)
    assert (s.inserted, s.rejected) == (1, 0)


@pytest.mark.parametrize("confidence", [1.5, -0.1, "high", True])
def test_extractions_invalid_confidence_is_rejected(conn, rejects, tmp_path, confidence):
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    papers.load_papers(conn, PAPERS, rejects)
    path = write_jsonl(tmp_path / "e.jsonl", [
        {"paper_id": "MOCK_P001", "method": "Mock Method Delta", "dataset": None, "task": None,
         "setting": None, "confidence": confidence, "source_sentence": "MOCK: s", "extractor": "mock-v0"},
    ])
    s = extractions.load_extractions(conn, path, rejects)
    assert (s.inserted, s.rejected) == (0, 1)


def test_extractions_require_a_method(conn, rejects, tmp_path):
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    papers.load_papers(conn, PAPERS, rejects)
    path = write_jsonl(tmp_path / "e.jsonl", [
        {"paper_id": "MOCK_P001", "method": None, "dataset": None, "task": None, "setting": None,
         "confidence": 0.5, "source_sentence": "MOCK: s", "extractor": "mock-v0"},
    ])
    s = extractions.load_extractions(conn, path, rejects)
    assert (s.inserted, s.rejected) == (0, 1)


# --- idempotency ------------------------------------------------------------------------------

def test_second_run_changes_nothing(loaded, conn, rejects):
    before = snapshot(conn)
    assert before["experiment"] == 11 and before["paper"] == 10
    v, p, e = (vocabulary.load_vocabulary(conn, VOCAB, rejects),
               papers.load_papers(conn, PAPERS, rejects),
               extractions.load_extractions(conn, EXTRACTIONS, rejects))
    assert snapshot(conn) == before
    assert (v.inserted, p.inserted, e.inserted) == (0, 0, 0)
    assert (v.skipped, p.skipped, e.skipped) == (12, 10, 11)
    assert e.rejected == 3  # the same three bad rows are rejected again
    # no duplicate rows hiding behind the counts
    assert conn.execute("SELECT count(*) FROM (SELECT 1 FROM experiment GROUP BY paper_id, method_id, "
                        "dataset_id, task_id, setting_id HAVING count(*) > 1) d").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM (SELECT lower(name) FROM author WHERE external_id IS NULL "
                        "GROUP BY 1 HAVING count(*) > 1) d").fetchone()[0] == 0


# --- refresh ----------------------------------------------------------------------------------

def test_refresh_views_updates_all_twelve_views(loaded, conn):
    assert conn.execute("SELECT count(*) FROM mv_universe_size WHERE n_papers > 0").fetchone()[0] == 0
    s = views.refresh_views(conn)
    assert s.details["views_refreshed"] == 12
    universe = dict(conn.execute("SELECT pair_type, n_papers FROM mv_universe_size").fetchall())
    # worked out by hand from db/mock/extractions.jsonl (the 11 accepted rows)
    assert universe == {"method_dataset": 7, "method_task": 8, "dataset_task": 7}
    for pair_type, sql in {
        "method_dataset": "dataset_id IS NOT NULL",
        "method_task": "task_id IS NOT NULL",
        "dataset_task": "dataset_id IS NOT NULL AND task_id IS NOT NULL",
    }.items():
        raw = conn.execute(f"SELECT count(DISTINCT paper_id) FROM experiment WHERE {sql}").fetchone()[0]
        assert raw == universe[pair_type]


# --- command line -----------------------------------------------------------------------------

def test_cli_load_all_with_refresh_flag(test_db_conninfo, conn, tmp_path, capsys):
    import psycopg
    dbname = psycopg.conninfo.conninfo_to_dict(test_db_conninfo)["dbname"]
    code = cli.main(["load-all", "--vocabulary", str(VOCAB), "--papers", str(PAPERS),
                     "--extractions", str(EXTRACTIONS), "--refresh",
                     "--dbname", dbname, "--reject-dir", str(tmp_path / "rejects")])
    out = capsys.readouterr().out
    assert code == 0
    assert count(conn, "experiment") == 11
    assert conn.execute("SELECT n_papers FROM mv_universe_size WHERE pair_type = 'method_task'").fetchone()[0] == 8
    for word in ("rows read", "inserted", "skipped", "rejected", "warnings"):
        assert word in out
    assert "password" not in out.lower()


# --- extra checks: stored provenance, no empty reject files, --refresh on every load command ---

def test_extractions_store_confidence_sentence_extractor_and_reviewed_false(loaded, conn):
    """No confidence filtering yet (open decision O7): every accepted row is stored as given."""
    file_rows = [json.loads(line) for line in open(EXTRACTIONS, encoding="utf-8")]
    accepted = [r for r in file_rows if r["paper_id"] not in ("MOCK_P009", "MOCK_P010", "MOCK_P999")]
    assert len(accepted) == 11
    for row in accepted:
        stored = conn.execute(
            "SELECT confidence, source_sentence, extractor, reviewed FROM experiment WHERE source_sentence = %s",
            (row["source_sentence"],)).fetchall()
        assert len(stored) == 1, row["source_sentence"]
        confidence, sentence, extractor, reviewed = stored[0]
        assert confidence == pytest.approx(row["confidence"])
        assert sentence == row["source_sentence"]          # verbatim
        assert extractor == row["extractor"]
        assert reviewed is False
    lowest = conn.execute("SELECT min(confidence) FROM experiment").fetchone()[0]
    assert lowest == pytest.approx(0.6), "the lowest-confidence mock row must still be stored"
    assert conn.execute("SELECT count(*) FROM experiment WHERE reviewed").fetchone()[0] == 0


def test_no_reject_file_is_written_when_nothing_is_rejected(conn, rejects):
    s = vocabulary.load_vocabulary(conn, VOCAB, rejects)
    s2 = papers.load_papers(conn, PAPERS, rejects)
    assert (s.rejected, s2.rejected) == (0, 0)
    assert s.reject_file is None and s2.reject_file is None
    assert not rejects.exists() or list(rejects.iterdir()) == []


@pytest.mark.parametrize("command", ["load-vocabulary", "load-papers", "load-extractions"])
def test_refresh_flag_works_on_each_load_command(command, test_db_conninfo, conn, rejects, capsys):
    import psycopg
    dbname = psycopg.conninfo.conninfo_to_dict(test_db_conninfo)["dbname"]
    # load whatever this command depends on, directly, so only the command under test uses the CLI
    if command in ("load-papers", "load-extractions"):
        vocabulary.load_vocabulary(conn, VOCAB, rejects)
    if command == "load-extractions":
        papers.load_papers(conn, PAPERS, rejects)
    file = {"load-vocabulary": VOCAB, "load-papers": PAPERS, "load-extractions": EXTRACTIONS}[command]
    code = cli.main([command, str(file), "--refresh", "--dbname", dbname, "--reject-dir", str(rejects)])
    out = capsys.readouterr().out
    assert code == 0
    assert "views_refreshed: 12" in out
    if command == "load-extractions":
        assert conn.execute("SELECT n_papers FROM mv_universe_size WHERE pair_type = 'method_task'"
                            ).fetchone()[0] == 8, "the views must reflect the rows just loaded"


def test_load_command_without_refresh_leaves_views_stale(test_db_conninfo, conn, rejects, capsys):
    import psycopg
    dbname = psycopg.conninfo.conninfo_to_dict(test_db_conninfo)["dbname"]
    vocabulary.load_vocabulary(conn, VOCAB, rejects)
    papers.load_papers(conn, PAPERS, rejects)
    cli.main(["load-extractions", str(EXTRACTIONS), "--dbname", dbname, "--reject-dir", str(rejects)])
    out = capsys.readouterr().out
    assert "views_refreshed" not in out
    assert conn.execute("SELECT count(*) FROM mv_universe_size WHERE n_papers > 0").fetchone()[0] == 0


def test_each_warning_is_printed_once(test_db_conninfo, conn, rejects, capsys):
    import psycopg
    dbname = psycopg.conninfo.conninfo_to_dict(test_db_conninfo)["dbname"]
    cli.main(["load-papers", str(PAPERS), "--dbname", dbname, "--reject-dir", str(rejects)])
    captured = capsys.readouterr()
    assert captured.out.count("MOCK_A002") == 1
    assert "MOCK_A002" not in captured.err
