# Sharing embeddings without Git (PROPOSAL)

Status: **PROPOSAL from Person 2 (database and retrieval). No code exists for this yet.** It depends on open decision O3 (SPECTER2) being confirmed by the team.

## Why

Embedding the corpus takes about 10 to 30 minutes on one laptop (see `db/experiments/embeddings/results.md`) and needs torch, a 0.9 GB model download and Python 3.12. Teammates should not each have to do this to run search, clustering or scoring. The vectors are binary, model-specific and change whenever the corpus or model changes, so they should **not** go into Git history (every re-export would add 15 to 30 MB to the repository forever). Instead, one person embeds and shares a small export file, and others import it into their own database.

## File format: a folder with two files

Recommended: **`.npy` plus a JSON manifest.** numpy is already in the embeddings environment, float32 round-trips exactly (PostgreSQL stores `vector` as float4), and no new dependency is needed.

```text
embeddings-specter2-2026-11-05/
  embeddings.npy      float32 array, shape (N, 768), row i belongs to paper_ids[i]
  manifest.json
```

`manifest.json`:

```json
{
  "format_version": 1,
  "created_at": "2026-11-05T10:00:00Z",
  "model": "allenai/specter2_base@<rev>+allenai/specter2@<rev> (proximity)",
  "dim": 768,
  "dtype": "float32",
  "count": 5000,
  "embeddings_sha256": "<hash of embeddings.npy>",
  "paper_ids": ["W1234567890", "..."],
  "input_sha256": ["<hash of title + [SEP] + abstract used for paper 0>", "..."]
}
```

- `input_sha256` (recommended) is the hash of the exact text that was embedded. It lets the importer notice that a paper's title or abstract differs in the target database, which would make the vector stale.
- Only paper ids and vectors are exported. **No titles or abstracts, no credentials, no database name.**
- Order of rows is the order of `paper_ids` (sorted by id, so exports are reproducible).

### Alternatives considered

| Format | Size per paper | Verdict |
|---|---|---|
| `.npy` float32 (proposed) | 3,072 bytes | exact, no new dependency |
| `.npy` float16 | 1,536 bytes | half the size but loses precision; not worth it at these sizes |
| CSV text, 9 significant digits | about 9,570 bytes | about 3 times larger, slow to parse, still not exact for float32 |
| CSV text, shortest exact repr | about 15,250 bytes | 5 times larger |
| Parquet | about the same as `.npy` | needs `pyarrow` (a large extra dependency) for no real gain |

Sizes of `.npy`, CSV and float16 were measured on 100 real SPECTER2 vectors from the experiment, then scaled.

## File size estimates

| Corpus | `embeddings.npy` | manifest (ids + input hashes) | Total | Zipped (about 7% smaller, measured ratio 0.93) |
|---|---|---|---|---|
| 5,000 papers | 15.4 MB | about 0.4 MB (ids 75 KB, hashes 340 KB) | **about 15.8 MB** | about 14.7 MB |
| 10,000 papers | 30.7 MB | about 0.8 MB (ids 150 KB, hashes 680 KB) | **about 31.6 MB** | about 29.3 MB |

Small enough to share through any file-sharing service. Where to put it (shared drive, a GitHub Release asset, a USB stick) is for the team to choose; it should not be a commit. Proposal: export into `db/exports/`, which would be added to `.gitignore` (like `db/rejects/`).

## Commands

Both live in the existing `db/embeddings/` package and run from `db/` with the embeddings environment:

```powershell
embeddings\.venv\Scripts\python.exe -m embeddings export-embeddings OUT_DIR [--dbname NAME]
embeddings\.venv\Scripts\python.exe -m embeddings import-embeddings IN_DIR [--dry-run] [--overwrite] [--strict] [--dbname NAME]
```

Neither command loads the model, so neither needs torch or the 0.9 GB download (only numpy and psycopg), and both could also run in a lighter environment.

### `export-embeddings`

1. Select papers where `embedding IS NOT NULL`, ordered by `paper_id`.
2. Refuse if they come from more than one `embedding_model` value (a mixed database should not be shared). Write that value into the manifest.
3. Read each vector exactly as stored (float4), write `embeddings.npy`, the manifest and its hash. Compute `input_sha256` from the paper's current title and abstract.
4. Print a summary: papers exported, model string, folder size.

### `import-embeddings`

All checks run **before anything is written**. With `--dry-run` the command only runs the checks and prints what it would do.

| # | Check | If it fails |
|---|---|---|
| 1 | `manifest.json` and `embeddings.npy` exist; `format_version` is known | stop |
| 2 | `embeddings.npy` hash equals `embeddings_sha256` (file not damaged or edited) | stop |
| 3 | array shape is `(count, dim)`, `count == len(paper_ids)`, ids are unique | stop |
| 4 | **`dim` is 768** (the `vector(768)` column) and dtype is float32 | stop |
| 5 | every value is finite (no NaN or infinity) | stop |
| 6 | **model string in the manifest equals the one pinned in the importer's code** (same base and adapter revisions) | stop; a different model must not be mixed in |
| 7 | the target database has no embeddings from a different model (same rule as `embed-papers`) | stop; use a fresh database or re-embed |

Then, per paper id in the file:

| Situation in the target database | What happens |
|---|---|
| paper exists, no embedding yet | vector and model string are written |
| paper exists, already embedded with the same model | skipped and counted ("already embedded"); replaced only with `--overwrite` |
| paper exists, but its title or abstract differs from `input_sha256` | **skipped and warned** (the vector would not match the text); needs re-embedding with `embed-papers` |
| **paper does not exist in the target database** | **not imported, never created.** Counted, and the ids are listed in a file in `db/rejects/`. No stub rows. With `--strict` the whole import stops instead. |

Papers in the target database that are **not** in the file are left alone with `embedding` NULL. The summary reports how many, so a teammate knows whether to load more papers, get a newer export, or run `embed-papers` for the rest.

Writes use small transactions (like `embed-papers`), so the import is resumable and re-running it is harmless. The summary shows: papers in file, imported, already embedded, skipped for changed text, missing from the database, papers in the database without a vector, and the model string.

### Optional extra check: `--verify-sample N`

Re-embed N random imported papers locally with the real model and require cosine similarity of at least 0.999 against the imported vectors. This catches silent differences in library versions or hardware. It needs torch and the model, so it is optional and off by default.

## Open questions for the team

1. Where do exports live (shared drive, GitHub Release asset, other)? Not decided by this proposal.
2. Is hashing the input text (`input_sha256`) wanted, or is matching paper ids enough? It costs about 0.3 to 0.7 MB and catches stale vectors.
3. Should an import into a database that already has embeddings from another model be a hard stop (proposed) or allowed with `--overwrite`?
4. Who produces the shared export, and how often (after each ingestion batch, or at milestones)?

## Not part of this proposal

Hybrid search, the Neo4j sync, and which papers are in the corpus (open decision O2).
