# Paper metadata format (PROPOSAL)

Status: **proposal from Person 2 (database and loader) for Person 1 to accept or change.**
Not part of `context/data-and-contracts.md` until the team agrees.

## File

JSON Lines (`.jsonl`), UTF-8, one JSON object per line, one paper per object.

## Fields

```json
{
  "paper_id": "W1234567890",
  "title": "Example title",
  "abstract": "Example abstract text.",
  "year": 2022,
  "doi": "10.1234/example",
  "venue": "Example Venue",
  "venue_type": "conference",
  "authors": [
    {"name": "Example Author", "external_id": "A123", "institution": "Example Institute", "order": 1}
  ],
  "references": ["W1111111111", "W2222222222"]
}
```

| Field | Required | Notes |
|---|---|---|
| `paper_id` | yes | Text ID shared with Neo4j (for example an OpenAlex work ID). Must be unique in the file. |
| `title` | yes | Non-empty. |
| `abstract` | no | `null` allowed. |
| `year` | no | Integer from 1950 to 2100 (database check). `null` allowed. |
| `doi` | no | `null` allowed. Unique across the database, so no two papers may share a DOI. |
| `venue` | no | Venue name as text. `null` allowed. |
| `venue_type` | no | One of `conference`, `journal`, `workshop`, `preprint`, `other`. **Added by Person 2, not in the original request.** If missing, the loader would use `other`. Needed because `venue` is unique on (name, type) and a NULL type would allow duplicate venues. |
| `authors` | yes (may be `[]`) | List of objects, see below. |
| `references` | yes (may be `[]`) | List of `paper_id` values this paper cites. |

Author object:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Non-empty. |
| `external_id` | no | For example an OpenAlex author ID. When present, it is how the loader matches authors across papers. |
| `institution` | no | Institution name. Institutions are matched by exact name. |
| `order` | yes | Integer position in the author list, starting at 1. |

## Loader behaviour this format assumes

- Loading is idempotent: running the same file twice changes nothing.
- A bad line (invalid JSON, missing required field, year out of range) is **rejected with a reason** and written to `db/rejects/`; it does not stop the other lines.
- A `references` entry that is not a `paper_id` in the database cannot be stored (foreign key). It is **skipped, not stored, and no stub paper is created**. The loader summary reports the count of skipped references and the cited IDs. (Decided by Person 2 with the team lead; Person 1 may still object.)
- An author's institution is set when the author is first inserted and is not overwritten. If a later paper gives a different institution for the same author, the loader logs a warning and keeps the first value. This follows from the schema storing one institution per author.
- `venue_type` defaults to `other` when missing (accepted).

## Author matching and known simplification

- Authors **with** an `external_id` are matched by it.
- Authors **without** an `external_id` are matched by **normalized name**: case-folded, with runs of whitespace collapsed to one space and the ends trimmed. If the matched author's stored institution differs from the one in the new record, the loader logs a warning and keeps the first institution.
- **Known simplification:** homonyms (two different people with the same normalized name) will be merged into one author row, and one person written with different spellings will be split into several. This is accepted for the prototype.
- **Real data should always carry `external_id` for every author.** Person 1's ingestion should supply it so that name matching is never needed outside mock data.
- An author who has an `external_id` is never matched by name to a different `external_id`.

## Mock example

`db/mock/papers.jsonl` follows this format. Every record there is mock data.
