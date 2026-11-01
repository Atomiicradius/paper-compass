"""load-extractions: experiment rows from extraction output (contract section 3).

A row is inserted only if its paper exists and every method/dataset/task/setting it names is in the
controlled vocabulary (or an alias). Everything else goes to a rejects file with a reason; this
loader never creates vocabulary entries.
"""
from .common import REJECT_DIR, Summary, clean, normalize, read_jsonl, reject
from .vocabulary import vocabulary_maps

ENTITY_COLUMNS = (("method", "method_id"), ("dataset", "dataset_id"), ("task", "task_id"),
                  ("setting", "setting_id"))


def check_row(row):
    """Return a reason string if the row is malformed, else None."""
    for field in ("paper_id", "method"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            return f"{field} is required and must be a non-empty string"
    for field in ("dataset", "task", "setting"):
        value = row.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            return f"{field} must be a non-empty string or null"
    confidence = row.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                   or not 0 <= confidence <= 1):
        return f"confidence must be a number from 0 to 1 or null, got {confidence!r}"
    for field in ("source_sentence", "extractor"):
        if row.get(field) is not None and not isinstance(row[field], str):
            return f"{field} must be a string or null"
    return None


def load_extractions(conn, path, reject_dir=REJECT_DIR):
    summary = Summary("load-extractions", str(path))
    rows, rejects = read_jsonl(path)
    summary.read = len(rows) + len(rejects)

    with conn.transaction():
        lookup = {}
        for vocab_type, _ in ENTITY_COLUMNS:
            names, aliases = vocabulary_maps(conn, vocab_type)
            lookup[vocab_type] = {**aliases, **names}  # a canonical name wins over an alias
        paper_ids = {r[0] for r in conn.execute("SELECT paper_id FROM paper")}

        for number, row in rows:
            reason = check_row(row)
            if reason:
                rejects.append(reject(number, reason, row))
                continue

            problems, ids = [], {}
            paper_id = row["paper_id"].strip()
            if paper_id not in paper_ids:
                problems.append(f"paper_id {paper_id!r} is not in the paper table")
            for vocab_type, column in ENTITY_COLUMNS:
                value = row.get(vocab_type)
                if value is None:
                    ids[column] = None
                elif normalize(value) in lookup[vocab_type]:
                    ids[column] = lookup[vocab_type][normalize(value)]
                else:
                    problems.append(f"{vocab_type} {clean(value)!r} is not in the vocabulary or its aliases")
            if problems:
                rejects.append(reject(number, "; ".join(problems), row))
                continue

            cur = conn.execute(
                "INSERT INTO experiment (paper_id, method_id, dataset_id, task_id, setting_id, confidence, "
                "source_sentence, extractor) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (paper_id, ids["method_id"], ids["dataset_id"], ids["task_id"], ids["setting_id"],
                 row.get("confidence"), row.get("source_sentence"), row.get("extractor")))
            if cur.rowcount:
                summary.inserted += 1
            else:
                summary.skipped += 1  # the same experiment is already stored

    return summary.finish(rejects, "extractions", reject_dir)
