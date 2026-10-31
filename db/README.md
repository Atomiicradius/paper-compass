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

Credentials live in `db/.env` (copy of `.env.example`). Ports are set in `docker-compose.yml`.

| Service | Address | Credentials in `.env` |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Neo4j Browser | http://127.0.0.1:7474 | `NEO4J_USER`, `NEO4J_PASSWORD` |
| Neo4j Bolt | `bolt://127.0.0.1:7687` | same as above |

psql, without installing anything (inside the container):

```powershell
docker exec -it pc-postgres psql -U paper_compass -d paper_compass
```

psql installed on your machine:

```powershell
psql -h 127.0.0.1 -p 5432 -U paper_compass -d paper_compass
```

(Use the user and database names from your `.env`; the password is prompted for.) Always use `127.0.0.1`, not `localhost`.

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
