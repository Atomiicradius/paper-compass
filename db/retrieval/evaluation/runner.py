"""Score precomputed rankings against labelled queries.  No database, no model.

  python -m retrieval.evaluation run --queries FILE --ranker NAME [--rankings FILE] [-k 10]

--queries   JSON Lines, one query per line (format: db/proposals/retrieval-eval-format.md).
--ranker    a label for the system being scored (for example keyword, vector, hybrid).
--rankings  JSON object {query_id: [paper_id, ...]} with the best result first. Default:
            rankings-<ranker>.json in the same folder as the queries file.
"""
import argparse
import json
import sys
from pathlib import Path

from .metrics import GRADES, evaluate_query, mean


class FormatError(Exception):
    pass


def load_queries(path):
    """Read and validate the query file. Returns a list of query dicts."""
    queries, seen = [], set()
    with open(path, encoding="utf-8-sig") as f:   # utf-8-sig: a BOM added by a Windows editor is harmless
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FormatError(f"{path} line {number}: invalid JSON ({exc.msg})") from None
            where = f"{path} line {number}"
            if not isinstance(row, dict):
                raise FormatError(f"{where}: each line must be a JSON object")
            query_id = row.get("query_id")
            if not isinstance(query_id, str) or not query_id.strip():
                raise FormatError(f"{where}: query_id must be a non-empty string")
            if query_id in seen:
                raise FormatError(f"{where}: duplicate query_id {query_id!r}")
            seen.add(query_id)
            if not isinstance(row.get("query_text"), str) or not row["query_text"].strip():
                raise FormatError(f"{where}: query_text must be a non-empty string")
            if "filters" in row and not isinstance(row["filters"], dict):
                raise FormatError(f"{where}: filters, if present, must be an object")
            judgments = row.get("judgments")
            if not isinstance(judgments, dict):
                raise FormatError(f"{where}: judgments must be an object of paper_id -> grade")
            for paper_id, grade in judgments.items():
                if isinstance(grade, bool) or not isinstance(grade, int) or grade not in GRADES:
                    raise FormatError(f"{where}: grade for {paper_id!r} must be 0, 1 or 2, got {grade!r}")
            queries.append(row)
    if not queries:
        raise FormatError(f"{path}: no queries found")
    return queries


def load_rankings(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise FormatError(f"{path}: invalid JSON ({exc.msg})") from None
    if not isinstance(data, dict) or not all(
            isinstance(v, list) and all(isinstance(i, str) for i in v) for v in data.values()):
        raise FormatError(f"{path}: expected an object of query_id -> list of paper_id strings")
    return data


def run(queries_path, ranker, rankings_path, k):
    """Return the report as a list of text lines."""
    queries = load_queries(queries_path)
    rankings = load_rankings(rankings_path)
    missing = [q["query_id"] for q in queries if q["query_id"] not in rankings]
    if missing:
        raise FormatError(f"{rankings_path} has no ranking for: {', '.join(missing)}")

    rows, skipped = [], []
    for query in queries:
        result = evaluate_query(rankings[query["query_id"]], query["judgments"], k)
        (rows if result["relevant_count"] else skipped).append((query["query_id"], result))

    lines = [f"ranker: {ranker}   k={k}   queries file: {queries_path}",
             f"{'query':<10}{'P@k':>8}{'R@k':>8}{'RR':>8}{'nDCG@k':>9}"]
    for query_id, r in rows:
        lines.append(f"{query_id:<10}{r['precision']:>8.4f}{r['recall']:>8.4f}"
                     f"{r['reciprocal_rank']:>8.4f}{r['ndcg']:>9.4f}")
    means = {key: mean([r[key] for _, r in rows]) for key in ("precision", "recall", "reciprocal_rank", "ndcg")}
    if rows:
        lines.append(f"{'mean':<10}{means['precision']:>8.4f}{means['recall']:>8.4f}"
                     f"{means['reciprocal_rank']:>8.4f}{means['ndcg']:>9.4f}")
    lines.append(f"mean over {len(rows)} of {len(queries)} queries (mean RR is the MRR)")
    for query_id, _ in skipped:
        lines.append(f"left out: {query_id} has no relevant paper in its judgments")
    return lines


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m retrieval.evaluation",
                                     description="Score precomputed rankings against labelled queries.")
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("run", help="print precision, recall, MRR and nDCG per query and the mean")
    sub.add_argument("--queries", required=True, help="JSON Lines query file with judgments")
    sub.add_argument("--ranker", required=True, help="label of the system being scored, e.g. keyword")
    sub.add_argument("--rankings", help="JSON file {query_id: [paper_id, ...]} (default: rankings-<ranker>.json "
                                        "next to the queries file)")
    sub.add_argument("-k", type=int, default=10, help="cutoff for P@k, R@k and nDCG@k (default 10)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.k < 1:
        print("ERROR: -k must be at least 1", file=sys.stderr)
        return 1
    rankings = args.rankings or Path(args.queries).with_name(f"rankings-{args.ranker}.json")
    try:
        print("\n".join(run(args.queries, args.ranker, rankings, args.k)))
    except (FormatError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0
