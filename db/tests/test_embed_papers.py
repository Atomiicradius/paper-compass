"""Tests for the embedding pipeline. They use a stub encoder, so the real model is never loaded
(except the one test marked `slow`). All papers here are made up for the test, in a throwaway database."""
import math
import random
import re
import zlib

import psycopg
import pytest

from embeddings import cli, encoder as real_encoder, pipeline

DIM = 768


class StubEncoder:
    """A fake encoder: deterministic pseudo-random vectors derived from the input text."""
    sep_token = "[SEP]"

    def __init__(self, model_string="stub-model@rev1 (proximity)", dim=DIM, fail_on_call=None, nan=False):
        self.model_string, self.dim, self.fail_on_call, self.nan = model_string, dim, fail_on_call, nan
        self.texts = []

    def vector_for(self, text):
        rng = random.Random(zlib.crc32(text.encode("utf-8")))
        return [rng.gauss(0, 1) for _ in range(self.dim)]

    def embed(self, texts):
        out = []
        for text in texts:
            self.texts.append(text)
            if self.fail_on_call is not None and len(self.texts) == self.fail_on_call:
                raise RuntimeError("simulated crash")
            vec = self.vector_for(text)
            if self.nan:
                vec[3] = float("nan")
            out.append(vec)
        return out


def add_papers(conn, rows):
    for paper_id, title, abstract in rows:
        conn.execute("INSERT INTO paper (paper_id, title, abstract, year) VALUES (%s, %s, %s, 2020)",
                     (paper_id, title, abstract))


def stored(conn, paper_id):
    vec_text, model = conn.execute("SELECT embedding::text, embedding_model FROM paper WHERE paper_id = %s",
                                   (paper_id,)).fetchone()
    return (None if vec_text is None else [float(x) for x in vec_text.strip("[]").split(",")]), model


def n_embedded(conn):
    return conn.execute("SELECT count(*) FROM paper WHERE embedding IS NOT NULL").fetchone()[0]


@pytest.fixture
def four_papers(conn):
    add_papers(conn, [("T_A", "Title A", "Abstract A"), ("T_B", "Title B", None),
                      ("T_C", "Title C", "   "), ("T_D", "Title D", "Abstract D")])
    return conn


# --- selection and skipping -------------------------------------------------------------------

def test_embeds_papers_with_an_abstract_and_skips_the_rest(four_papers):
    conn, enc = four_papers, StubEncoder()
    s = pipeline.embed_papers(conn, enc)
    assert (s.selected, s.embedded, s.skipped_no_abstract, s.already_embedded) == (4, 2, 2, 0)
    assert stored(conn, "T_A")[0] is not None and stored(conn, "T_D")[0] is not None
    for skipped in ("T_B", "T_C"):
        assert stored(conn, skipped) == (None, None), "no abstract: nothing may be embedded or invented"
    assert len(enc.texts) == 2


def test_input_is_title_separator_abstract_exactly(four_papers):
    enc = StubEncoder()
    pipeline.embed_papers(four_papers, enc)
    assert enc.texts == ["Title A[SEP]Abstract A", "Title D[SEP]Abstract D"]


def test_encoder_is_called_one_paper_at_a_time(four_papers):
    calls = []

    class Spy(StubEncoder):
        def embed(self, texts):
            calls.append(len(texts))
            return super().embed(texts)
    pipeline.embed_papers(four_papers, Spy())
    assert calls == [1, 1]


def test_stored_vector_and_model_string(four_papers):
    conn, enc = four_papers, StubEncoder(model_string="stub@abc (proximity)")
    pipeline.embed_papers(conn, enc)
    vec, model = stored(conn, "T_A")
    expected = enc.vector_for("Title A[SEP]Abstract A")
    assert len(vec) == DIM and model == "stub@abc (proximity)"
    assert all(math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-6) for a, b in zip(vec, expected))


def test_other_paper_columns_are_untouched(four_papers):
    pipeline.embed_papers(four_papers, StubEncoder())
    assert four_papers.execute("SELECT title, abstract, year FROM paper WHERE paper_id = 'T_A'"
                               ).fetchone() == ("Title A", "Abstract A", 2020)


# --- idempotency, force, resume ---------------------------------------------------------------

def test_second_run_embeds_nothing_and_does_not_load_the_model(four_papers):
    conn = four_papers
    pipeline.embed_papers(conn, StubEncoder())
    before = {p: stored(conn, p) for p in ("T_A", "T_D")}
    enc = StubEncoder()
    s = pipeline.embed_papers(conn, enc)
    assert (s.selected, s.embedded, s.already_embedded) == (2, 0, 2)  # the two without abstract stay skipped
    assert s.skipped_no_abstract == 2 and enc.texts == []
    assert {p: stored(conn, p) for p in before} == before and n_embedded(conn) == 2


