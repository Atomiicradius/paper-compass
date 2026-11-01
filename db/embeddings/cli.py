"""Command line: python -m embeddings embed-papers [--force] [--dbname NAME]  (run from db/)"""
import argparse
import os
import sys
from pathlib import Path

import psycopg

from .pipeline import CHUNK_SIZE, EmbeddingError, embed_papers

DB_DIR = Path(__file__).resolve().parents[1]


def connection_params(dbname=None, env_file=DB_DIR / ".env"):
    """Settings from the environment, then db/.env (environment variables win), then defaults
    (127.0.0.1, port 5432). POSTGRES_PORT matters when another PostgreSQL already owns 5432."""
    from dotenv import load_dotenv
    load_dotenv(env_file)
    return {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"), "port": os.environ.get("POSTGRES_PORT", "5432"),
        "user": os.environ.get("POSTGRES_USER", ""), "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "dbname": dbname or os.environ.get("POSTGRES_DB", ""),
    }


def connect(dbname=None):
    """Autocommit; the pipeline opens its own transactions."""
    return psycopg.connect(**connection_params(dbname), autocommit=True)


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m embeddings",
                                     description="Embed papers with SPECTER2 and store them in paper.embedding.")
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("embed-papers", help="embed papers whose embedding is NULL")
    sub.add_argument("--force", action="store_true", help="re-embed every paper, including ones already embedded")
    sub.add_argument("--dbname", help="database to use instead of POSTGRES_DB from db/.env")
    sub.add_argument("--chunk-size", type=int, default=CHUNK_SIZE, help="papers per database transaction")
    return parser


def main(argv=None, encoder_factory=None, connect_fn=None):
    """encoder_factory and connect_fn exist so tests can pass a stub encoder and a test connection."""
    args = build_parser().parse_args(argv)
    if encoder_factory is None:
        from .encoder import SpecterEncoder as encoder_factory  # noqa: N813
    encoder = encoder_factory()
    connect_fn = connect_fn or connect

    def progress(done, total):
        print(f"  embedded {done}/{total}", file=sys.stderr, flush=True)

    try:
        with connect_fn(args.dbname) as conn:
            summary = embed_papers(conn, encoder, force=args.force, chunk_size=args.chunk_size, progress=progress)
    except KeyboardInterrupt:
        print("Interrupted. Finished batches are saved; run the same command again to resume.", file=sys.stderr)
        return 130
    except (EmbeddingError, psycopg.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("\n".join(summary.lines()))
    return 0
