# API shapes for O10 (proposal, awaiting Persons 1 and 2)

Status: **proposed by Person 3, 2026-11-22. Not agreed yet.** Once Persons 1 and 2 confirm, the shapes below are copied into `context/data-and-contracts.md` section 5 and O10 is closed in `context/decisions-and-progress.md`.

Every shape below was checked against the real pilot database `pc_pilot` (1,999 papers, 1,055 experiments, 1,999 SPECTER2 embeddings, restored from `pc_pilot_2026-11-21.dump`), with the Neo4j projection synced from it. The checks used `fastapi.testclient` and the Streamlit UI in `ui/`. Times are single requests on a laptop, after warm-up.

| Endpoint | Status on pc_pilot | Time |
|---|---|---:|
| `GET /opportunities` | 200, 13 items | ~50 ms |
| `GET /opportunities/{id}` | 200; 404 for an unknown id | ~50 ms |
| `POST /opportunities/{id}/explain` | 200, citation check passed | ~220 ms |
| `POST /search` (keyword) | 200 | ~760 ms |
| `POST /search` (vector) | 200 once the SPECTER2 query encoder is installed | see the report |
| `GET /papers/{id}` | 200; 404 for an unknown id | ~60 ms |
| `GET /papers/{id}/graph` | 200 (Neo4j) | ~730 ms cold |
| `GET /papers/{id}/related` | 200 | ~120 ms |
| `GET /trends` | 200 | ~80 ms |
| `GET /clusters` | 200 | ~25 ms |
| `GET /landscape` | 200 | ~210 ms |
| `POST /rag/query` | 501 until O5 | |

## 1. Opportunity (contract section 4, unchanged)

`GET /opportunities?limit=20&offset=0&cutoff_year=&weights_version=&min_confidence=` returns `{total, items: [Opportunity], disclaimer}`. `GET /opportunities/{id}` returns one Opportunity. This is the contract object, with real values from opportunity 14:

```json
{
  "opportunity_id": 14,
  "elements": {"method": "Masked Language Modeling", "task": "Machine Translation", "dataset": null, "setting": null},
  "corpus": {"papers": 1991, "cutoff_year": 2026},
  "observed_count": 1,
  "expected_count": 11.859649,
  "signals": {"sparsity": 0.844, "semantic_compatibility": 0.75, "temporal_activity": 0.548,
              "graph_bridge_strength": null, "method_compatibility": null},
  "confidence": 1.0,
  "score": 73.73,
  "weights_version": "v1-three-signal",
  "evidence": {"supports_A": ["W2982180741", "..."], "supports_B": ["..."], "bridge": ["..."], "nearest_existing": ["..."]}
}
```

**Question Q1 (all):** `corpus.papers` is currently *all* papers with `year <= cutoff` (1,991). The expected count uses the same-universe N, which is 399 papers for Method × Task. A reader who sees "1,991 papers, expected 11.9" may assume the expected count was taken over 1,991 papers. Proposal: keep `corpus.papers` as it is and add `corpus.universe_size` (399). The UI already shows N from `/explain`. Adding a field is a contract change, so it needs your yes.

## 2. Explain (Person 2's `rag/`, see `db/proposals/evidence-chain-format.md`)

`POST /opportunities/{id}/explain` returns:

```text
{ opportunity_id, disclaimer,
  evidence: { pair: {a: {kind, id, name}, b: {...}},
              corpus: {cutoff_year, universe_size, n_a, n_b, observed, expected},
              yearly: [{year, a, b, both}],
              roles: { supports_A | supports_B | bridge: [{paper_id, title, year, venue, source_sentence, extractor}],
                       nearest_existing: [{paper_id, title, year, venue, tier, similarity, uses, source_sentence, extractor}] },
              limitations: [str] },
  summary: markdown str, summary_source: "template" | "llm", summary_fallback_reason: str | null,
  citation_check: {ok, cited: [paper_id], unknown: [paper_id], uncited_markers_count, has_no_citations} }
```

422 if the opportunity is not exactly one pair of method/dataset/task; 404 if unknown.

## 3. Search and papers (provisional)

`POST /search` body is the contract `{query, top_k=10, year_min}` plus optional `year_max, venues, methods, datasets, tasks, match ("same_experiment"|"any"), collapse_same_title (bool, default false), mode ("auto"|"vector"|"keyword")`. It returns `{query, mode, score_type ("cosine_similarity"|"ts_rank"), model, note, results: [SearchHit]}`, where `SearchHit = {paper_id, title, year, venue, score, methods, datasets, tasks}`.

**Q2 (Person 1, UI):** screen 1 in plan section 14.1 lists authors and topics on each hit. `SearchHit` has neither. On pc_pilot `paper_topic` is empty, so topics would always be `[]`. Should authors be added to `SearchHit` (an extra join), or is the paper page enough?

`GET /papers/{id}` returns `{paper_id, title, year, abstract, doi, venue, authors: [name], topics, methods, datasets, tasks, cites: [paper_id], cited_by: [paper_id]}`. `cites`/`cited_by` only include papers inside the corpus.

`GET /papers/{id}/related?top_k&year_min&year_max` returns `{paper_id, score_type, model, results: [SearchHit]}`. It returns 409 if the paper has no embedding.

`GET /papers/{id}/graph?limit=200` returns `{center, nodes: [{id, label, name, year}], edges: [{source, target, type}]}`. Labels and types are the Neo4j ones in contract section 2.

## 4. Landscape (provisional)

- `GET /trends?element_type=method|dataset|task|topic&label=emerging|declining|stable` returns `[{element_type, element_id, name, yearly: {year: n}, total, recent_share, growth, label}]`.
- `GET /clusters` returns `{method, min_cluster_size, min_samples, pca_dims, selection, embedding_model, n_papers, n_noise, clusters: [{cluster_id, size, year_min, year_max, top_elements: [{name, n_papers}], paper_ids}]}`. The `min_samples`, `pca_dims` and `selection` fields are new in this change; see `graph/README.md`.
- `GET /landscape` returns `{corpus, papers_per_year, n_clusters, emerging, declining, weakly_connected_cluster_pairs, bridge_papers: [{paper_id, own_cluster, linked_clusters}], disclaimer}`.

**Q3 (Person 1):** trends labels elements with only 1 to 3 papers as emerging or declining (e.g. Label Smoothing, 1 paper). The UI hides elements with fewer than 5 papers by default. Should the API apply a `min_total` itself?

## 5. Not built

`POST /rag/query` (501, needs O5) and `POST /opportunities/{id}/feedback` (stretch).
