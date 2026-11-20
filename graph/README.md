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
python -m graph.clusters --pg-dsn $PG --embedding-model <model name>
```

The sync's sweep step deletes graph nodes that are no longer in PostgreSQL. Point it only at the project's Neo4j, never at a shared instance holding other data.
