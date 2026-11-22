"""Prepare the derived data a demo needs, from a freshly restored pilot database. Safe to run twice.

    python -m api.prepare_demo [--dbname pc_pilot] [--force] [--skip-neo4j]

What a restored dump does not contain, and this fills in:
  1. opportunities: Method x Task scoring with the settings chosen on pc_pilot (scoring/tuning-pc_pilot.md:
     min_support 5, min_sparsity 0.3, k 5). Skipped if opportunities already exist (use --force to redo them).
  2. clusters: graph/out/clusters.json with the pilot settings (the API also computes it on first use).
  3. Neo4j: the projection of PostgreSQL (python -m graph.sync), unless it already has the same number of papers.

The connection comes from PC_PG_DSN / PC_NEO4J_* or, if those are not set, from db/.env (database pc_pilot, or
--dbname). Nothing is invented: every step reads the database and writes derived rows only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# the settings recorded in decision 32
PILOT_SCORING = {"pair_type": "method_task", "min_support": 5, "min_sparsity": 0.3, "k": 5.0}


def prepare_scoring(conn, pair_type: str, min_support: int, min_sparsity: float, k: float, force: bool = False) -> dict:
    from scoring.pipeline import run

    existing = conn.execute("SELECT COUNT(*) FROM opportunity").fetchone()[0]
    if existing and not force:
        return {"action": "kept", "existing": existing}
    ids = run(conn, pair_type, min_support, k, None, min_sparsity=min_sparsity, replace=True)
    return {"action": "scored", "stored": len(ids), "existing": existing}


def prepare_clusters(conn, out: Path, force: bool = False) -> dict:
    from graph.clusters import PILOT_SETTINGS, build_result, single_embedding_model, write_result

    if out.exists() and not force:
        return {"action": "kept", "path": str(out)}
    model = single_embedding_model(conn)
    if model is None:
        return {"action": "skipped", "reason": "no embeddings, or embeddings from several models"}
    result = build_result(conn, model, **PILOT_SETTINGS)
    write_result(result, out)
    return {"action": "computed", "clusters": len(result["clusters"]), "noise": result["n_noise"], "path": str(out)}


def prepare_neo4j(pg_conn, force: bool = False) -> dict:
    uri = os.environ.get("PC_NEO4J_URI")
    if not uri:
        return {"action": "skipped", "reason": "Neo4j is not configured (PC_NEO4J_URI / PC_NEO4J_PASSWORD)"}
    from neo4j import GraphDatabase

    from graph.sync import sync
    from graph.verify import verify

    papers = pg_conn.execute("SELECT COUNT(*) FROM paper").fetchone()[0]
    auth = (os.environ.get("PC_NEO4J_USER", "neo4j"), os.environ.get("PC_NEO4J_PASSWORD", ""))
    with GraphDatabase.driver(uri, auth=auth, connection_timeout=5, connection_acquisition_timeout=10) as driver:
        with driver.session() as session:
            have = session.run("MATCH (p:Paper) RETURN count(p) AS n").single()["n"]
        if have == papers and not force:
            return {"action": "kept", "papers": have}
        sync(pg_conn, driver, log=lambda *_: None)
        mismatches = verify(pg_conn, driver, None, log=lambda *_: None)
    return {"action": "synced", "papers": papers, "mismatches": len(mismatches)}


def main(argv: list[str] | None = None) -> int:
    import psycopg

    from api.main import _settings_from_env_file
    from graph.clusters import DEFAULT_OUT

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dbname", default=None, help="database name (default: PC_PG_DBNAME or pc_pilot)")
    ap.add_argument("--force", action="store_true", help="redo every step even if its output exists")
    ap.add_argument("--skip-neo4j", action="store_true")
    ap.add_argument("--clusters-path", default=os.environ.get("PC_CLUSTERS_PATH", str(DEFAULT_OUT)))
    args = ap.parse_args(argv)
    if args.dbname:
        os.environ["PC_PG_DBNAME"] = args.dbname
    for key, value in _settings_from_env_file().items():      # db/.env supplies what the environment does not
        os.environ.setdefault(key, value)
    dsn = os.environ.get("PC_PG_DSN")
    if not dsn:
        print("ERROR: set PC_PG_DSN or create db/.env (see db/README.md)", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            papers = conn.execute("SELECT COUNT(*) FROM paper").fetchone()[0]
            print(f"database: {papers} papers")
            if papers == 0:
                print("ERROR: the database has no papers; restore the pilot dump first (db/README.md)", file=sys.stderr)
                return 2
            print("1/3 opportunities:", prepare_scoring(conn, force=args.force, **PILOT_SCORING))
            conn.commit()
            print("2/3 clusters:     ", prepare_clusters(conn, Path(args.clusters_path), force=args.force))
            if args.skip_neo4j:
                print("3/3 neo4j:         skipped (--skip-neo4j)")
            else:
                print("3/3 neo4j:        ", prepare_neo4j(conn, force=args.force))
    except psycopg.Error as e:
        print(f"ERROR: PostgreSQL: {(str(e).strip().splitlines() or [''])[0]}", file=sys.stderr)
        return 1
    print("done. Check it with: curl http://127.0.0.1:8000/health")
    return 0


if __name__ == "__main__":
    sys.exit(main())
