"""Recursive CTE (Postgres) against Cypher (Neo4j) for 1-hop and 2-hop citation neighbourhoods (read only).

  python scripts/measurements/graph_hops.py            (the api-venv interpreter)

The queries are the repo's own, from graph/queries.py (nothing invented):
  * Cypher: MULTI_HOP_CITATIONS  -> MATCH path = (p:Paper {paper_id: $id})-[:CITES*1..N]->(q:Paper) WHERE q <> p
                                    RETURN q.paper_id, min(length(path)) AS hops
  * SQL:    MULTI_HOP_CITATIONS_SQL -> WITH RECURSIVE reach(...) over the `citation` table, same result columns.
The Graph screen / graph API itself runs PAPER_NEIGHBORHOOD (one hop, all relationship types, Cypher only; it has no SQL
twin). It is timed too, on the same papers, as a reference, but it is not part of the CTE comparison.

Method: 30 papers sampled with random.Random(42) from the papers that have at least one OUTGOING citation (the query
follows CITES outwards). For each paper and each depth (1, 2): first check that both engines return the same papers and
the same hop numbers; then 3 warm-up runs (discarded) and 10 timed runs per engine. Latency = Python wall clock around
execute + fetch of every row. Server-side time is recorded too: Cypher result_available_after + result_consumed_after,
and EXPLAIN (ANALYZE) "Execution Time" for the CTE (one extra pass).
"""

from __future__ import annotations

import random
import time

from common import DATABASE, SEED, machine, median, percentile, neo4j_driver, pg_connect, save

N_PAPERS = 30
DEPTHS = (1, 2)
WARMUP = 3
REPEATS = 10


