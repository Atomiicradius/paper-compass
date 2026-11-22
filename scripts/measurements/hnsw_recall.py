"""HNSW recall@10 against an exact scan, and index vs exact latency, on pc_demo_opps (read only).

  python scripts/measurements/hnsw_recall.py            (the api-venv interpreter)

Method (also written up in docs/measurements.md):
  * 200 papers sampled at random with random.Random(42) from the papers that have an embedding; each paper's own stored
    embedding is the query vector.
  * "index" = the SELECT that db.retrieval.search.search(...) runs (the function the API calls): top_k=10, the query paper
    excluded with exclude_ids, hnsw.iterative_scan = strict_order. Three index configurations are measured:
      A. hnsw.ef_search = server default (read with SHOW), the planner decides the plan;
      B. the same ef_search, but the HNSW index is FORCED (SET LOCAL enable_seqscan = off). A exists because the planner
         does not use the HNSW index at the default ef_search on this small table (the plan check below proves what it
         does), so A alone would measure a sequential scan, not HNSW;
      C. hnsw.ef_search = 100 (what search() uses when the API does not pass a value), the planner decides.
  * "exact" = the same SELECT with SET LOCAL enable_indexscan = off: a sequential scan and a sort.
  * Every EXPLAIN (ANALYZE, FORMAT JSON) pass records, per query, whether the plan used the HNSW index, and the
    summary counts them. The plans printed in the result file have the 768-number vector literal elided.
  * recall@10 = |index top-10 ∩ exact top-10| / 10, per query.
  * latency: Python wall clock around the whole call (transaction, set_config, query, fetch), and the database's own
    "Execution Time" from EXPLAIN (ANALYZE). The database time is measured in a separate pass over the same queries.
    The first 10 queries of every pass are discarded as warm-up.
"""

from __future__ import annotations

import random
import re
import time

from common import DATABASE, SEED, machine, median, percentile, pg_connect, save

N_QUERIES = 200
TOP_K = 10
WARMUP = 10
VECTOR_LITERAL = re.compile(r"'\[[^\]]*\]'::vector")


def build_sql(pid: str):
    """The SELECT that search() runs (same text, same filter clauses), for one query paper."""
    from db.retrieval.search import _filters

    clauses, fparams = _filters(None, None, None, None, None, None, [pid], "same_experiment")
    sql = ("SELECT p.paper_id, p.title, p.year, v.name, p.embedding <=> %b::real[]::vector AS distance"
           "\nFROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id"
           "\nWHERE " + " AND ".join(["p.embedding IS NOT NULL"] + clauses)
           + "\nORDER BY distance LIMIT %s OFFSET %s")
    return sql, fparams


def uses_index(plan_node: dict, index_name: str) -> bool:
    if plan_node.get("Index Name") == index_name:
        return True
    return any(uses_index(child, index_name) for child in plan_node.get("Plans", []))


def run_sql(conn, pid, vector, ef_search, mode, explain=None, index_name=None):
    """One query in its own transaction. mode: "planner" | "forced_index" | "exact".
    explain: None (rows), "plan" (EXPLAIN text) or "analyze" (-> (execution ms, used the HNSW index))."""
    from db.retrieval.search import vector_parameter

    sql, fp = build_sql(pid)
    full = [vector_parameter(vector)] + fp + [TOP_K, 0]
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("SELECT set_config('hnsw.ef_search', %s, true), set_config('hnsw.iterative_scan', 'strict_order', true)", (str(ef_search),))
        if mode == "exact":
            cur.execute("SET LOCAL enable_indexscan = off")
        elif mode == "forced_index":
            cur.execute("SET LOCAL enable_seqscan = off")
        if explain == "plan":
            cur.execute("EXPLAIN " + sql, full)
            return VECTOR_LITERAL.sub("'[...768 numbers...]'::vector", "\n".join(r[0] for r in cur.fetchall()))
        if explain == "analyze":
            cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, full)
            plan = cur.fetchone()[0][0]
            return plan["Execution Time"], uses_index(plan["Plan"], index_name)
        cur.execute(sql, full)
        return cur.fetchall()


def stats(values: list[float]) -> dict:
    return {"median": median(values), "p95": percentile(values, 95), "min": min(values), "max": max(values), "n": len(values)}


