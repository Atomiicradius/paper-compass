# Evidence chain format (PROPOSAL)

Status: **PROPOSAL from Person 2 (evidence and RAG).** The code exists in `rag/` (branch `rag/evidence`), but nothing here is in `context/data-and-contracts.md`. Changing a contract needs a team decision. Open questions for Person 3 and for the UI owner (O10) are at the end.

## What it is

For one research-element combination (a pair A and B, for example a method and a task) the evidence chain collects, from PostgreSQL only, the facts that explain why the combination looks weakly represented: counts, a yearly series, the supporting papers, the closest existing work, and where each fact came from. Nothing is invented: every paper id comes from the `paper` table. A text summary is built from this JSON with a fixed template (no LLM).

## Functions (package `rag/`, all take a psycopg connection first)

| Function | Returns |
|---|---|
| `nearest_existing(conn, element_a, element_b, cutoff_year, limit=5)` | `list[str]` paper ids (the signature agreed with Person 3) |
| `nearest_existing_detailed(...)` | list of `{paper_id, title, year, tier, similarity, uses}` |
| `build_evidence(conn, element_a, element_b, cutoff_year, limit_per_role=5)` | the evidence JSON below |
| `build_evidence_ids(conn, element_a, element_b, cutoff_year, limit_per_role=5)` | `{"supports_A": [...], "supports_B": [...], "bridge": [...], "nearest_existing": [...]}` |
| `collect_paper_ids(evidence)` | `set[str]` of every paper id in the evidence (the allowed set for citation checks) |
| `summarize_evidence(evidence)` | text summary with `[paper:ID]` markers |
| `extract_paper_ids(text)`, `verify_citations(text, allowed_ids)` | citation checks |

An element is `(kind, id)` with kind `"method"`, `"dataset"` or `"task"`; the two kinds must differ and ids must be ints. Anything else raises `ValueError` before any SQL runs. The role names are exactly the values allowed by the `opportunity_evidence.role` check constraint, so `build_evidence_ids` output can be written to that table as it is.

## The universe and the counts

Same-universe rule (`data-and-contracts.md`): the universe of a pair is the experiment rows in which **both** columns of the pair's kinds are non-null, for papers with a known year that is `<= cutoff_year`. Papers with no year are left out. All counts are distinct papers over this one set.

- `n_a`: papers with a universe row that has A. `n_b`: the same for B. `N`: papers with any universe row.
- `observed`: papers with ONE experiment row that has A and B together.
- `expected = n_a * n_b / N` (0.0 when N is 0).

They are computed from the `experiment` table, not from the materialized views, because the views have no cutoff year. With a cutoff after the last year and no paper without a year, they equal the views (tested).

## Evidence JSON

```json
{
  "pair": {"a": {"kind": "method", "id": 1, "name": "Mock Method Alpha"},
           "b": {"kind": "task", "id": 1, "name": "Mock Task X"}},
  "corpus": {"cutoff_year": 2024, "universe_size": 8, "n_a": 3, "n_b": 3, "observed": 1, "expected": 1.125},
  "yearly": [{"year": 2019, "a": 1, "b": 1, "both": 1}, {"year": 2020, "a": 1, "b": 1, "both": 0}],
  "roles": {
    "supports_A": [{"paper_id": "...", "title": "...", "year": 2023, "venue": "...",
                    "source_sentence": "...", "extractor": "..."}],
    "supports_B": ["... same fields ..."],
    "bridge": [{"paper_id": "...", "title": "...", "year": 2021, "venue": null}],
    "nearest_existing": [{"paper_id": "...", "title": "...", "year": 2019, "venue": "...",
                          "source_sentence": "...", "extractor": "...",
                          "tier": "exact", "similarity": null, "uses": "both"}]
  },
  "limitations": ["...", "..."]
}
```

- `yearly`: papers per year using A, using B, and using both in one experiment, from the first to the last year in the universe; years without papers are zeros; `[]` if the universe is empty.
- `supports_A`: papers that use A but not B in the universe (supports_B the other way round). `bridge`: papers that cite into both of those sets, or that are in one set and cite a paper of the other. `nearest_existing`: exact papers (A and B together) first, then close ones.
- Every list holds at most `limit_per_role` entries. `supports_*` and `bridge` are ordered newest first (year DESC, then paper_id); `nearest_existing` keeps its own order (exact by year DESC, then close by similarity DESC).
- `source_sentence` and `extractor` are copied verbatim from one stored experiment of that paper that has the element, and are `null` when nothing is stored.
- `nearest_existing[].tier`: `"exact"` (A and B in one experiment) or `"close"`. For close papers `similarity` is the cosine similarity of the paper's embedding to the centroid (mean embedding) of the papers that use the other element, and `uses` says which element the paper uses (`"a"` or `"b"`).
- `limitations` is a fixed list of strings: counts depend on the analyzed corpus and extraction coverage; the same-universe and cutoff scope; a low count is a candidate for human review, not proof of a gap; closest work can only come from the corpus.