def main() -> None:
    from graph.queries import (MULTI_HOP_CITATIONS, MULTI_HOP_CITATIONS_SQL, PAPER_NEIGHBORHOOD, multi_hop_citations,
                               multi_hop_citations_sql)

    pg = pg_connect()
    cur = pg.cursor()
    driver = neo4j_driver()
    out: dict = {"database": DATABASE, "seed": SEED, "n_papers": N_PAPERS, "depths": list(DEPTHS), "warmup_runs": WARMUP, "timed_runs": REPEATS}
    out["machine"] = machine()

    # --- is the graph a copy of the same data? -----------------------------------------------------------------------
    pg_papers = cur.execute("SELECT count(*) FROM paper").fetchone()[0]
    pg_edges = cur.execute("SELECT count(*) FROM citation").fetchone()[0]
    pg_with_out = cur.execute("SELECT count(DISTINCT citing_paper_id) FROM citation").fetchone()[0]
    pg_with_any = cur.execute("SELECT count(*) FROM (SELECT citing_paper_id FROM citation UNION SELECT cited_paper_id FROM citation) t").fetchone()[0]
    with driver.session() as s:
        n4_papers = s.run("MATCH (p:Paper) RETURN count(p) AS n").single()["n"]
        n4_edges = s.run("MATCH (:Paper)-[r:CITES]->(:Paper) RETURN count(r) AS n").single()["n"]
        n4_edge_set = {(r["a"], r["b"]) for r in s.run("MATCH (a:Paper)-[:CITES]->(b:Paper) RETURN a.paper_id AS a, b.paper_id AS b")}
        version = s.run("CALL dbms.components() YIELD name, versions RETURN name, versions").single()
    pg_edge_set = set(cur.execute("SELECT citing_paper_id, cited_paper_id FROM citation").fetchall())
    out["copy_check"] = {"postgres": {"papers": pg_papers, "citation_rows": pg_edges, "papers_with_an_outgoing_citation": pg_with_out, "papers_with_any_citation_edge": pg_with_any},
                         "neo4j": {"papers": n4_papers, "cites_relationships": n4_edges, "version": f"{version['name']} {version['versions'][0]}"},
                         "same_edge_set": pg_edge_set == n4_edge_set, "edges_only_in_postgres": len(pg_edge_set - n4_edge_set), "edges_only_in_neo4j": len(n4_edge_set - pg_edge_set)}
    print("copy check:", out["copy_check"])

    # --- the sample -------------------------------------------------------------------------------------------------
    candidates = [r[0] for r in cur.execute("SELECT DISTINCT citing_paper_id FROM citation ORDER BY 1")]
    sample = random.Random(SEED).sample(candidates, N_PAPERS)
    out["sample"] = sample

    # --- same answer? -------------------------------------------------------------------------------------------------
    mismatches, sizes = [], {d: [] for d in DEPTHS}
    with driver.session() as s:
        for pid in sample:
            for d in DEPTHS:
                sql_rows = multi_hop_citations_sql(pg, pid, d)
                cy_rows = multi_hop_citations(s, pid, d)
                a = {r["paper_id"]: r["hops"] for r in sql_rows}
                b = {r["paper_id"]: r["hops"] for r in cy_rows}
                sizes[d].append(len(a))
                if a != b:
                    mismatches.append({"paper_id": pid, "depth": d, "sql_papers": len(a), "cypher_papers": len(b),
                                       "only_in_sql": sorted(set(a) - set(b))[:5], "only_in_cypher": sorted(set(b) - set(a))[:5],
                                       "different_hops": sum(1 for k in set(a) & set(b) if a[k] != b[k])})
    out["result_sizes"] = {str(d): {"median": median(v), "min": min(v), "max": max(v), "total": sum(v)} for d, v in sizes.items()}
    out["mismatches"] = mismatches
    print(f"same papers and same hop numbers in {N_PAPERS * len(DEPTHS) - len(mismatches)}/{N_PAPERS * len(DEPTHS)} (paper, depth) cases; mismatches: {len(mismatches)}")
    for m in mismatches:
        print("  MISMATCH", m)

    # --- timing -------------------------------------------------------------------------------------------------------
    def timed_sql(pid, d):
        t0 = time.perf_counter()
        multi_hop_citations_sql(pg, pid, d)
        return (time.perf_counter() - t0) * 1000

    def timed_cypher(session, pid, d):
        t0 = time.perf_counter()
        result = session.run(MULTI_HOP_CITATIONS % d, paper_id=pid)
        list(result)
        summary = result.consume()
        wall = (time.perf_counter() - t0) * 1000
        return wall, summary.result_available_after + summary.result_consumed_after

    def sql_exec_ms(pid, d):
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + MULTI_HOP_CITATIONS_SQL, {"paper_id": pid, "max_hops": d})
        return cur.fetchone()[0][0]["Execution Time"]

    res = {}
    with driver.session() as s:
        for d in DEPTHS:
            sql_wall, cy_wall, cy_server, sql_server = [], [], [], []
            for pid in sample:
                for _ in range(WARMUP):  # discarded
                    timed_sql(pid, d)
                    timed_cypher(s, pid, d)
                    sql_exec_ms(pid, d)
                for _ in range(REPEATS):
                    sql_wall.append(timed_sql(pid, d))
                    w, srv = timed_cypher(s, pid, d)
                    cy_wall.append(w)
                    cy_server.append(srv)
                    sql_server.append(sql_exec_ms(pid, d))
            f = lambda v: {"median": median(v), "p95": percentile(v, 95), "min": min(v), "max": max(v), "n": len(v)}
            res[str(d)] = {"postgres_cte_python_ms": f(sql_wall), "postgres_cte_server_ms": f(sql_server),
                           "neo4j_cypher_python_ms": f(cy_wall), "neo4j_cypher_server_ms": f(cy_server)}
            r = res[str(d)]
            print(f"{d}-hop  CTE python median/p95 {r['postgres_cte_python_ms']['median']:.2f}/{r['postgres_cte_python_ms']['p95']:.2f} ms (server {r['postgres_cte_server_ms']['median']:.2f}/{r['postgres_cte_server_ms']['p95']:.2f}) | "
                  f"Cypher python median/p95 {r['neo4j_cypher_python_ms']['median']:.2f}/{r['neo4j_cypher_python_ms']['p95']:.2f} ms (server {r['neo4j_cypher_server_ms']['median']:.2f}/{r['neo4j_cypher_server_ms']['p95']:.2f})")
        # the Graph screen's own query (Cypher only, one hop, all relationship types), same 30 papers, limit 200 as the API
        ref = []
        for pid in sample:
            for _ in range(WARMUP):
                s.run(PAPER_NEIGHBORHOOD, paper_id=pid, limit=200).single()
            for _ in range(REPEATS):
                t0 = time.perf_counter()
                s.run(PAPER_NEIGHBORHOOD, paper_id=pid, limit=200).single()
                ref.append((time.perf_counter() - t0) * 1000)
        res["graph_screen_paper_neighborhood_cypher_python_ms"] = {"median": median(ref), "p95": percentile(ref, 95), "min": min(ref), "max": max(ref), "n": len(ref)}
        print("Graph-screen query (PAPER_NEIGHBORHOOD, Cypher):", res["graph_screen_paper_neighborhood_cypher_python_ms"])
    out["latency"] = res
    out["latency_method"] = "nearest-rank percentile over all (paper x run) samples; 3 warm-up runs per paper/depth/engine discarded; python = perf_counter around execute + fetch of all rows; server = Cypher result_available_after + result_consumed_after, CTE = EXPLAIN (ANALYZE) Execution Time"
    print("saved", save("graph_hops.json", out))
    driver.close()


if __name__ == "__main__":
    main()
