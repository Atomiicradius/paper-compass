# Measurements for the report

Two measurements on the `pc_demo_opps` database (1,999 papers): how close the HNSW vector index gets to an exact scan, and how
a recursive CTE on Postgres compares with Cypher on Neo4j for citation neighbourhoods. Everything here comes from the two
scripts in `scripts/measurements/`; the raw output is in `scripts/measurements/results/*.json`. Nothing was written to any
database (every Postgres session is opened with `default_transaction_read_only = on`, Neo4j only ran `MATCH`).

## Headline numbers

| Measurement | Result |
|---|---|
| HNSW recall@10 vs exact scan, `ef_search = 100` (what `search()` uses) | mean **0.9995**, min **0.9**, **1 of 200** queries below 1.0 |
| HNSW recall@10, server default `ef_search = 40`, planner's own choice | 1.0000, but the planner used a **sequential scan** (0 of 200 plans used the index), so this is not a recall of HNSW |
| HNSW recall@10, `ef_search = 40`, index forced | mean **0.9995**, min **0.9**, **1 of 200** below 1.0 (the same query) |
| Vector query, index (`ef_search = 100`) vs exact: median, from Python | **2.48 ms** vs **7.04 ms** (p95 3.18 vs 9.51 ms) |
| Vector query, index vs exact: median, database execution time | **0.50 ms** vs **4.66 ms** (p95 0.74 vs 5.38 ms) |
| 1-hop citations, median, from Python | CTE **0.63 ms**, Cypher **2.40 ms** (p95 0.88 vs 4.05 ms) |
| 2-hop citations, median, from Python | CTE **0.71 ms**, Cypher **2.52 ms** (p95 1.06 vs 4.51 ms) |
| CTE and Cypher return the same papers and hop numbers | 60 of 60 (paper, depth) cases, **0 mismatches** |

In this setup Cypher is **slower** than the recursive CTE, by about 3.5 to 4 times at both depths. See the limitations before
reading anything general into that.

## The machine

| | |
|---|---|
| CPU | 13th Gen Intel Core i7-13650HX (14 cores, 20 logical) |
| RAM | 23.7 GB (Docker Desktop is given 11.5 GB and 20 CPUs) |
| OS | Windows 11 (10.0.26300), Python 3.12.3 |
| Docker | Docker Desktop 29.9.2, WSL2 kernel 6.18.58.1; both databases run in containers on the same machine as the client |
| Postgres | PostgreSQL 16.15 with pgvector 0.8.7, container `pc-postgres`, `shared_buffers = 128MB` |
| Neo4j | Neo4j Kernel 5.26.32 Community, container `pc-neo4j`, default memory settings |
| Client | the `api-venv` interpreter with the embeddings venv's site-packages first on the path (as the API launcher does), psycopg 3.3.6, neo4j driver 5.28.8 |

The client talks to both databases over `127.0.0.1` (Postgres on its published port, Neo4j over Bolt). The machine was
otherwise a normal working laptop (editor and other programs open), not a quiet benchmark host.

## 1. HNSW recall against an exact scan

### Method

- **Index parameters, read from the database.** `pg_indexes` shows
  `CREATE INDEX idx_paper_embedding_hnsw ON public.paper USING hnsw (embedding vector_cosine_ops)` with **no `WITH (...)`
  clause** and `pg_class.reloptions` is `NULL`. So the index was built with pgvector's defaults, which are **m = 16 and
  ef_construction = 64** (pgvector's documented defaults; Postgres does not store them anywhere else, so this is the one value
  that is read as "no override" and not as a number). Index size 8,183,808 bytes; the `paper` table is 11,231,232 bytes.
- **Server settings** (read with `SHOW`): `hnsw.ef_search = 40`, `hnsw.iterative_scan = off`, `hnsw.max_scan_tuples = 20000`.
- **Queries.** 200 papers sampled with `random.Random(42).sample(...)` from the 1,999 papers that have an embedding (all of
  them); each paper's own stored embedding is the query vector. First sampled ids: W3201959471, W2010595692, W1554944419,
  W4323572061, W2140679639.
- **Index side.** The same `SELECT` as `db.retrieval.search.search()` (the function the API calls): top 10, the query paper
  excluded with `exclude_ids`, `hnsw.iterative_scan = strict_order` set for the transaction. For the plain planner configurations
  the function itself is called; the `EXPLAIN ANALYZE` pass runs a copy of its SQL, and the script checks that the copy returns
  the same ids as the function (0 differences).
