# ingest/

Ingestion scripts for Paper Compass (Person 1).

Fetches research papers from OpenAlex, cleans metadata, reconstructs abstracts from inverted indexes, normalizes venue types, extracts author IDs and institutions, and emits JSON Lines adhering to Person 2's loader specifications (`db/proposals/paper-metadata-format.md`).

## Quickstart

Run with Python from repository root:

```powershell
# 1. Fetch 500-paper pilot
python ingest/fetch_openalex.py --query "machine translation low-resource" --count 500 --out ingest/data/papers_pilot.jsonl

# 2. Test loading into PostgreSQL using Person 2's loader
cd db
..\.venv\Scripts\python.exe -m loaders load-papers ..\ingest\data\papers_pilot.jsonl
```

## Vocabulary

`ingest/data/vocabulary.jsonl` is written by `ingest/create_vocabulary.py`. The vocabulary is curated manually in ingest/create_vocabulary.py: its entries and aliases are the lists in that file. Format: `db/proposals/vocabulary-format.md`.

## Schema output

Every line in `papers_pilot.jsonl` is a JSON object with:
- `paper_id`: Clean OpenAlex work ID (e.g. `W3123456789`)
- `title`: Paper title
- `abstract`: Full text reconstructed from inverted index (or null)
- `year`: Publication year (1950..2100)
- `doi`: Clean DOI (e.g. `10.1234/...`)
- `venue`: Venue display name
- `venue_type`: One of `conference`, `journal`, `workshop`, `preprint`, `other`
- `authors`: List of authors with `name`, `external_id` (OpenAlex `A...` ID), `institution`, and 1-based `order`
- `references`: List of cited `paper_id` strings (`W...`)