A paper that uses A and B only in **different** experiments is in no role and no tier (it is neither "A but not B" nor "A and B together").

## Citation marker

A paper is cited as `[paper:ID]`, on one line, with no space after the colon, in lower case (`[paper:W1234567890]`, `[paper:MOCK_P001]`). The id is any run of characters without whitespace or brackets. Only markers count; a bare id in the prose is ignored. `verify_citations(text, allowed_ids)` returns `ok`, `cited`, `unknown`, `uncited_markers_count` (malformed markers such as `[paper: W1]` or `[Paper:W1]`) and `has_no_citations`. `ok` is false if any cited id is not in the allowed set or any marker is malformed. An answer without any citation is `ok` but flagged.

## Summary text and its inference rule

`summarize_evidence(evidence)` builds a fixed-template text with four `## ` sections: what the corpus shows (counts as observations), what the system infers (one hedged statement), closest existing work (with `[paper:ID]` markers) and limitations. The inference depends only on the expected and observed counts, checked in this order:

| Condition | Statement |
|---|---|
| `expected < MIN_EXPECTED_FOR_INFERENCE` (1.0) | There is too little data to say anything about the pair. No inference sentence. This also covers an empty universe, and it applies even if `observed >= expected`. |
| `observed >= expected` | The pair is not weakly represented in the analyzed corpus and is not flagged as a candidate. |
| `observed < expected` and `expected >= 1.0` | The pair is potentially underexplored in the analyzed corpus: a candidate for review, not a proven gap. |
| ... and `expected < LOW_CONFIDENCE_BELOW_EXPECTED` (5.0) | A second sentence adds that this is low confidence because the expected count is small, and states that count. |

**The two thresholds are provisional until open decision O6.** `MIN_EXPECTED_FOR_INFERENCE = 1.0` mirrors Person 3's candidate filter, which drops pairs with an expected count below 1; `LOW_CONFIDENCE_BELOW_EXPECTED = 5.0` is a starting value with no data behind it yet. Both are module constants in `rag/summary.py` and should be tuned on real data together with the scoring thresholds. The wording follows `AGENTS.md`: never "definitely unexplored", "guaranteed research gap" or "nobody has done this" (a test scans for them).

## How the other modules would call it

**Person 3, scoring pipeline.** When it stores an opportunity: `ids = build_evidence_ids(conn, ("method", m), ("task", t), cutoff_year)`, then one `opportunity_evidence` row per id and role. He replaces his interim `nearest_existing` with `rag.nearest.nearest_existing` (same signature).

**Person 3, API, `POST /opportunities/{id}/explain`.** Load the opportunity row, then `evidence = build_evidence(conn, a, b, opportunity.corpus_cutoff_year)` and `text = summarize_evidence(evidence)`. Response (proposed): `{"evidence": evidence, "summary": text, "citation_check": verify_citations(text, collect_paper_ids(evidence))}`.

**Later, with an LLM (open decision O5).** The model would receive the evidence JSON, be told to cite only with `[paper:ID]` markers, and its answer is passed to `verify_citations(answer, collect_paper_ids(evidence))`. If the check fails, the API returns the template summary instead. Not built; no LLM client is chosen.

## Open questions

**For Person 3**
1. An opportunity row can have a method, dataset, task **and** setting. These functions take exactly one pair, and settings are not supported. Which pair should the evidence use when an opportunity has three or four elements (for example one call per pair of kinds, or only method x task)?
2. Is `opportunity.corpus_cutoff_year` the cutoff to pass? And is a default of 5 papers per role right?
3. Do you want `bridge` from this SQL (citation links between the A-only and B-only papers), or from your Neo4j graph code once it exists? The role name stays the same.
4. Please compare your own `n_a`, `n_b`, `N` and observed with `build_evidence(...)["corpus"]` on the same data; they should be identical under the same-universe rule.
5. Papers that use A and B only in separate experiments appear in no role. Should they count as "closest existing work"?
6. The summary uses `expected < 1.0` as "too little data", mirroring your candidate filter, and `expected < 5.0` as low confidence. Is 1.0 exactly your filter's threshold, and should the two values live in one shared place once O6 is settled?

**For the UI owner (O10)**
1. Is this JSON a good payload for the evidence panel (snake_case keys, `similarity` as a 0 to 1 number, `yearly` as a list of objects)?
2. The summary is Markdown-like text with `## ` headings and `[paper:ID]` markers. Should the UI turn markers into links to `GET /papers/{id}`, or should the API return the sections separately?
3. Should the limitations banner show `limitations` exactly as given?
4. Confirm the response shape of `POST /opportunities/{id}/explain` above, or give the shape you need, so it can be added to `data-and-contracts.md`.
