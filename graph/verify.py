"""Count verification between PostgreSQL and Neo4j (sync rule 3).

    python -m graph.verify --pg-dsn ... --neo4j-uri ... --neo4j-password ...

Compares every node label and relationship type in graph.model, which covers
the required papers, citations and experiments. Exits non-zero on mismatch.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from graph.model import NODES, RELS


@dataclass
class CountCheck:
    name: str
    postgres: int
    neo4j: int

    @property
    def ok(self) -> bool:
        return self.postgres == self.neo4j


def collect(pg_conn, driver, database: str | None = None) -> list[CountCheck]:
    checks = []
    with pg_conn.cursor() as cur, driver.session(database=database) as session:
        for spec in NODES:
            cur.execute(f"SELECT COUNT(*) FROM ({spec.sql}) s")
            pg_n = cur.fetchone()[0]
            neo_n = session.run(f"MATCH (n:{spec.label}) RETURN count(n) AS n").single()["n"]
            checks.append(CountCheck(f":{spec.label}", pg_n, neo_n))
        for spec in RELS:
            cur.execute(f"SELECT COUNT(*) FROM ({spec.sql}) s")
            pg_n = cur.fetchone()[0]
            neo_n = session.run(
                f"MATCH (:{spec.src_label})-[r:{spec.rel_type}]->(:{spec.dst_label}) RETURN count(r) AS n"
            ).single()["n"]
            checks.append(CountCheck(f"({spec.src_label})-[:{spec.rel_type}]->({spec.dst_label})", pg_n, neo_n))
    return checks


def verify(pg_conn, driver, database: str | None = None, log=print) -> list[CountCheck]:
    """Print every check and return the mismatches."""
    checks = collect(pg_conn, driver, database)
    width = max(len(c.name) for c in checks)
    for c in checks:
        log(f"{'OK ' if c.ok else 'BAD'} {c.name:<{width}}  postgres={c.postgres:<8} neo4j={c.neo4j}")
    bad = [c for c in checks if not c.ok]
    if bad:
        log(f"SYNC VERIFICATION FAILED: {len(bad)} mismatch(es)")
    else:
        log("sync verification passed")
    return bad


def main() -> None:
    import psycopg
    from neo4j import GraphDatabase

    ap = argparse.ArgumentParser(description="Compare PostgreSQL and Neo4j counts")
    ap.add_argument("--pg-dsn", required=True)
    ap.add_argument("--neo4j-uri", required=True)
    ap.add_argument("--neo4j-user", default="neo4j")
    ap.add_argument("--neo4j-password", required=True)
    ap.add_argument("--neo4j-database", default=None)
    args = ap.parse_args()
    with psycopg.connect(args.pg_dsn) as pg, GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    ) as driver:
        bad = verify(pg, driver, args.neo4j_database)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
