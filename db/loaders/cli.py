"""Command line for the loaders. Run from db/:  python -m loaders <command> ..."""
import argparse
import sys

import psycopg

from .common import REJECT_DIR, connect
from .extractions import load_extractions
from .papers import load_papers
from .views import refresh_views
from .vocabulary import load_vocabulary


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m loaders",
                                     description="Load vocabulary, paper metadata and extractions into PostgreSQL.")
    # Options every command accepts, written after the command name.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--dbname", help="database to use instead of POSTGRES_DB from db/.env")
    shared.add_argument("--reject-dir", default=str(REJECT_DIR), help="where rejected rows are written")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("load-vocabulary", "load vocabulary.jsonl"),
                            ("load-papers", "load paper metadata JSON Lines"),
                            ("load-extractions", "load extraction JSON Lines")):
        sub = commands.add_parser(name, help=help_text, parents=[shared])
        sub.add_argument("file")
        sub.add_argument("--refresh", action="store_true", help="refresh the materialized views afterwards")

    commands.add_parser("refresh-views", help="refresh all materialized views concurrently", parents=[shared])

    full = commands.add_parser("load-all", help="vocabulary, then papers, then extractions", parents=[shared])
    full.add_argument("--vocabulary", required=True)
    full.add_argument("--papers", required=True)
    full.add_argument("--extractions", required=True)
    full.add_argument("--refresh", action="store_true", help="refresh the materialized views at the end")
    return parser


def show(summary):
    print("\n".join(summary.lines()))
    print()


def run(conn, args):
    reject_dir = args.reject_dir
    if args.command == "load-vocabulary":
        show(load_vocabulary(conn, args.file, reject_dir))
    elif args.command == "load-papers":
        show(load_papers(conn, args.file, reject_dir))
    elif args.command == "load-extractions":
        show(load_extractions(conn, args.file, reject_dir))
    elif args.command == "load-all":
        show(load_vocabulary(conn, args.vocabulary, reject_dir))
        show(load_papers(conn, args.papers, reject_dir))
        show(load_extractions(conn, args.extractions, reject_dir))
    if args.command == "refresh-views" or getattr(args, "refresh", False):
        show(refresh_views(conn))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        with connect(args.dbname) as conn:
            run(conn, args)
    except (psycopg.Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("The file being loaded was rolled back; nothing from it was stored.", file=sys.stderr)
        return 1
    return 0
