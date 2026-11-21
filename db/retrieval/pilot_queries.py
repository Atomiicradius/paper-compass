"""Read-only sanity run of the search layer on the pilot database (a testing aid, not part of any API).

Run from db/ with the embeddings environment:
  embeddings/.venv/Scripts/python.exe -m retrieval.pilot_queries --dbname pc_pilot

For each query it prints the top 5 vector results (title, year, similarity), the median time of 5 runs after one
warm-up (database call only; encoding the query is timed separately), the top 5 keyword results, and how many of
the 5 are shared. Then it shows EXPLAIN ANALYZE of one year-filtered vector query. Nothing is written to the
database. The query text is encoded with the adhoc_query adapter by default;
--query-adapter proximity encodes it like a paper (the old behaviour).
"""
import argparse
import re
import statistics
import sys
import time

from .cli import connect
from .search import _filters, keyword_search, search

QUERIES = [
    "low-resource neural machine translation",
    "back-translation for low-resource languages",
    "multilingual pretraining for translation",
    "zero-shot translation",
    "unsupervised machine translation",
    "quality estimation for machine translation",
    "adam optimizer",
    "speech translation",
]


def median_ms(function, runs=5):
    function()  # warm-up, not counted
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        function()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def explain_filtered(conn, vector, year_min, top_k=5):
    """EXPLAIN ANALYZE of the vector query with a year filter, under the same session settings search() applies."""
    clauses, params = _filters(year_min, None, None, None, None, None, None, "same_experiment")
    sql = ("SELECT p.paper_id, p.title, p.year, p.embedding <=> %s::vector AS distance\n"
           "FROM paper p LEFT JOIN venue v ON v.venue_id = p.venue_id\n"
           "WHERE " + " AND ".join(["p.embedding IS NOT NULL"] + clauses) + "\nORDER BY distance LIMIT %s")
    literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
    with conn.transaction():
        conn.execute("SELECT set_config('hnsw.ef_search', '100', true), set_config('hnsw.iterative_scan', 'strict_order', true)")
        setting = conn.execute("SHOW hnsw.iterative_scan").fetchone()[0]
        plan = [r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, [literal] + params + [top_k])]
        rows = conn.execute(sql, [literal] + params + [top_k]).fetchall()
    return setting, plan, rows


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dbname", required=True)
    parser.add_argument("--query-adapter", choices=("adhoc_query", "proximity"),
                        help="adapter for the query text (default: PC_QUERY_ADAPTER, else adhoc_query; proximity = the old behaviour)")
    parser.add_argument("--year-min", type=int, default=2020, help="year filter for the EXPLAIN ANALYZE query")
    args = parser.parse_args(argv)

    from embeddings.encoder import make_query_encoder
    encoder = make_query_encoder(args.query_adapter)
    encoder.embed(["warm up"])  # load the model once, outside the timings

    with connect(args.dbname) as conn:
        print(f"query encoder: {encoder.model_string}")
        print(f"papers with an embedding: {conn.execute('SELECT count(*) FROM paper WHERE embedding IS NOT NULL').fetchone()[0]}")
        print(f"embedding_model values: {[r[0] for r in conn.execute('SELECT DISTINCT embedding_model FROM paper')]}\n")
        for query in QUERIES:
            start = time.perf_counter()
            vector = encoder.embed([query])[0]
            encode_ms = (time.perf_counter() - start) * 1000
            vec_ms = median_ms(lambda: search(conn, vector, top_k=5))
            kw_ms = median_ms(lambda: keyword_search(conn, query, top_k=5))
            vec, kw = search(conn, vector, top_k=5), keyword_search(conn, query, top_k=5)
            shared = {r["paper_id"] for r in vec} & {r["paper_id"] for r in kw}
            print(f"## {query}")
            print(f"vector search: median {vec_ms:.1f} ms (query encoding {encode_ms:.0f} ms); keyword search: median {kw_ms:.1f} ms")
            for rank, r in enumerate(vec, start=1):
                print(f"  V{rank} {r['similarity']:.3f}  {r['year']}  {r['title'][:95]}  [{r['paper_id']}]"
                      + ("  *also in keyword top 5*" if r["paper_id"] in shared else ""))
            for rank, r in enumerate(kw, start=1):
                print(f"  K{rank} {r['score']:.3f}  {r['year']}  {r['title'][:95]}  [{r['paper_id']}]")
            print(f"  shared in top 5: {len(shared)} of 5 (keyword returned {len(kw)})\n")

        query = QUERIES[0]
        vector = encoder.embed([query])[0]
        setting, plan, rows = explain_filtered(conn, vector, args.year_min)
        print(f"## EXPLAIN ANALYZE: '{query}', year >= {args.year_min}, top 5")
        print(f"hnsw.iterative_scan in this session: {setting}")
        for line in plan:  # the 768-number query vector is hidden so the plan stays readable
            print("  " + re.sub(r"'\[[^\]]*\]'::vector", "'[... 768 numbers ...]'::vector", line))
        print(f"rows returned: {len(rows)}")
        print("indexes on paper:", [r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'paper'")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
