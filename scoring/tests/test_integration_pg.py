"""Integration tests against a real PostgreSQL 15+ with pgvector.

Skipped unless PC_TEST_PG_DSN is set, e.g.
    PC_TEST_PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres

The schema is built from the SQL blocks in section 1 of
context/data-and-contracts.md, inside a throwaway schema that is dropped
afterwards. All rows are MOCK data.

This is the "verify against raw SQL" check from AGENTS.md hard rule 5: the
materialized views, the on-the-fly cutoff query and the pure-Python counts
must agree.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from scoring.counts import PAIR_TYPES, fetch_pair_counts, pair_counts_from_rows
from scoring.tests.fixtures import MOCK_ROWS

DSN = os.environ.get("PC_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="PC_TEST_PG_DSN not set")

CONTRACTS = Path(__file__).resolve().parents[2] / "context" / "data-and-contracts.md"


def contract_sql() -> str:
    text = CONTRACTS.read_text(encoding="utf-8")
    section1 = text.split("## 2. Neo4j model")[0]
    return "\n".join(re.findall(r"```sql\n(.*?)```", section1, flags=re.S))


@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    schema = f"pc_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}, public")
        c.execute(contract_sql())
        _load_mock(c)
        try:
            yield c
        finally:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


def _vec(i: int) -> str:
    v = [0.0] * 768
    v[i % 768] = 1.0
    v[(i + 1) % 768] = 0.5
    return "[" + ",".join(map(str, v)) + "]"


def _load_mock(c):
    papers = sorted({(r["paper_id"], r["year"]) for r in MOCK_ROWS})
    for i, (pid, year) in enumerate(papers):
        c.execute(
            "INSERT INTO paper (paper_id, title, year, embedding, embedding_model) VALUES (%s, %s, %s, %s, 'MOCK')",
            (pid, f"MOCK {pid}", year, _vec(i)),
        )
    for t in ("method", "dataset", "task"):
        for i in (1, 2):
            c.execute(f"INSERT INTO {t} ({t}_id, canonical_name) VALUES (%s, %s)", (i, f"MOCK {t} {i}"))
    for r in MOCK_ROWS:
        c.execute(
            "INSERT INTO experiment (paper_id, method_id, dataset_id, task_id, setting_id, extractor) "
            "VALUES (%s, %s, %s, %s, %s, 'manual')",
            (r["paper_id"], r["method_id"], r["dataset_id"], r["task_id"], r["setting_id"]),
        )
    c.execute("INSERT INTO citation VALUES ('MOCK-P4', 'MOCK-P1'), ('MOCK-P3', 'MOCK-P2')")
    for (mv,) in c.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = current_schema()").fetchall():
        c.execute(f"REFRESH MATERIALIZED VIEW {mv}")


@pytest.mark.parametrize("pair_type", sorted(PAIR_TYPES))
def test_views_match_python_counts(conn, pair_type):
    expected = pair_counts_from_rows(MOCK_ROWS, pair_type)
    got = fetch_pair_counts(conn, pair_type)
    assert (got.n_total, got.n_a, got.n_b, got.observed) == (expected.n_total, expected.n_a, expected.n_b, expected.observed)


@pytest.mark.parametrize("pair_type", sorted(PAIR_TYPES))
def test_cutoff_query_matches_python_counts(conn, pair_type):
    expected = pair_counts_from_rows([r for r in MOCK_ROWS if r["year"] <= 2022], pair_type)
    got = fetch_pair_counts(conn, pair_type, cutoff_year=2022)
    assert (got.n_total, got.n_a, got.n_b, got.observed) == (expected.n_total, expected.n_a, expected.n_b, expected.observed)


def test_pipeline_stores_opportunities_with_evidence(conn):
    from scoring.pipeline import run

    # method x dataset universe = P1, P2, P4 (N = 3). m1 is in P1, P2; d2 is in P1, P4.
    # (m1, d2): observed 1 (P1), expected 2*2/3. (m2, d1) has expected 2/3 < min_expected, so it is dropped.
    ids = run(conn, "method_dataset", min_support=1, k=5.0, cutoff_year=None)
    rows = conn.execute(
        "SELECT method_id, dataset_id, observed_count, expected_count, confidence, weights_version, corpus_cutoff_year "
        "FROM opportunity WHERE opportunity_id = ANY(%s)", (ids,)
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(1, 2)]
    _, _, observed, expected, conf, wv, cutoff = rows[0]
    assert observed == 1
    assert expected == pytest.approx(4 / 3)
    assert conf == pytest.approx((4 / 3) / 5)
    assert wv == "v1-three-signal"
    assert cutoff == 2025
    evidence = dict.fromkeys(("supports_A", "supports_B", "bridge", "nearest_existing"))
    for role in evidence:
        evidence[role] = [p for (p,) in conn.execute(
            "SELECT paper_id FROM opportunity_evidence WHERE opportunity_id = %s AND role = %s ORDER BY paper_id",
            (ids[0], role),
        ).fetchall()]
    assert evidence == {
        "supports_A": ["MOCK-P2"],          # m1 without d2
        "supports_B": ["MOCK-P4"],          # d2 without m1
        "bridge": [],                       # P4 cites P1, but P1 uses both, so it is not on the A-only side
        # rag.nearest: exact papers (P1 uses both) first, then close ones by embedding similarity
        "nearest_existing": ["MOCK-P1", "MOCK-P2", "MOCK-P4"],
    }
