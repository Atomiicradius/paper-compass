"""Fixtures for the rag tests.

HOW `rag` BECOMES IMPORTABLE, AND WHY HERE
`rag/` sits at the repository root. pytest (default "prepend" import mode) puts only the test file's own
folder (rag/tests) on sys.path, so `import rag` would fail without help. This conftest adds the repository
root to sys.path. A conftest.py in rag/tests only affects tests under rag/tests, so it cannot clash with
the root conftest.py that Person 3's branch has: no root conftest.py is created here.

It also adds db/ to sys.path to reuse `loaders.common.connection_params`, which reads db/.env and
POSTGRES_PORT, so these tests connect to the same Postgres as the db tests (a local PostgreSQL service
can own port 5432). The rag package itself never imports from db/.

Each test session creates a throwaway database, applies db/init.sql and drops it afterwards. The main
database is never touched. The Postgres container must be running.
"""
import sys
import uuid
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = REPO_ROOT / "db"
for path in (REPO_ROOT, DB_DIR, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from loaders.common import connection_params  # noqa: E402


@pytest.fixture(scope="session")
def test_db_params():
    name = "pc_test_rag_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(**connection_params("postgres"), autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    try:
        params = connection_params(name)
        with psycopg.connect(**params, autocommit=True) as c:
            c.execute((DB_DIR / "init.sql").read_text(encoding="utf-8"))
        yield params
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def conn(test_db_params):
    """A connection to the throwaway database with every table emptied and every view refreshed."""
    with psycopg.connect(**test_db_params, autocommit=True) as c:
        tables = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]
        c.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        for (view,) in c.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'").fetchall():
            c.execute(f"REFRESH MATERIALIZED VIEW {view}")
        yield c
