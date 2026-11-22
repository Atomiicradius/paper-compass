# graph/ (Person 3)

Neo4j projection of PostgreSQL, plus landscape analysis (clusters, bridges, trends).

| File | What it does |
|---|---|
| `constraints.cypher` | Uniqueness constraint on every node ID (applied automatically by the sync) |
| `model.py` | PostgreSQL → Neo4j mapping for nodes and relationships, including the derived Paper shortcut edges |
| `sync.py` | Idempotent batch sync: `MERGE` only, mark-and-sweep removes rows deleted in PostgreSQL, then runs verification |
| `verify.py` | Compares node and relationship counts per label/type; exits non-zero on mismatch |
| `queries.py` | Cypher for the graph screen, method bridges, multi-hop citations, plus the recursive-CTE equivalent for the benchmark |
| `trends.py` | Yearly distinct-paper counts per method/dataset/task/topic; emerging/declining labels |
| `clusters.py` | HDBSCAN on embeddings (O8 default); writes `graph/out/clusters.json` (there is no cluster table in the schema) |
| `bridges.py` | Bridge papers between clusters; cluster pairs that are semantically close but rarely cite each other |

```bash
python -m graph.sync     --pg-dsn $PG --neo4j-uri bolt://localhost:7687 --neo4j-password ...
python -m graph.verify   --pg-dsn $PG --neo4j-uri bolt://localhost:7687 --neo4j-password ...
python -m graph.clusters --pg-dsn $PG --embedding-model <model name> --pca-dims 20 --min-cluster-size 15 --min-samples 5
```

Clustering settings for pc_pilot (O8, 2026-11-22). HDBSCAN directly on the 768-dim SPECTER2 vectors found only
2-5 clusters with 46-80% of papers as noise, so the unit vectors are first reduced to 20 PCA dimensions
(`random_state=0`). Grid on pc_pilot (noise %, mean cosine silhouette of clustered papers):

| setting | clusters | noise | silhouette | largest cluster |
|---|---:|---:|---:|---:|
| 768-dim, mcs 15 (old default) | 2 | 55.4% | 0.41 | 42.7% |
| PCA 50, mcs 15, ms 5 | 11 | 58.2% | 0.26 | 16.7% |
| **PCA 20, mcs 15, ms 5 (chosen)** | **7** | **44.2%** | **0.24** | **21.0%** |
| PCA 10, mcs 10, ms 5 | 7 | 41.2% | 0.23 | 21.2% |

Chosen for the lowest noise without a giant cluster. The corpus is mostly about one subject (MT), so a lot of
noise is expected. The defaults of `cluster_embeddings` are unchanged (no PCA).

pc_pilot sync (2026-11-22): 12,864 nodes and 34,796 relationships; all 26 label/type counts match PostgreSQL,
and a second run leaves the counts unchanged.

The sync's sweep step deletes graph nodes that are no longer in PostgreSQL. Point it only at the project's Neo4j, never at a shared instance holding other data.
