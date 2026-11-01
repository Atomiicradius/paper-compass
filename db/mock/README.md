# MOCK DATA - not real

Everything in this folder is invented placeholder data for testing the database and the loader.
It does not describe real papers, authors, institutions, venues, methods or datasets.

- Every `paper_id` starts with `MOCK_`.
- Papers have titles starting with `MOCK:` and DOIs under `10.0000/mock.`.
- Vocabulary names start with `Mock`.
- Extraction rows use `extractor: "mock-v0"` and a `source_sentence` starting with `MOCK:`.

Files:
- `vocabulary.jsonl`: 12 vocabulary entries (4 methods, 3 datasets, 3 tasks, 2 settings).
- `papers.jsonl`: 10 papers with authors, venue and references.
- `extractions.jsonl`: 14 extraction rows. 3 are meant to be rejected by the loader
  (unknown method, unknown dataset, paper not in `papers.jsonl`).

Deliberate edge cases:
- an author with no `external_id` on two papers, spelled with different case and spacing, and with a
  different institution on each (must merge by normalized name and log an institution conflict)
- an author with an `external_id` whose institution differs between two papers (conflict to be logged)
- a paper with no venue and no DOI
- a reference to a paper that is not in the file (`MOCK_P404`)
- a vocabulary alias used in an extraction row (method, dataset and task)
- rows with null dataset, task or setting

Total rows: 12 + 10 + 14 = 36.
