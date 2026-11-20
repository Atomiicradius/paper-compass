"""Sync + verification against real PostgreSQL and Neo4j.

Skipped unless PC_TEST_PG_DSN and PC_TEST_NEO4J_URI (and PC_TEST_NEO4J_PASSWORD) are set.
WARNING: the sync's sweep step deletes every node of the synced labels that the
run did not touch. Point PC_TEST_NEO4J_URI at a throwaway Neo4j instance only.
"""

from __future__ import annotations

import os

import pytest

from graph.sync import sync
from graph.verify import collect

PG = os.environ.get("PC_TEST_PG_DSN")
NEO = os.environ.get("PC_TEST_NEO4J_URI")
pytestmark = pytest.mark.skipif(not (PG and NEO), reason="PC_TEST_PG_DSN / PC_TEST_NEO4J_URI not set")

# Reuse the schema + MOCK data fixture from the scoring integration test.
from scoring.tests.test_integration_pg import conn  # noqa: E402,F401


@pytest.fixture
def driver():
    neo4j = pytest.importorskip("neo4j")
    d = neo4j.GraphDatabase.driver(NEO, auth=(os.environ.get("PC_TEST_NEO4J_USER", "neo4j"),
                                              os.environ.get("PC_TEST_NEO4J_PASSWORD", "")))
    yield d
    d.close()


def snapshot(driver):
    with driver.session() as s:
        nodes = s.run("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS n ORDER BY l").data()
        rels = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY t").data()
    return nodes, rels


def test_sync_is_idempotent_and_verified(conn, driver):  # noqa: F811
    sync(conn, driver, log=lambda *_: None)
    first = snapshot(driver)
    sync(conn, driver, log=lambda *_: None)
    assert snapshot(driver) == first
    assert all(c.ok for c in collect(conn, driver)), [c for c in collect(conn, driver) if not c.ok]


def test_sweep_removes_rows_deleted_in_postgres(conn, driver):  # noqa: F811
    sync(conn, driver, log=lambda *_: None)
    conn.execute("DELETE FROM paper WHERE paper_id = 'MOCK-P5'")
    sync(conn, driver, log=lambda *_: None)
    with driver.session() as s:
        assert s.run("MATCH (p:Paper {paper_id: 'MOCK-P5'}) RETURN count(p) AS n").single()["n"] == 0
    assert all(c.ok for c in collect(conn, driver))