- **Exact side.** The same `SELECT` with `SET LOCAL enable_indexscan = off`, which forces a sequential scan plus a sort.
- **Proof of the plans.** `EXPLAIN` of the first query for every configuration (stored in the JSON, with the 768-number vector
  literal elided): the exact mode is `Seq Scan on paper` and does not mention the HNSW index; the index modes are
  `Index Scan using idx_paper_embedding_hnsw`, except configuration A (below). Every `EXPLAIN (ANALYZE, FORMAT JSON)` in the
  timing pass also records whether its plan used the HNSW index, and the table shows the counts.
- **Recall** = |index top-10 ∩ exact top-10| / 10 per query; mean, min and the number of queries below 1.0 are reported.
- **Latency.** Python: `perf_counter` around the whole call (transaction, `set_config`, query, fetching the rows). Database:
  the `Execution Time` of `EXPLAIN (ANALYZE)`, in a separate pass over the same 200 queries. The first 10 queries of every pass
  are discarded. Percentiles are nearest-rank (the 190th of 200 sorted values for p95), with no interpolation.

### What the plan check found, and one measurement problem

1. **At the default `ef_search = 40` the planner does not use the HNSW index on this table.** The plan the planner picks changes
   with `ef_search` (observed on the first query: at 40 it chose the sequential scan plus sort, estimated total cost about 439;
   at 100 it chose the index scan, estimated cost about 378 for the limited query). I did not look into pgvector's cost model
   further than that observation. So the "default" run measured an exact scan: its recall of 1.0 says nothing
   about HNSW. To still measure HNSW at the default `ef_search`, configuration B forces the index with
   `SET LOCAL enable_seqscan = off`. Forcing is a measurement device, not something the API does.
2. **Prepared statements mix plans.** psycopg prepares a statement after it has run five times and then re-uses one cached plan.
   In a first version of the script this made later configurations silently re-use the plan of an earlier one (a recall of
   1.0 appeared where the index gives 0.9 for one query, and latencies were wrong). The API opens a new connection for every
   request, so it never re-uses a statement. The measurement connection therefore sets `prepare_threshold = None`. The numbers
   below are from the corrected script (the earlier runs were discarded, not averaged in).

### Results

Recall@10 over 200 queries:

| Configuration | Plan used the HNSW index | Recall mean | Recall min | Queries below 1.0 | Queries with fewer than 10 results |
|---|---|---|---|---|---|
| A: `ef_search = 40` (default), planner's choice | **0 / 200** (sequential scan) | 1.0000 | 1.0 | 0 | 0 |
| B: `ef_search = 40` (default), index forced | 200 / 200 | **0.9995** | 0.9 | **1** | 0 |
| C: `ef_search = 100` (what `search()` uses), planner's choice | 200 / 200 | **0.9995** | 0.9 | **1** | 0 |

The one imperfect query is the same in B and C: paper `W4414051084`, 9 of 10 neighbours found (recall 0.9); the other 199
queries have recall 1.0. Both settings therefore give the same recall on this sample. In 7 of the 200 queries the exact top 10
contains two or more equal distances (duplicate or near-duplicate records), so a different tie order could in principle change
a recall figure; this was not investigated further.

Latency per query, in milliseconds (200 queries each, warm cache):

| Configuration | Python median | Python p95 | Database median | Database p95 |
|---|---|---|---|---|
| A: `ef_search = 40`, planner (sequential scan) | 6.70 | 7.72 | 4.58 | 5.06 |
| B: `ef_search = 40`, index forced | 2.42 | 2.96 | 0.30 | 0.44 |
| C: `ef_search = 100`, planner (index) | 2.48 | 3.18 | 0.50 | 0.74 |
| Exact (`enable_indexscan = off`) | 7.04 | 9.51 | 4.66 | 5.38 |

Min and max of each series are in `results/hnsw_recall.json` (for example the slowest index query from Python was 9.0 ms and
the slowest exact one 15.7 ms). The HNSW index is about 2.8 times faster than the exact scan measured from Python and about
9.4 times faster measured inside the database (median, `ef_search = 100`). The Python figure includes a fixed cost (Python median minus
database median is about 2.0 ms for the index and about 2.4 ms for the exact scan) for the transaction, the two `set_config`
calls, the round trip to the container and sending the 768-number parameter; that cost is why the Python ratio is smaller than
the database ratio.

