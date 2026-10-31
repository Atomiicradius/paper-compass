"""Shared fixtures for the schema tests.

Each test run creates a throwaway database, applies db/init.sql to it, and drops it afterwards.
The main database (POSTGRES_DB) is never touched. Connection settings come from db/.env
(or the same variable names in the environment). The Postgres container must be running.
"""
import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest

DB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DB_DIR))  # so tests can import the `loaders` package


def _settings():
    values = {}
    env_file = DB_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        values[key] = os.environ.get(key, values.get(key, ""))
    return values


def _conninfo(dbname, s):
    return f"host=127.0.0.1 port=5432 user={s['POSTGRES_USER']} password={s['POSTGRES_PASSWORD']} dbname={dbname}"


@pytest.fixture(scope="session")
def test_db_conninfo():
    s = _settings()
    name = "pc_test_" + uuid.uuid4().hex[:10]
    admin = psycopg.connect(_conninfo("postgres", s), autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    try:
        with psycopg.connect(_conninfo(name, s), autocommit=True) as conn:
            conn.execute((DB_DIR / "init.sql").read_text(encoding="utf-8"))
        yield _conninfo(name, s)
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def private_db():
    """A brand-new throwaway database, for tests that load a lot of data or drop indexes.
    Created from db/init.sql and dropped afterwards; the shared test database is not touched."""
    s = _settings()
    name = "pc_test_" + uuid.uuid4().hex[:10]
    admin = psycopg.connect(_conninfo("postgres", s), autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    c = None
    try:
        c = psycopg.connect(_conninfo(name, s), autocommit=True)
        c.execute((DB_DIR / "init.sql").read_text(encoding="utf-8"))
        yield c
    finally:
        if c is not None:
            c.close()
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def conn(test_db_conninfo):
    """A connection to the throwaway database with every table emptied first.
    Materialized views are refreshed too, so no test sees the contents left by an earlier test."""
    with psycopg.connect(test_db_conninfo, autocommit=True) as c:
        tables = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]
        c.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        for (view,) in c.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'").fetchall():
            c.execute(f"REFRESH MATERIALIZED VIEW {view}")
        yield c
