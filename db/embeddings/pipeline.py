"""Select papers that need an embedding, embed them one at a time, and store the vectors.

An encoder is any object with `model_string`, `sep_token` and `embed(list_of_texts) -> list_of_vectors`.
"""
import math
import time
from dataclasses import dataclass

EXPECTED_DIM = 768  # paper.embedding is vector(768)
CHUNK_SIZE = 50     # papers per database transaction


class EmbeddingError(Exception):
    pass


@dataclass
class Summary:
    model: str
    selected: int = 0
    embedded: int = 0
    skipped_no_abstract: int = 0
    already_embedded: int = 0
    seconds_per_paper: float = 0.0

    def lines(self):
        return ["== embed-papers ==",
                f"model: {self.model}",
                f"papers selected: {self.selected}",
                f"embedded: {self.embedded}",
                f"skipped (no abstract): {self.skipped_no_abstract}",
                f"already embedded (left alone): {self.already_embedded}",
                f"seconds per paper (encoding only): {self.seconds_per_paper:.3f}"]


def check_vector(vector, paper_id):
    if len(vector) != EXPECTED_DIM:
        raise EmbeddingError(f"{paper_id}: the encoder returned {len(vector)} dimensions but the paper table "
                             f"column is vector({EXPECTED_DIM}); nothing from this batch was written")
    if not all(math.isfinite(x) for x in vector):
        raise EmbeddingError(f"{paper_id}: the embedding contains NaN or infinite values (not finite); "
                             "nothing from this batch was written")


def vector_literal(vector):
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def embed_papers(conn, encoder, force=False, chunk_size=CHUNK_SIZE, progress=None):
    """Embed papers whose embedding is NULL (all papers with --force). Resumable: finished chunks stay
    stored, and a re-run only picks up what is still NULL. Papers without an abstract are skipped."""
    summary = Summary(model=encoder.model_string)

    if not force:
        mixed = conn.execute("SELECT count(*) FROM paper WHERE embedding IS NOT NULL "
                             "AND embedding_model IS DISTINCT FROM %s", (encoder.model_string,)).fetchone()[0]
        if mixed:
            raise EmbeddingError(f"{mixed} papers already have embeddings from a different model; mixing models "
                                 "would make similarities meaningless. Re-run with --force to re-embed everything.")
        summary.already_embedded = conn.execute(
            "SELECT count(*) FROM paper WHERE embedding IS NOT NULL").fetchone()[0]

    where = "" if force else "WHERE embedding IS NULL"
    rows = conn.execute(f"SELECT paper_id, title, abstract FROM paper {where} ORDER BY paper_id").fetchall()
    summary.selected = len(rows)
    todo = [r for r in rows if r[2] and r[2].strip()]
    summary.skipped_no_abstract = len(rows) - len(todo)
    if not todo:
        return summary

    sep = encoder.sep_token  # loads the model, so only reached when there is work
    encoding_seconds = 0.0
    for start in range(0, len(todo), chunk_size):
        chunk, vectors = todo[start:start + chunk_size], []
        for paper_id, title, abstract in chunk:
            began = time.perf_counter()
            vector = encoder.embed([title + sep + abstract])[0]  # batch size 1
            encoding_seconds += time.perf_counter() - began
            check_vector(vector, paper_id)
            vectors.append(vector)
        with conn.transaction():
            for (paper_id, _, _), vector in zip(chunk, vectors):
                conn.execute("UPDATE paper SET embedding = %s::vector, embedding_model = %s WHERE paper_id = %s",
                             (vector_literal(vector), encoder.model_string, paper_id))
        summary.embedded += len(chunk)
        summary.seconds_per_paper = encoding_seconds / summary.embedded
        if progress:
            progress(summary.embedded, len(todo))
    return summary