## 2. Recursive CTE against Cypher

### Which query

The Graph screen and the graph API run `PAPER_NEIGHBORHOOD` from `graph/queries.py`: one hop, every relationship type
(authors, venue, topics, methods, tasks, datasets, citations), Cypher only, no SQL twin. A recursive-CTE comparison needs a
query that exists in both languages, and the repo has exactly one pair, in the same file, written for this comparison:
`MULTI_HOP_CITATIONS` (Cypher) and `MULTI_HOP_CITATIONS_SQL` (recursive CTE over the `citation` table). Both return each paper
reachable over `CITES` edges in 1..N hops together with its shortest hop count. **That pair is what was measured**; no query
was invented. The API does not call this pair today (it is the multi-hop citation benchmark). `PAPER_NEIGHBORHOOD` was also
timed on the same papers as a reference and is reported separately.

```cypher
MATCH path = (p:Paper {paper_id: $paper_id})-[:CITES*1..N]->(q:Paper)
WHERE q <> p
RETURN q.paper_id AS paper_id, min(length(path)) AS hops
ORDER BY hops, paper_id
```

```sql
WITH RECURSIVE reach(paper_id, hops) AS (
    SELECT cited_paper_id, 1 FROM citation WHERE citing_paper_id = %(paper_id)s
    UNION
    SELECT c.cited_paper_id, r.hops + 1
    FROM reach r JOIN citation c ON c.citing_paper_id = r.paper_id
    WHERE r.hops < %(max_hops)s
)
SELECT paper_id, MIN(hops) AS hops FROM reach
WHERE paper_id <> %(paper_id)s
GROUP BY paper_id ORDER BY hops, paper_id
```

### Method

- **The data is a copy.** The Neo4j graph is derived from the Postgres tables. Checked: 1,999 papers in both; 11,542 citation
  rows in Postgres and 11,542 `CITES` relationships in Neo4j, and the two edge sets are identical (0 edges on only one side).
  So this compares query styles on the same edges, not two independent datasets.
- **Sample.** 30 papers with `random.Random(42).sample(...)` from the 1,391 papers that have at least one **outgoing** citation
  (the query follows `CITES` outwards; 1,646 papers have any citation edge, but a paper with only incoming edges would return
  an empty result for both engines). First sampled ids: W4415368442, W2122585011, W1880262756.
- **Equality check first.** For every paper and depth, the two engines must return the same papers *and* the same hop numbers.
- **Warm-up and timing.** For each paper, depth and engine: 3 warm-up runs (discarded), then 10 timed runs, so 300 samples per
  engine and depth. Python time is `perf_counter` around execute plus fetching every row. Server-side time is also recorded:
  Cypher `result_available_after + result_consumed_after` (Neo4j reports whole milliseconds), and `EXPLAIN (ANALYZE)`
  `Execution Time` for the CTE (one extra pass per run).

### Results

Same answer: **60 of 60** (paper, depth) cases identical, **0 mismatches**.

Result sizes (papers returned per query): 1 hop median 5 (min 1, max 26, 223 in total over the 30 papers); 2 hops median 23.5
(min 1, max 163, 1,233 in total).

Latency per query, in milliseconds (300 samples each):

| Depth | Engine | Python median | Python p95 | Server median | Server p95 |
|---|---|---|---|---|---|
| 1 hop | Postgres recursive CTE | **0.63** | 0.88 | 0.054 | 0.082 |
| 1 hop | Neo4j Cypher | **2.40** | 4.05 | 1 | 2 |
| 2 hops | Postgres recursive CTE | **0.71** | 1.06 | 0.104 | 0.357 |
| 2 hops | Neo4j Cypher | **2.52** | 4.51 | 1 | 2 |

Cypher is slower than the CTE here: about 3.8 times at one hop and 3.5 times at two hops (medians from Python). The server-side
Cypher figures are whole milliseconds, so they cannot show differences below 1 ms; the Python column is the one to compare.
Max values: Cypher 19.2 ms (one hop) and 7.6 ms (two hops); CTE 1.5 ms and 1.6 ms.

