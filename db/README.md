# db/

Local PostgreSQL (with pgvector) and Neo4j for Paper Compass, plus the loaders that fill PostgreSQL.
The schema is `init.sql`, copied verbatim from section 1 of `context/data-and-contracts.md`.

All commands below are PowerShell, run from this folder (`db/`) unless noted.

## Start the databases

```powershell
Copy-Item .env.example .env      # then edit .env and set real passwords
docker compose up --build
```

- Postgres is built from `Dockerfile`: `postgres:16` pinned by digest (PostgreSQL 16.15) plus the apt package `postgresql-16-pgvector` pinned to one version, so everyone gets the same image. Add `-d` to run in the background.
- `init.sql` runs automatically the first time the Postgres volume is created.
- `.env` is ignored by git. Only `.env.example` (placeholders) is committed.

## Connect

Credentials and host ports live in `db/.env` (copy of `.env.example`). If a port variable is missing, the default below is used.

| Service | Default address | Credentials in `.env` | Port variable |
|---|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `POSTGRES_PORT` |
| Neo4j Browser | http://127.0.0.1:7474 | `NEO4J_USER`, `NEO4J_PASSWORD` | `NEO4J_HTTP_PORT` |
| Neo4j Bolt | `bolt://127.0.0.1:7687` | same as above | `NEO4J_BOLT_PORT` |

The port variables change only the port on your machine; inside the containers the ports stay 5432, 7474 and 7687. The loaders, the embedding and search commands and the tests all read `POSTGRES_PORT` (and `POSTGRES_HOST`, default `127.0.0.1`) from `.env` or the environment, so after changing the port nothing else needs editing. Restart the containers with `docker compose up -d` for a port change to take effect.

psql, without installing anything (inside the container):

```powershell
docker exec -it pc-postgres psql -U paper_compass -d paper_compass
```

psql installed on your machine:

```powershell
psql -h 127.0.0.1 -p 5432 -U paper_compass -d paper_compass
```

(Use the user, database and port from your `.env`; the password is prompted for.) Always use `127.0.0.1`, not `localhost`.

**Troubleshooting: "password authentication failed" although the container is running.** This usually means another PostgreSQL (for example a Windows service) owns port 5432, so your connection reaches it instead of the container. Check with `netstat -ano | findstr :5432`, then set `POSTGRES_PORT=55432` in `db/.env` and re-run `docker compose up -d`.

Neo4j is only a running container here. The graph model and sync belong to the graph module.

## Python environment (loaders and tests)

One virtual environment at the repository root, with pinned versions:

```powershell
# from the repository root, once
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r db/requirements.txt
```

## Load data

Run from `db/`. Load in dependency order: vocabulary, then papers, then extractions.

```powershell
..\.venv\Scripts\python.exe -m loaders load-vocabulary mock/vocabulary.jsonl
..\.venv\Scripts\python.exe -m loaders load-papers mock/papers.jsonl
..\.venv\Scripts\python.exe -m loaders load-extractions mock/extractions.jsonl
..\.venv\Scripts\python.exe -m loaders refresh-views
```

Or everything at once, refreshing the materialized views at the end:

```powershell
..\.venv\Scripts\python.exe -m loaders load-all --vocabulary mock/vocabulary.jsonl --papers mock/papers.jsonl --extractions mock/extractions.jsonl --refresh
```

| Command | What it does |
|---|---|
| `load-vocabulary FILE` | methods, datasets, tasks, settings and their aliases (settings have no aliases) |
| `load-papers FILE` | papers, venues, institutions, authors, citations |
| `load-extractions FILE` | experiments; rows outside the vocabulary or without a paper are rejected |
| `refresh-views` | `REFRESH MATERIALIZED VIEW CONCURRENTLY` on all 12 views |
| `load-all` | the three loads in order |

Every load command accepts `--refresh` (refresh the views afterwards). Every command accepts `--dbname NAME` (use another database instead of `POSTGRES_DB`) and `--reject-dir DIR`.

How the loaders behave:
- Connection settings come from `db/.env` (or environment variables of the same name). Nothing is hardcoded.
- **One transaction per input file.** If the database reports an error, that file is rolled back completely.
- **Idempotent.** Running a load twice changes nothing; the second run reports everything as skipped.
- **Nothing is invented.** A value outside the vocabulary (or a missing `paper_id`) is not inserted. The row is written to `db/rejects/<kind>-<timestamp>.jsonl` with the original row and a reason. A file is only written when something was rejected. Rejects are ignored by git; delete old ones by hand.
- Names and aliases match ignoring case and extra whitespace.
- Authors are matched by `external_id`, or by normalized name when there is none. If the institution differs, the first one is kept and a warning is printed. Citations to papers that are not in the database are skipped and counted; no stub papers are created.
- Embedding columns are left NULL.
- Each command prints a summary: rows read, inserted, skipped, rejected, warnings.