def main() -> None:
    from db.retrieval.search import search

    conn = pg_connect()
    cur = conn.cursor()
    out: dict = {"database": DATABASE, "seed": SEED, "n_queries": N_QUERIES, "top_k": TOP_K}

    # --- what the database says about itself (nothing assumed) ---------------------------------------------------
    out["postgres"] = cur.execute("SELECT version()").fetchone()[0]
    out["pgvector"] = cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    out["papers"], out["papers_with_embedding"] = cur.execute("SELECT count(*), count(embedding) FROM paper").fetchone()
    idx = cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'paper' AND indexdef ILIKE '%hnsw%'").fetchall()
    out["hnsw_indexes"] = [{"name": n, "definition": d} for n, d in idx]
    name = idx[0][0]
    out["hnsw_reloptions"] = cur.execute("SELECT reloptions FROM pg_class WHERE relname = %s", (name,)).fetchone()[0]
    out["hnsw_index_size_bytes"] = cur.execute("SELECT pg_relation_size(%s::regclass)", (name,)).fetchone()[0]
    out["table_size_bytes"] = cur.execute("SELECT pg_table_size('paper')").fetchone()[0]
    # m and ef_construction are stored in reloptions only when the index was built WITH (...); NULL means pgvector's defaults
    meta = cur.execute("SELECT current_setting('hnsw.ef_search'), current_setting('hnsw.iterative_scan'), current_setting('hnsw.max_scan_tuples')").fetchone()
    out["server_defaults"] = {"hnsw.ef_search": meta[0], "hnsw.iterative_scan": meta[1], "hnsw.max_scan_tuples": meta[2]}
    default_ef = int(meta[0])
    out["shared_buffers"] = cur.execute("SHOW shared_buffers").fetchone()[0]
    out["machine"] = machine()
    print("index:", out["hnsw_indexes"], "| reloptions:", out["hnsw_reloptions"], "| defaults:", out["server_defaults"])

    # --- the sample -------------------------------------------------------------------------------------------------
    ids = [r[0] for r in cur.execute("SELECT paper_id FROM paper WHERE embedding IS NOT NULL ORDER BY paper_id")]
    sample = random.Random(SEED).sample(ids, N_QUERIES)
    vectors = {pid: [float(x) for x in cur.execute("SELECT embedding::real[] FROM paper WHERE paper_id = %s", (pid,)).fetchone()[0]] for pid in sample}
    out["sample_first_ids"] = sample[:5]

    # --- the three index configurations and the exact scan ----------------------------------------------------------
    configs = [
        {"key": "A_default_ef_planner", "label": f"ef_search = {default_ef} (server default), planner's choice", "ef": default_ef, "mode": "planner"},
        {"key": "B_default_ef_forced_index", "label": f"ef_search = {default_ef} (server default), HNSW index forced (enable_seqscan = off)", "ef": default_ef, "mode": "forced_index"},
        {"key": "C_ef100_planner", "label": "ef_search = 100 (the value search() uses), planner's choice", "ef": 100, "mode": "planner"},
    ]

    # EXPLAIN: show which plan each mode really gets (first query)
    plans = {c["key"]: run_sql(conn, sample[0], vectors[sample[0]], c["ef"], c["mode"], explain="plan") for c in configs}
    plans["exact"] = run_sql(conn, sample[0], vectors[sample[0]], 100, "exact", explain="plan")
    out["explain_first_query"] = plans
    for k, p in plans.items():
        kind = "HNSW index scan" if name in p else ("Seq Scan on paper" if "Seq Scan on paper" in p else "other")
        print(f"EXPLAIN {k}: {kind}")
    assert name not in plans["exact"] and "Seq Scan on paper" in plans["exact"], "the exact mode must bypass the index"
    assert name in plans["B_default_ef_forced_index"], "the forced mode must use the index"

    exact_rows = {pid: run_sql(conn, pid, vectors[pid], 100, "exact") for pid in sample}
    exact = {pid: ([r[0] for r in rows], [float(r[4]) for r in rows]) for pid, rows in exact_rows.items()}
    out["queries_with_equal_distances_inside_the_exact_top10"] = sum(1 for pid in sample if len(set(round(d, 12) for d in exact[pid][1])) < TOP_K)

    results = {}
    for c in configs:
        def one(pid):
            if c["mode"] == "planner":  # the real function the API calls
                return [r["paper_id"] for r in search(conn, vectors[pid], top_k=TOP_K, exclude_ids=[pid], ef_search=c["ef"])]
            return [r[0] for r in run_sql(conn, pid, vectors[pid], c["ef"], c["mode"])]

        for pid in sample[:WARMUP]:
            one(pid)
        recalls, times, short = [], [], 0
        for pid in sample:
            t0 = time.perf_counter()
            got = one(pid)
            times.append((time.perf_counter() - t0) * 1000)
            short += len(got) < TOP_K
            recalls.append(len(set(got) & set(exact[pid][0])) / TOP_K)
        # the replicated SELECT must give the same answer as search() (EXPLAIN ANALYZE is run on the replica)
        differs = 0
        if c["mode"] == "planner":
            for pid in sample[:20]:
                same = [r[0] for r in run_sql(conn, pid, vectors[pid], c["ef"], "planner")]
                differs += same != [r["paper_id"] for r in search(conn, vectors[pid], top_k=TOP_K, exclude_ids=[pid], ef_search=c["ef"])]
        # database time and plan type, from EXPLAIN (ANALYZE), separate pass
        for pid in sample[:WARMUP]:
            run_sql(conn, pid, vectors[pid], c["ef"], c["mode"], explain="analyze", index_name=name)
        analyzed = [run_sql(conn, pid, vectors[pid], c["ef"], c["mode"], explain="analyze", index_name=name) for pid in sample]
        results[c["key"]] = {
            "label": c["label"], "ef_search": c["ef"], "mode": c["mode"],
            "recall_mean": sum(recalls) / len(recalls), "recall_min": min(recalls),
            "queries_below_1.0": sum(r < 1.0 for r in recalls),
            "queries_below_1.0_detail": {pid: rc for pid, rc in zip(sample, recalls) if rc < 1.0},
            "recall_histogram": {str(r): recalls.count(r) for r in sorted(set(recalls))},
            "queries_returning_fewer_than_10": short,
            "queries_whose_plan_used_the_hnsw_index": sum(1 for _, used in analyzed if used),
            "python_ms": stats(times), "db_ms": stats([t for t, _ in analyzed]),
            "replica_sql_differs_from_search_function": differs,
        }
        r = results[c["key"]]
        print(f"{c['label']}: recall mean {r['recall_mean']:.4f}, min {r['recall_min']}, below 1.0: {r['queries_below_1.0']}/{N_QUERIES}; "
              f"plan used HNSW in {r['queries_whose_plan_used_the_hnsw_index']}/{N_QUERIES}; python median/p95 {r['python_ms']['median']:.2f}/{r['python_ms']['p95']:.2f} ms; "
              f"db median/p95 {r['db_ms']['median']:.2f}/{r['db_ms']['p95']:.2f} ms")
    out["index"] = results

    # --- exact latency ----------------------------------------------------------------------------------------------
    for pid in sample[:WARMUP]:
        run_sql(conn, pid, vectors[pid], 100, "exact")
    times = []
    for pid in sample:
        t0 = time.perf_counter()
        run_sql(conn, pid, vectors[pid], 100, "exact")
        times.append((time.perf_counter() - t0) * 1000)
    for pid in sample[:WARMUP]:
        run_sql(conn, pid, vectors[pid], 100, "exact", explain="analyze", index_name=name)
    analyzed = [run_sql(conn, pid, vectors[pid], 100, "exact", explain="analyze", index_name=name) for pid in sample]
    out["exact"] = {"python_ms": stats(times), "db_ms": stats([t for t, _ in analyzed]), "queries_whose_plan_used_the_hnsw_index": sum(1 for _, used in analyzed if used)}
    e = out["exact"]
    print(f"exact: python median/p95 {e['python_ms']['median']:.2f}/{e['python_ms']['p95']:.2f} ms; db median/p95 {e['db_ms']['median']:.2f}/{e['db_ms']['p95']:.2f} ms; plan used HNSW in {e['queries_whose_plan_used_the_hnsw_index']}/{N_QUERIES}")
    out["latency_method"] = "nearest-rank percentile; python = perf_counter around the call incl. transaction + set_config + fetch; db = EXPLAIN (ANALYZE) Execution Time; first 10 queries of each pass discarded as warm-up; everything is warm (the data fits in shared_buffers)"
    print("saved", save("hnsw_recall.json", out))


if __name__ == "__main__":
    main()