Reference, not part of the comparison: the Graph screen's own query (`PAPER_NEIGHBORHOOD`, Cypher, limit 200) on the same 30
papers: median 2.23 ms, p95 3.29 ms (300 samples).

## Limitations

- **Small data.** 1,999 papers and 11,542 citation edges. Everything fits in memory, 2-hop results have 24 papers at the
  median, and neither engine is stressed. The HNSW index (8 MB) is small enough that a sequential scan over 1,999 vectors takes
  about 5 ms; the index advantage and the recall would look different at 100,000 or 1,000,000 vectors, and at that size the
  planner would pick the index at the default settings. No conclusion about large graphs can be drawn from these numbers.
- **One machine, not a quiet one.** A Windows laptop with Docker Desktop (WSL2), the client and both databases on the same
  host, other programs open. Docker's network and virtualisation add a fixed cost to every call, and that cost differs between
  the Postgres connection and the Bolt connection, so part of the Cypher-versus-CTE gap may come from the transport and driver
  and not from the query engine. Run-to-run variation was visible (the Python median of the index query moved between about
  2.4 and 2.5 ms over repeated runs, the exact scan between 6.7 and 7.7 ms).
- **Warm cache only.** Every figure is warm: each pass discards warm-up queries and the data fits in `shared_buffers` and in
  Neo4j's page cache. Cold-cache behaviour (first query after a restart) was **not measured**, because that needs restarting
  the containers.
- **Recall depends on the sample and on ties.** 200 queries, each paper used as its own query (which is how the app's "related
  papers" works, but not how a free-text query behaves). One query out of 200 lost a neighbour; with so few misses the mean
  recall is a coarse number, and 7 queries have tied distances in the exact top 10.
- **The default `ef_search` is not a fair test of HNSW here.** At 40 the planner chooses a sequential scan, so the only way to
  measure HNSW at that setting is to force it, which the API never does. Configuration C (`ef_search = 100`) is the one that
  matches the API.
- **Filtered searches were not measured.** The API often adds year or element filters; pgvector applies them after the index
  scan, and recall with filters (where `hnsw.iterative_scan` matters) can be lower. Only the unfiltered top 10 was measured.
- **The CTE and Cypher shapes.** The Cypher query enumerates paths (`[:CITES*1..N]`) and then takes the minimum length per paper;
  the CTE works breadth-first with `UNION` removing duplicate rows. Neither is the only way to write the query (Cypher could use
  `shortestPath` or `DISTINCT` on a node-uniqueness expansion; the CTE could use an array or `CYCLE` clause), and a different
  shape could change the result. Only the repo's own pair was measured. Depths above 2 were not measured, and that is where
  path enumeration and recursive CTEs diverge most.
- **Derived data.** The graph is a copy of the Postgres tables, so this says something about the two query styles on identical
  edges and nothing about which store is the better source of truth.
- **Neo4j timing resolution.** The server-side Cypher time is reported in whole milliseconds.

## Reproducing

From the repository root, with the `pc-postgres` and `pc-neo4j` containers running and `db/.env` filled in (passwords are read
from it and never printed or written to a result file), using the same Python as the API:

```
python scripts/measurements/hnsw_recall.py     # writes results/hnsw_recall.json
python scripts/measurements/graph_hops.py      # writes results/graph_hops.json
```

`PC_MEASURE_DB` (default `pc_demo_opps`) and `PC_EMBEDDINGS_SITE` (the embeddings venv's `site-packages`) can be set if they are
elsewhere. Timings will differ a little on every run; recall should be identical.

## Screenshots for the report

`docs/screenshots/` holds full-window captures of the current UI (1440 x 900 at device pixel ratio 2, so 2880 x 1800 pixels,
dark theme, the API running against `pc_demo_opps`):

| File | Screen |
|---|---|
| `01-story-home.png` | Story (home) |
| `02-candidates-detail-panel.png` | Candidates with the detail panel (opportunity #1, closest existing work loaded) |
| `03-papers-hybrid-search.png` | Papers, hybrid search ("back-translation for low-resource languages") |
| `04-papers-paper-drawer.png` | Papers: the drawer with the details of the first result |
| `04b-candidates-evidence-drawer.png` | Candidates: the evidence drawer ("Evidence & explanation") |
| `05-graph.png` | Graph for W4388691873 |
| `06-landscape.png` | Landscape |
