"""Idempotent batch sync PostgreSQL -> Neo4j (data-and-contracts.md section 2.3).

    python -m graph.sync --pg-dsn postgresql://... --neo4j-uri bolt://localhost:7687 \
                         --neo4j-user neo4j --neo4j-password ...

* Only MERGE on IDs, never CREATE. Properties are overwritten from PostgreSQL.
* Mark and sweep: every node and relationship touched in this run gets
  `_sync_run = <run id>`; afterwards anything with an older run id is removed,
  so rows deleted or changed in PostgreSQL disappear from the graph too.
  Re-running on unchanged data yields the same graph (only `_sync_run` differs).
* Runs graph.verify at the end and exits non-zero on any count mismatch.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, Iterator

from graph.model import NODES, RELS, NodeSpec, RelSpec

BATCH_SIZE = 1000


def batched(rows: Iterable[dict], size: int = BATCH_SIZE) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for r in rows:
        batch.append(r)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def pg_rows(pg_conn, sql: str) -> Iterator[dict]:
    with pg_conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        for row in cur:
            yield dict(zip(cols, row))


def apply_constraints(session) -> None:
    text = (Path(__file__).parent / "constraints.cypher").read_text(encoding="utf-8")
    for stmt in text.split(";"):
        lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("//")]
        if lines:
            session.run("\n".join(lines))


def node_merge_cypher(spec: NodeSpec) -> str:
    return (
        f"UNWIND $rows AS row "
        f"MERGE (n:{spec.label} {{{spec.key}: row.{spec.key}}}) "
        f"SET n += row, n._sync_run = $run"
    )


def rel_merge_cypher(spec: RelSpec) -> str:
    set_props = "".join(f", r.`{p}` = row.`{p}`" for p in spec.props)
    return (
        f"UNWIND $rows AS row "
        f"MATCH (a:{spec.src_label} {{{spec.src_key}: row.src}}) "
        f"MATCH (b:{spec.dst_label} {{{spec.dst_key}: row.dst}}) "
        f"MERGE (a)-[r:{spec.rel_type}]->(b) "
        f"SET r._sync_run = $run{set_props}"
    )


def sweep_cypher() -> list[str]:
    """Remove anything not touched by this run. Relationships first, then nodes."""
    stmts = []
    for spec in RELS:
        stmts.append(
            f"MATCH (:{spec.src_label})-[r:{spec.rel_type}]->(:{spec.dst_label}) "
            f"WHERE r._sync_run IS NULL OR r._sync_run <> $run DELETE r"
        )
    for spec in NODES:
        stmts.append(
            f"MATCH (n:{spec.label}) WHERE n._sync_run IS NULL OR n._sync_run <> $run DETACH DELETE n"
        )
    return stmts


def sync(pg_conn, driver, database: str | None = None, log=print) -> str:
    run = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    with driver.session(database=database) as session:
        apply_constraints(session)
        for spec in NODES:
            n = 0
            for batch in batched(pg_rows(pg_conn, spec.sql)):
                session.execute_write(lambda tx, b=batch: tx.run(node_merge_cypher(spec), rows=b, run=run).consume())
                n += len(batch)
            log(f"merged {n:>7} :{spec.label}")
        for spec in RELS:
            n = 0
            for batch in batched(pg_rows(pg_conn, spec.sql)):
                session.execute_write(lambda tx, b=batch: tx.run(rel_merge_cypher(spec), rows=b, run=run).consume())
                n += len(batch)
            log(f"merged {n:>7} ({spec.src_label})-[:{spec.rel_type}]->({spec.dst_label})")
        for stmt in sweep_cypher():
            session.execute_write(lambda tx, s=stmt: tx.run(s, run=run).consume())
    return run


def main() -> None:
    import psycopg
    from neo4j import GraphDatabase

    from graph.verify import verify

    ap = argparse.ArgumentParser(description="Idempotent PostgreSQL -> Neo4j sync")
    ap.add_argument("--pg-dsn", required=True)
    ap.add_argument("--neo4j-uri", required=True)
    ap.add_argument("--neo4j-user", default="neo4j")
    ap.add_argument("--neo4j-password", required=True)
    ap.add_argument("--neo4j-database", default=None)
    args = ap.parse_args()

    with psycopg.connect(args.pg_dsn) as pg, GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    ) as driver:
        run = sync(pg, driver, args.neo4j_database)
        print(f"sync run {run} done; verifying")
        mismatches = verify(pg, driver, args.neo4j_database)
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