def test_force_re_embeds_everything(four_papers):
    conn = four_papers
    pipeline.embed_papers(conn, StubEncoder(model_string="old (proximity)"))
    enc = StubEncoder(model_string="new (proximity)")
    s = pipeline.embed_papers(conn, enc, force=True)
    assert (s.selected, s.embedded, s.already_embedded) == (4, 2, 0)
    assert len(enc.texts) == 2 and stored(conn, "T_A")[1] == "new (proximity)"


def test_interrupted_run_keeps_finished_chunks_and_resumes(conn):
    add_papers(conn, [(f"T_{i}", f"Title {i}", f"Abstract {i}") for i in range(5)])
    with pytest.raises(RuntimeError):
        pipeline.embed_papers(conn, StubEncoder(fail_on_call=4), chunk_size=2)
    assert n_embedded(conn) == 2, "the first chunk of 2 was committed, the interrupted chunk was not"

    resume = StubEncoder()
    s = pipeline.embed_papers(conn, resume, chunk_size=2)
    assert (s.selected, s.embedded, s.already_embedded) == (3, 3, 2)
    assert len(resume.texts) == 3, "papers already embedded must not be embedded again"
    assert n_embedded(conn) == 5


def test_default_run_refuses_to_mix_models(four_papers):
    conn = four_papers
    pipeline.embed_papers(conn, StubEncoder(model_string="model-A (proximity)"))
    with pytest.raises(pipeline.EmbeddingError, match="--force"):
        pipeline.embed_papers(conn, StubEncoder(model_string="model-B (proximity)"))
    assert stored(conn, "T_A")[1] == "model-A (proximity)"


# --- safety checks ----------------------------------------------------------------------------

def test_wrong_dimension_stops_before_anything_is_written(four_papers):
    with pytest.raises(pipeline.EmbeddingError, match="768"):
        pipeline.embed_papers(four_papers, StubEncoder(dim=384))
    assert n_embedded(four_papers) == 0


def test_nan_values_are_rejected_and_not_written(four_papers):
    with pytest.raises(pipeline.EmbeddingError, match="NaN|finite"):
        pipeline.embed_papers(four_papers, StubEncoder(nan=True))
    assert n_embedded(four_papers) == 0


# --- model string and pins --------------------------------------------------------------------

def test_model_string_names_both_pinned_revisions():
    s = real_encoder.model_string()
    assert re.fullmatch(r"allenai/specter2_base@[0-9a-f]{40}\+allenai/specter2@[0-9a-f]{40} \(proximity\)", s)
    assert real_encoder.SpecterEncoder.model_string == s
    assert real_encoder.MAX_LENGTH == 512


def test_creating_the_real_encoder_does_not_load_the_model():
    # must be cheap: the model is only loaded on first use (and not at all if nothing needs embedding)
    enc = real_encoder.SpecterEncoder()
    assert enc._model is None


# --- command line -----------------------------------------------------------------------------

@pytest.fixture
def connect_to_test_db(test_db_conninfo):
    return lambda dbname: psycopg.connect(test_db_conninfo, autocommit=True)


def test_cli_prints_the_summary(connect_to_test_db, four_papers, capsys):
    code = cli.main(["embed-papers"], encoder_factory=lambda: StubEncoder("stub@x (proximity)"),
                    connect_fn=connect_to_test_db)
    out = capsys.readouterr().out
    assert code == 0
    for text in ("papers selected: 4", "embedded: 2", "skipped (no abstract): 2",
                 "already embedded (left alone): 0", "seconds per paper", "stub@x (proximity)"):
        assert text in out, text
    assert n_embedded(four_papers) == 2


def test_cli_force_flag(connect_to_test_db, four_papers, capsys):
    cli.main(["embed-papers"], encoder_factory=StubEncoder, connect_fn=connect_to_test_db)
    capsys.readouterr()
    cli.main(["embed-papers", "--force"], encoder_factory=StubEncoder, connect_fn=connect_to_test_db)
    out = capsys.readouterr().out
    assert "embedded: 2" in out and "already embedded (left alone): 0" in out


# --- the real model (skipped unless run with -m slow) -------------------------------------------

@pytest.mark.slow
def test_real_specter2_on_three_texts():
    enc = real_encoder.SpecterEncoder()
    assert enc.sep_token == "[SEP]"
    texts = [
        "Title one" + enc.sep_token + "We study neural machine translation for low-resource languages.",
        "Title two" + enc.sep_token + "We segment medical images with a convolutional network.",
        "Title three" + enc.sep_token + "We train an agent with reinforcement learning in simulated games.",
    ]
    vectors = enc.embed(texts)
    assert len(vectors) == 3 and all(len(v) == DIM for v in vectors)
    assert all(math.isfinite(x) for v in vectors for x in v)
    assert vectors[0] != vectors[1] != vectors[2]
