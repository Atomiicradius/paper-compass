"""Connection settings: the Postgres host port comes from POSTGRES_PORT and defaults to 5432.
No database is needed. Covers every place that builds a connection: the loaders, the embeddings CLI, the
retrieval CLI and the test fixtures. (A local PostgreSQL service can own port 5432, so the container may
be published on another port.)"""
import importlib.util
import os
from pathlib import Path

import pytest

# Load THIS folder's conftest.py by path. A plain `import conftest` would pick up whichever conftest module
# is loaded first, which is the wrong one when rag/tests is run in the same pytest session.
_spec = importlib.util.spec_from_file_location("db_tests_conftest", Path(__file__).with_name("conftest.py"))
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)

from embeddings import cli as embeddings_cli
from loaders import common as loaders_common
from retrieval import cli as retrieval_cli

KEYS = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
needs_dotenv = pytest.mark.skipif(importlib.util.find_spec("dotenv") is None,
                                  reason="python-dotenv is only installed in the embeddings environment")


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Work on a copy of os.environ so nothing a builder loads from an env file leaks into other tests,
    and start without any POSTGRES_* variable."""
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


# each builder: env_file -> {"host": ..., "port": ..., "dbname": ...} (always strings)
def _loaders(env_file):
    p = loaders_common.connection_params(env_file=env_file)
    return p["host"], p["port"]


def _embeddings(env_file):
    p = embeddings_cli.connection_params(env_file=env_file)
    return p["host"], p["port"]


def _retrieval(env_file):
    p = retrieval_cli.connection_params(env_file=env_file)
    return p["host"], p["port"]


def _fixtures(env_file):
    s = conftest._settings(env_file)
    info = conftest._conninfo("postgres", s)
    assert f"host={s['POSTGRES_HOST']} port={s['POSTGRES_PORT']} " in info   # the conninfo uses the same values
    return s["POSTGRES_HOST"], s["POSTGRES_PORT"]


BUILDERS = [pytest.param(_loaders, id="loaders"),
            pytest.param(_fixtures, id="test-fixtures"),
            pytest.param(_embeddings, id="embeddings-cli", marks=needs_dotenv),
            pytest.param(_retrieval, id="retrieval-cli", marks=needs_dotenv)]


@pytest.mark.parametrize("builder", BUILDERS)
def test_default_is_localhost_5432(builder, tmp_path):
    assert builder(tmp_path / "missing.env") == ("127.0.0.1", "5432")


@pytest.mark.parametrize("builder", BUILDERS)
def test_port_comes_from_the_environment(builder, tmp_path, monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "55432")
    assert builder(tmp_path / "missing.env") == ("127.0.0.1", "55432")


@pytest.mark.parametrize("builder", BUILDERS)
def test_port_comes_from_the_env_file(builder, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=u\nPOSTGRES_PASSWORD=p\nPOSTGRES_DB=d\nPOSTGRES_PORT=55432\n", encoding="utf-8")
    assert builder(env_file) == ("127.0.0.1", "55432")


@pytest.mark.parametrize("builder", BUILDERS)
def test_environment_wins_over_the_env_file(builder, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PORT=55432\n", encoding="utf-8")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    assert builder(env_file) == ("127.0.0.1", "6543")


@pytest.mark.parametrize("builder", BUILDERS)
def test_an_env_file_without_a_port_keeps_the_default(builder, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=u\nPOSTGRES_PASSWORD=p\nPOSTGRES_DB=d\n", encoding="utf-8")
    assert builder(env_file) == ("127.0.0.1", "5432")


def test_the_loaders_use_the_dbname_argument_over_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_DB=main_db\n", encoding="utf-8")
    assert loaders_common.connection_params("other_db", env_file)["dbname"] == "other_db"
    assert loaders_common.connection_params(None, env_file)["dbname"] == "main_db"
