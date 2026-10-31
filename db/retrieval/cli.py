"""Command line for trying out the SQL search layer (a testing aid; there is no API here).

Run from db/ with the embeddings environment (it has numpy for .npy files and python-dotenv):
  embeddings\\.venv\\Scripts\\python.exe -m retrieval search --vector-file q.npy --top-k 5 --year-min 2020
  embeddings\\.venv\\Scripts\\python.exe -m retrieval keyword "machine translation" --top-k 5
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

from .search import keyword_search, search

DB_DIR = Path(__file__).resolve().parents[1]


def connect(dbname=None):
    from dotenv import load_dotenv
    load_dotenv(DB_DIR / ".env")
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"), port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ.get("POSTGRES_USER", ""), password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=dbname or os.environ.get("POSTGRES_DB", ""), autocommit=True)


def read_vector(path):
    """A query vector from a .npy file (one row) or a JSON list of numbers."""
    path = Path(path)
    if path.suffix == ".npy":
        try:
            import numpy
        except ImportError:
            raise ValueError("reading .npy needs numpy; use the embeddings environment or a .json file") from None
        return [float(x) for x in numpy.load(path).reshape(-1)]
    return json.loads(path.read_text(encoding="utf-8"))


def add_filters(parser):
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--year-min", type=int)
    parser.add_argument("--year-max", type=int)
    parser.add_argument("--venue", action="append", dest="venues", help="repeat for several (OR)")
    parser.add_argument("--method", action="append", dest="methods", help="name or alias; repeat for several (OR)")
    parser.add_argument("--dataset", action="append", dest="datasets")
    parser.add_argument("--task", action="append", dest="tasks")
    parser.add_argument("--match", choices=("same_experiment", "any"), default="same_experiment",
                        help="same_experiment: one experiment must satisfy all method/dataset/task filters "
                             "(default); any: each filter may be met by a different experiment")
    parser.add_argument("--exclude", action="append", dest="exclude_ids", help="paper_id to leave out")
    parser.add_argument("--entities", action="store_true", dest="include_entities",
                        help="also show each paper's methods, datasets and tasks")
    parser.add_argument("--dbname", help="database to use instead of POSTGRES_DB from db/.env")


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m retrieval", description="Try the SQL search layer.")
    commands = parser.add_subparsers(dest="command", required=True)
    vec = commands.add_parser("search", help="vector search with a query vector read from a file")
    vec.add_argument("--vector-file", required=True, help=".npy (one 768-d vector) or .json (list of numbers)")
    vec.add_argument("--ef-search", type=int, default=100)
    add_filters(vec)
    kw = commands.add_parser("keyword", help="full-text keyword baseline")
    kw.add_argument("text")
    add_filters(kw)
    return parser


def show(results, score_name):
    for rank, r in enumerate(results, start=1):
        print(f"{rank:>3}. {r[score_name]:.4f}  {r['paper_id']}  ({r['year']}, {r['venue']})  {r['title']}")
        if "methods" in r:
            print(f"       methods: {', '.join(r['methods']) or '-'}; datasets: {', '.join(r['datasets']) or '-'}; "
                  f"tasks: {', '.join(r['tasks']) or '-'}")
    if not results:
        print("(no results)")


def main(argv=None, connect_fn=None):
    args = build_parser().parse_args(argv)
    filters = dict(top_k=args.top_k, offset=args.offset, year_min=args.year_min, year_max=args.year_max,
                   venues=args.venues, methods=args.methods, datasets=args.datasets, tasks=args.tasks,
                   exclude_ids=args.exclude_ids, include_entities=args.include_entities, match=args.match)
    try:
        with (connect_fn or connect)(args.dbname) as conn:
            if args.command == "search":
                show(search(conn, read_vector(args.vector_file), ef_search=args.ef_search, **filters), "similarity")
            else:
                show(keyword_search(conn, args.text, **filters), "score")
    except (ValueError, OSError, psycopg.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0
