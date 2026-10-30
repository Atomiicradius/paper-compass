# Vocabulary format (PROPOSAL)

Status: **proposal from Person 2 (database and loader) for Person 1 to accept or change.**
Not part of `context/data-and-contracts.md` until the team agrees.

## File

JSON Lines (`.jsonl`), UTF-8, one JSON object per line, one vocabulary entry per object.

## Fields

```json
{"type": "method", "canonical_name": "Example Method", "aliases": ["EM", "example-method"]}
```

| Field | Required | Notes |
|---|---|---|
| `type` | yes | One of `method`, `dataset`, `task`, `setting`. |
| `canonical_name` | yes | The name stored in the table. Unique within its type. |
| `aliases` | yes (may be `[]`) | Other spellings that should resolve to `canonical_name`. |

## Mapping to the schema

| `type` | Entity table | Column used | Alias table |
|---|---|---|---|
| `method` | `method` | `canonical_name` | `method_alias` |
| `dataset` | `dataset` | `canonical_name` | `dataset_alias` |
| `task` | `task` | `canonical_name` | `task_alias` |
| `setting` | `setting` | `name` | **none** |

## Rules the loader would apply

- Aliases are unique **per type** (the alias tables have `alias` as the primary key). An alias that already points to a different canonical name of the same type is rejected with a reason.
- Matching of extraction values to the vocabulary is exact. Whether it should ignore case or surrounding whitespace is **not decided**; the loader would trim whitespace only, unless Person 1 says otherwise.
- An alias may equal its own `canonical_name`. That is harmless and ignored.
- Loading is idempotent: re-running adds nothing.
- The vocabulary file is **deliberately** edited by the extraction owner. The loader never adds vocabulary from extraction output; unknown values are written to `db/rejects/` with a reason.

## Known gaps in the schema (not changed here)

- **`setting` has no alias table.** Entries of type `setting` must have `"aliases": []`; the loader rejects a non-empty list. A `setting` value in an extraction row is matched to a canonical name **exactly, after normalizing case and whitespace** (case-folded, whitespace collapsed and trimmed). No schema change is made. **Limitation:** different wordings of the same setting (for example "low-resource" and "low resource settings") will not match and the row goes to `db/rejects/`. If settings need aliases, that is a schema change and needs a team decision.
- **`topic` is not covered.** The schema has a `topic` table and `paper_topic` link, but this format has no `topic` type and the metadata format has no topic field. Not needed for the current task.
- `description` columns on method, dataset and task are not part of this format and stay NULL.

## Mock example

`db/mock/vocabulary.jsonl` follows this format. Every entry there is mock data.
