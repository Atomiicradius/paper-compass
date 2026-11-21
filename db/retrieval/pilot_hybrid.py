"""Read-only look at vector, keyword and hybrid search on the pilot database (a testing aid, not an evaluation).

Run from db/ with the embeddings environment:
  embeddings/.venv/Scripts/python.exe -m retrieval.pilot_hybrid --dbname pc_pilot

For each query it prints the top 5 titles of vector, keyword and hybrid (RRF, k=60, 50 candidates per list) and
the latency of each (median of 5 runs after one warm-up; database calls only, the query is encoded once and not
timed). For the three back-translation / quality-estimation queries it also counts how many papers matching a
LEXICAL rule (the phrase in the title or abstract, the rule of db/retrieval-diagnosis.md) are in the top 5 and top
10 of each mode. That rule is made of the same words keyword search matches, so it favours keyword search, and the
counts are not a blind evaluation. The connection is read-only.
"""
import argparse
import re
import statistics
import sys
import time

import psycopg

from .cli import connection_params
from .search import keyword_search, search, search_hybrid

QUERIES = [
    "low-resource neural machine translation",
    "back-translation for low-resource languages",
    "multilingual pretraining for translation",
    "zero-shot translation",
    "unsupervised machine translation",
    "quality estimation for machine translation",
    "adam optimizer",
    "speech translation",
    "back-translation",
]
# query -> regex of the lexical relevance rule (title or abstract)
RULES = {
    "back-translation for low-resource languages": "back[- ]?translation",
    "back-translation": "back[- ]?translation",
    "quality estimation for machine translation": "quality[- ]estimation",
}
MODES = ("vector", "keyword", "hybrid")


def median_ms(function, runs=5):
    function()  # warm-up, not counted
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        function()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dbname", required=True)
    args = parser.parse_args(argv)

    from embeddings.encoder import make_query_encoder
    encoder = make_query_encoder()
    encoder.embed(["warm up"])
    conn = psycopg.connect(**connection_params(args.dbname), autocommit=True,
                           options="-c default_transaction_read_only=on")
    print(f"query encoder: {encoder.model_string}")
    print(f"papers with an embedding: {conn.execute('SELECT count(*) FROM paper WHERE embedding IS NOT NULL').fetchone()[0]}\n")
    counts = []
    for query in QUERIES:
        vector = encoder.embed([query])[0]
        runs = {"vector": lambda: search(conn, vector, top_k=10),
                "keyword": lambda: keyword_search(conn, query, top_k=10),
                "hybrid": lambda: search_hybrid(conn, query, vector, top_k=10)}
        results = {mode: runs[mode]() for mode in MODES}
        latency = {mode: median_ms(runs[mode]) for mode in MODES}
        print(f"## {query}")
        print("latency (median of 5 after a warm-up, ms): " + ", ".join(f"{m} {latency[m]:.1f}" for m in MODES))
        for mode in MODES:
            for rank, r in enumerate(results[mode][:5], start=1):
                extra = ""
                if mode == "hybrid":
                    extra = f"  [vector rank {r['vector_rank'] or '-'}, keyword rank {r['keyword_rank'] or '-'}]"
                print(f"  {mode[0].upper()}{rank} {r['year']}  {r['title'][:100]}  [{r['paper_id']}]{extra}")
        if query in RULES:
            relevant = {pid for (pid,) in conn.execute(
                "SELECT paper_id FROM paper WHERE title || ' ' || coalesce(abstract, '') ~* %s", (RULES[query],))}
            row = {mode: tuple(sum(1 for r in results[mode][:n] if r["paper_id"] in relevant) for n in (5, 10))
                   for mode in MODES}
            counts.append((query, len(relevant), row))
            print("  lexical-rule matches in top 5 / top 10: " + "; ".join(f"{m} {row[m][0]}/{row[m][1]}" for m in MODES)
                  + f"  (papers matching the rule: {len(relevant)})")
        print()
    print("## lexical-rule counts (not a blind evaluation; the rule is lexical and favours keyword search)")
    print("| Query | Papers matching the rule | " + " | ".join(f"{m} top 5 | {m} top 10" for m in MODES) + " |")
    print("| --- | ---: | " + " | ".join("---: | ---:" for _ in MODES) + " |")
    for query, total, row in counts:
        print(f"| {query} | {total} | " + " | ".join(f"{row[m][0]} | {row[m][1]}" for m in MODES) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