File formats are proposed in `proposals/`.

## Embeddings

`embeddings/` fills `paper.embedding` with SPECTER2 vectors (base model plus the proximity adapter, both pinned to exact Hugging Face revisions; the model string is stored in `paper.embedding_model`). It has its own environment because it needs torch (Python 3.12):

```powershell
python -m venv embeddings/.venv      # use Python 3.12
embeddings\.venv\Scripts\python.exe -m pip install -r embeddings/requirements-embeddings.txt
embeddings\.venv\Scripts\python.exe -m embeddings embed-papers            # papers with embedding NULL
embeddings\.venv\Scripts\python.exe -m embeddings embed-papers --force    # redo everything
```

The first run downloads about 0.9 GB of model files. Papers without an abstract are skipped (never embedded from the title alone). Work is saved every 50 papers, so an interrupted run resumes by running the same command again. A run refuses to mix embeddings from different models unless `--force` is used. The experiment that measured SPECTER2 is in `experiments/embeddings/`.

The embedding tests use a fake encoder and run with the other tests. One extra test runs the real model and is skipped by default: `embeddings\.venv\Scripts\python.exe -m pytest tests -m slow`.

## Search layer

`retrieval/` is the SQL search layer (no API; the API belongs to the scoring and API module). `search(conn, query_vector, top_k, offset, year_min, year_max, venues, methods, datasets, tasks, exclude_ids, include_entities, ef_search)` returns plain dicts (`paper_id`, `title`, `year`, `venue`, `similarity`) from a single parameterized SQL statement. Papers without an embedding are never returned. Method, dataset and task filters take canonical names or aliases and check the paper's experiments; several values inside one filter mean OR. How different entity filters combine is set by `match`:

- `match="same_experiment"` (the default): **one** experiment of the paper must satisfy all supplied entity filters. `methods=["A"], tasks=["B"]` needs an experiment that uses A on B.
- `match="any"`: each filter may be satisfied by a different experiment. A paper with A in one experiment and B in another matches.

With a single entity filter both modes are the same. Year, venue and exclusion filters always combine with AND. The same option exists on `keyword_search()` and as `--match` on the command line.

Filters are applied after the HNSW index scan, so `search()` turns on pgvector's iterative index scan (`hnsw.iterative_scan = strict_order`) for each call; otherwise a selective filter returns too few rows. pgvector stops iterating after `hnsw.max_scan_tuples` index entries (default 20000).

`keyword_search(conn, text, ...)` is the full-text baseline for the later keyword-vs-vector evaluation (on-the-fly `to_tsvector`, no index).

To try it from the command line (testing aid only), with the embeddings environment:

```powershell
embeddings\.venv\Scripts\python.exe -m retrieval search --vector-file q.npy --top-k 5 --year-min 2020 --method "Some Method" --entities
embeddings\.venv\Scripts\python.exe -m retrieval keyword "machine translation" --top-k 5
```

## Evaluating retrieval

`retrieval/evaluation/` scores rankings against labelled queries: precision@K, recall@K, MRR and nDCG@K (graded relevance 0, 1, 2; the formulas are in the docstring of `metrics.py`). It reads **files only**: it never calls the database or a model, so keyword, vector and hybrid rankings can be compared later by saving each system's results as a JSON file.

```powershell
..\.venv\Scripts\python.exe -m retrieval.evaluation run --queries eval/queries.jsonl --ranker keyword --rankings eval/rankings-keyword.json -k 10
```

`--rankings` defaults to `rankings-<ranker>.json` next to the queries file. A query with no relevant paper in its judgments is left out of the means and listed. The query-file format, and how to label without bias, is a proposal in `proposals/retrieval-eval-format.md`.

## Tests

The tests need the containers running. They create a throwaway database for each run, apply `init.sql` to it, and drop it afterwards, so the main database is never touched.

```powershell
..\.venv\Scripts\python.exe -m pytest tests -v
```

## Mock data

`mock/` holds invented placeholder data (all ids start with `MOCK_`). It is not real. See `mock/README.md`.

## Reset from scratch

**This deletes all data loaded into this project's PostgreSQL and Neo4j** (the Docker volumes), then reloads `init.sql`. Other Docker projects are not affected.

```powershell
docker compose down -v
docker compose up --build
```

Then load the data again with the commands above.
