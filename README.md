# paper-compass

Research Paper Discovery and Exploration System (DBMS course CD252IA, RV College of Engineering).

**Pipeline:** Discover -> Connect -> Map -> Detect -> Score -> Explain. It retrieves papers for a research idea, maps how the surrounding work is connected, and flags potentially underexplored combinations of research elements (methods, tasks, datasets, settings), ranked and backed by evidence. A candidate opportunity is a signal for human review, not proof of a research gap.

---

## Quickstart: Data & Database Setup

### 1. Ingest Papers & Generate Controlled Vocabulary (Person 1)

```powershell
# Ingest pilot corpus from OpenAlex API (~500 papers in Machine Translation / Low-Resource NLP)
python ingest/fetch_openalex.py --query "machine translation low-resource" --count 500 --out ingest/data/papers_pilot.jsonl

# Write the controlled vocabulary & aliases (curated manually in ingest/create_vocabulary.py)
python ingest/create_vocabulary.py

# Run extraction to produce experiment tuples (method, dataset, task, setting, confidence, source_sentence)
python extraction/extract.py --papers ingest/data/papers_pilot.jsonl --vocab ingest/data/vocabulary.jsonl --out extraction/data/extractions_pilot.jsonl

# Verify data integrity and loader compatibility (dry-run)
python db/test_pilot_loaders.py
```

### 2. How to Load into PostgreSQL (When Docker is Running)

Ensure the database containers are started and configured:

```powershell
cd db
# Copy env file if not already done, then edit with your passwords/ports
Copy-Item .env.example .env

# Start PostgreSQL (pgvector) and Neo4j
docker compose up -d --build
```

Load the data into PostgreSQL in dependency order (Vocabulary -> Papers -> Extractions), then refresh the 12 materialized views:

```powershell
# Load all datasets at once and refresh materialized views:
python -m loaders load-all `
  --vocabulary ..\ingest\data\vocabulary.jsonl `
  --papers ..\ingest\data\papers_pilot.jsonl `
  --extractions ..\extraction\data\extractions_pilot.jsonl `
  --refresh
```

Or run each loader individually:

```powershell
# 1. Load vocabulary (canonical names + aliases)
python -m loaders load-vocabulary ..\ingest\data\vocabulary.jsonl

# 2. Load papers (venues, institutions, authors, citations)
python -m loaders load-papers ..\ingest\data\papers_pilot.jsonl

# 3. Load extractions (experiments; unmapped entities are rejected to db/rejects/)
python -m loaders load-extractions ..\extraction\data\extractions_pilot.jsonl

# 4. Refresh materialized views
python -m loaders refresh-views
```

---

## Documentation & Context

All project context lives in [`context/`](context/). Read [`context/AGENTS.md`](context/AGENTS.md) first; it specifies which file to read for which task.

| File | Purpose |
|---|---|
| [`context/AGENTS.md`](context/AGENTS.md) | Index, hard rules, folder ownership, wording rules |
| [`context/project-context.md`](context/project-context.md) | Problem, positioning, architecture, scope |
| [`context/data-and-contracts.md`](context/data-and-contracts.md) | Schema, Neo4j model, extraction format, opportunity object, API |
| [`context/build-plan.md`](context/build-plan.md) | Ownership, phases, evaluation, risks |
| [`context/decisions-and-progress.md`](context/decisions-and-progress.md) | Open decisions, decision log, per-person progress |
| [`context/docs/reference/project-plan-v2.md`](context/docs/reference/project-plan-v2.md) | Detailed reasoning behind the design |

Schema and contract changes require a team decision (see hard rules in [`context/AGENTS.md`](context/AGENTS.md)).
