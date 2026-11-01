# Retrieval evaluation: query-set format (PROPOSAL)

Status: **PROPOSAL from Person 2 (database and retrieval).** Not part of `context/data-and-contracts.md`. The number of queries, who labels, and where the file lives need the team's agreement. Depends on having a real corpus (open decision O2) and, for vector search, confirmed embeddings (O3).

## Purpose

Compare keyword, vector and hybrid search (and later the query encoder: the `specter2_adhoc_query` adapter versus the proximity adapter) on the same labelled queries, using precision@K, recall@K, MRR and nDCG@K.

## Query file: JSON Lines, one query per line

```json
{"query_id": "q01", "query_text": "low-resource neural machine translation", "filters": {"year_min": 2018}, "judgments": {"W1111111111": 2, "W2222222222": 1, "W3333333333": 0}}
```

| Field | Required | Notes |
|---|---|---|
| `query_id` | yes | Unique text id, for example `q01`. |
| `query_text` | yes | The query as a user would type it. Used by keyword search and by the query encoder. |
| `filters` | no | The filters to apply, using the `search()` argument names (`year_min`, `year_max`, `venues`, `methods`, `datasets`, `tasks`, `match`). The scoring runner ignores them; whoever produces the rankings applies them. |
| `judgments` | yes | Object `paper_id -> grade`. Papers not listed are treated as grade 0. |

Grades: **2** = directly about the query (would be a good answer), **1** = related or partly relevant, **0** = judged and not relevant. Metrics count grade 1 and 2 as relevant for precision, recall and MRR; nDCG uses the difference (gain `2^grade - 1`).

## Rankings file (output of a system, input of the runner)

One JSON file per system: `{"q01": ["W1111111111", "W4444444444", "..."], "q02": [...]}`, best result first. Default name `rankings-<ranker>.json` next to the query file, for example `rankings-keyword.json`, `rankings-vector.json`, `rankings-hybrid.json`. A separate small script (not part of the runner) produces these from `search()` and `keyword_search()`; the runner never calls the database or a model.

```powershell
embeddings\.venv\Scripts\python.exe -m retrieval.evaluation run --queries eval/queries.jsonl --ranker keyword -k 10
```

It prints precision, recall, reciprocal rank and nDCG per query, then the mean. A query with no relevant paper is left out of the means and listed.

## Who labels and how many

- **15 to 20 queries**, written by the team from the real topics in the corpus (several topics, some broad, some narrow, a few with filters).
- **Labelled by people**, ideally two (for example Person 1 and Person 3) on the same queries, then disagreements settled by discussion. The person who built the search layer should not be the only labeller.
- A query needs enough judged papers to be meaningful: aim for at least 5 relevant papers per query, otherwise recall and nDCG are noisy.

## Avoiding bias

- **Label with the system's results hidden.** Labellers see candidate papers in random order, without rank, score or which system returned them. Otherwise high-ranked papers look more relevant.
- **Build the candidate pool from several systems**: for each query, take the union of the top results of keyword, vector and (later) hybrid search, plus some random papers from the same topic. A paper outside the pool is treated as grade 0; a pool made from one system favours that system.
- **Fix the judgments before looking at any metric**, and do not edit them to improve a score.
- Keep the query file in the repository (it holds ids and grades, not text of papers); keep the rankings out of Git if they are large.

## Limits

With 15 to 20 queries the means are rough. Report the per-query numbers next to the mean, and do not claim a difference between two systems unless it appears on most queries.
