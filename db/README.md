# db/

Local PostgreSQL (with pgvector) and Neo4j for Paper Compass. The schema is `init.sql`, copied verbatim from section 1 of `context/data-and-contracts.md`.

## Run it

From this folder (`db/`):

```powershell
Copy-Item .env.example .env      # then edit .env and set real passwords
docker compose up --build
```

- Postgres is built from `Dockerfile`: `postgres:16` pinned by digest (PostgreSQL 16.15) plus the apt package `postgresql-16-pgvector` pinned to one version, so everyone gets the same image. Use `docker compose up --build -d` to run in the background.
- `init.sql` runs automatically the first time the Postgres volume is created.
- `.env` is ignored by git. Only `.env.example` (placeholders) is committed.

## Connect

| Service | Address | Credentials |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432`, database `POSTGRES_DB` | `POSTGRES_USER` / `POSTGRES_PASSWORD` from `.env` |
| Neo4j Browser | http://127.0.0.1:7474 | `NEO4J_USER` / `NEO4J_PASSWORD` from `.env` |
| Neo4j Bolt | `bolt://127.0.0.1:7687` | same as above |

```powershell
docker exec -it pc-postgres psql -U paper_compass -d paper_compass
```

## Start from scratch

This deletes **this project's** Postgres and Neo4j data (not other Docker projects) and reloads `init.sql`:

```powershell
docker compose down -v
docker compose up --build
```

## Mock data

`db/mock/` holds invented placeholder data (all ids start with `MOCK_`). It is not real. See `db/mock/README.md`. Proposed file formats for real data are in `db/proposals/`.
