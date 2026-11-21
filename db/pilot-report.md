# Pilot report: 2,000-paper corpus loaded and embedded (database `pc_pilot`)

Branch `db/pilot`, 2026-11-20. Every number below comes from a run on that date (output kept in the working notes of the run); nothing is estimated.

## 1. Load (Part 3)

`python -m loaders load-all --refresh` on `ingest/data/vocabulary.jsonl`, `ingest/data/papers_pilot.jsonl` and `extraction/data/extractions_pilot.jsonl` into a new database `pc_pilot` created from `db/init.sql`.

| Item | Count |
| --- | ---: |
| Vocabulary entries inserted | 125 (aliases inserted: 224) |
| Paper rows read | 2000 |
| Papers inserted | 1999 |
| Papers rejected | 1 |
| Venues inserted | 535 |
| Institutions inserted | 993 |
| Authors inserted | 8157 |
| Paper-author links inserted | 10662 |
| Author institutions filled in later (NULL, then a value) | 223 |
| Author institution conflicts (first value kept; full list in `db/rejects/institution_conflicts.log`, not committed) | 616 |
| Citations stored | 11542 |
| Citations skipped (cited paper not in the corpus) | 66949 |
| Experiments inserted | 1055 of 1055 read (0 rejected) |
| Method / dataset / task / setting entities | 54 / 41 / 18 / 12 |
| Authors without an institution (query on `pc_pilot`) | 2,396 of 8,157 |

`mv_universe_size` (distinct papers per pair type, after `--refresh`):

| pair_type | n_papers |
| --- | ---: |
| dataset_task | 27 |
| method_dataset | 32 |
| method_task | 399 |

Other warnings in the papers summary: 15 authors listed twice on one paper (second entry ignored).

**Rejected paper.** `W1522301498` (Kingma & Ba, "Adam") is rejected because its DOI `10.48550/arxiv.1412.6980` already belongs to `W2964121744`. They are two OpenAlex records for the same paper.

**Idempotence.** A second `load-all --refresh` inserted 0 rows in every table (papers skipped 1,999, citations already present 11,542, experiments skipped 1,055); the row counts of paper, author, institution, venue, paper_author, citation, experiment, method_alias and task_alias were identical before and after, and the institution conflict list (616) was identical, with no new conflicts.

## 2. Embedding (Part 4)

`python -m embeddings embed-papers --dbname pc_pilot` with the existing code and the pinned environment (`db/embeddings/requirements-embeddings.txt`; torch 2.15.0, transformers 4.57.6, adapters 1.3.0). Model `allenai/specter2_base@3447645e...` with the proximity adapter `allenai/specter2@20815596...`, text = title + [SEP] + abstract, `vector(768)`.

| Item | Value |
| --- | --- |
| Device | CPU (torch 2.15.0+cpu, CUDA not available; 14 torch threads on 20 logical CPUs) |
| Batch size | 1 (the existing pipeline encodes one paper per call; chunks of papers share one database transaction) |
| Total wall time | 344 s (start of the command to its end, including model load) |
| Seconds per paper (encoding only, as reported by the CLI) | 0.124 |
| Papers with an embedding | 1,999 of 1,999 |
| NULL embeddings / zero-norm embeddings | 0 / 0 |
| Embedding norm (min, max) | 21.280, 22.524 |
| Dimensions (min, max) | 768, 768 |
| `embedding_model` values | 1 distinct value (the string above) |
| HNSW index | `idx_paper_embedding_hnsw` on `paper` using `hnsw (embedding vector_cosine_ops)`; pgvector 0.8.7 |
| `hnsw.iterative_scan` in the search session | `strict_order` (`SHOW` inside the search transaction) |

The log prints "There are adapters available but none are activated for the forward pass" once at start. To check that the adapter really is active, the stored vectors of the 5 pilot papers that also exist in the earlier experiment (`db/experiments/embeddings`, made with the adapter verified active by `verify_adapter.py`) were compared with it: cosine 1.000000 for all 5 (min and mean). The model cache stays in the ignored `data/` folder.

## 3. Sample searches (Part 5)

Run by `db/retrieval/pilot_queries.py`. Each query text is encoded the same way a paper is (proximity adapter, no abstract); there is no separate query encoder yet. Vector search = `search(top_k=5)`; keyword search = `keyword_search(top_k=5)` (PostgreSQL full text, all query words must match). Times are the median of 5 runs after one warm-up.

| Query | Vector ms | Keyword ms | Shared top-5 |
| --- | ---: | ---: | ---: |
| low-resource neural machine translation | 47.7 | 245.4 | 1 of 5 (keyword returned 5) |
| back-translation for low-resource languages | 47.9 | 225.4 | 0 of 5 (keyword returned 5) |
| multilingual pretraining for translation | 47.7 | 220.4 | 0 of 5 (keyword returned 5) |
| zero-shot translation | 47.8 | 213.2 | 3 of 5 (keyword returned 5) |
| unsupervised machine translation | 47.7 | 218.4 | 1 of 5 (keyword returned 5) |
| quality estimation for machine translation | 47.9 | 216.7 | 0 of 5 (keyword returned 5) |
| adam optimizer | 47.7 | 209.5 | 2 of 5 (keyword returned 4) |
| speech translation | 48.0 | 213.0 | 0 of 5 (keyword returned 5) |

Top 5 by vector search (similarity = 1 - cosine distance):

**low-resource neural machine translation**

1. Low-Resource Neural Machine Translation: A Systematic Literature Review (2023), 0.975
2. Low-resource Neural Machine Translation: Methods and Trends (2022), 0.973
3. A Survey on Low-Resource Neural Machine Translation (2021), 0.972
4. Neural machine translation for low-resource languages (2017), 0.970
5. Neural Machine Translation for Low-resource Languages: A Survey (2022), 0.967

**back-translation for low-resource languages**

1. Survey of Low-Resource Machine Translation (2022), 0.953
2. Survey of Low-Resource Machine Translation (2021), 0.953
3. Survey of Low-Resource Machine Translation (2022), 0.952
4. Neural Machine Translation for Low-Resource Languages: Challenges and Solutions (2018), 0.947
5. Creating a High-Quality Machine Translation System for a Low-Resource Language: Yiddish (2009), 0.946

**multilingual pretraining for translation**

1. Cross-lingual Language Model Pretraining (2019), 0.956
2. Multilingual Neural Machine Translation for Low Resource Languages (2017), 0.956
3. Improving Neural Machine Translation Models with Monolingual Data (2016), 0.953
4. Exploiting Multilingualism and Transfer Learning for Low Resource Machine Translation (2018), 0.952
5. Google's Neural Machine Translation System: Bridging the Gap between Human and Machine Translat (2016), 0.951

**zero-shot translation**

1. Google’s Multilingual Neural Machine Translation System: Enabling Zero-Shot Translation (2017), 0.946
2. Multilingual Neural Machine Translation for Low-Resource Languages (2018), 0.933
3. A Comparison of Different NMT Approaches to Low-Resource Dutch-Albanian Machine Translation (2021), 0.932
4. Improving Zero-shot Multilingual Neural Machine Translation for Low-Resource Languages (2021), 0.932
5. Back-Translation Still Matters: Leveraging Monolingual Data for Low-Resource Machine Translatio (2026), 0.932

**unsupervised machine translation**

1. A Simplified Training Pipeline for Low-Resource and Unsupervised Machine Translation (2023), 0.945
2. Unsupervised Source Hierarchies for Low-Resource Neural Machine Translation (2018), 0.941
3. Neural Machine Translation for Low-Resource Languages: Challenges and Solutions (2018), 0.938
4. Neural Machine Translation for Low-Resource Languages from a Chinese-centric Perspective: A Sur (2024), 0.937
5. BLEU (2001), 0.937

**quality estimation for machine translation**

1. BLEU (2001), 0.961
2. Survey of Low-Resource Machine Translation (2022), 0.954
3. Survey of Low-Resource Machine Translation (2022), 0.954
4. Survey of Low-Resource Machine Translation (2021), 0.954
5. LIFT: A Quality-Aware Data Selection Framework for Low-Resource Machine Translation (2026), 0.947

**adam optimizer**

1. Adam: A Method for Stochastic Optimization (2015), 0.955
2. Decoupled Weight Decay Regularization (2017), 0.932
3. The Elements of Statistical Learning: Data Mining, Inference, and Prediction (2013), 0.927
4. Neural Networks: A Comprehensive Foundation (1998), 0.927
5. Statistical Learning Theory (1999), 0.925

**speech translation**

1. Speech Acts (1969), 0.930
2. Moses (2007), 0.930
3. Tacotron: Towards End-to-End Speech Synthesis (2017), 0.929
4. Neural Machine Translation for Low-Resource Languages: Challenges and Solutions (2018), 0.928
5. Machine Translation of Low-Resource Spoken Dialects: Strategies for Normalizing Swiss German (2018), 0.927

Top 5 by keyword search (ts_rank score):

**low-resource neural machine translation**

1. Based on Gated Dynamic Encoding Optimization, the LGE-Transformer Method for Low-Resource Neura (2024), 1.000
2. Low-Resource Neural Machine Translation: A Systematic Literature Review (2023), 1.000
3. A Joint Back-Translation and Transfer Learning Method for Low-Resource Neural Machine Translati (2020), 0.999
4. MTNLP-IIITH: Machine Translation for Low-Resource Indic Languages (2024), 0.999
5. Review of Research on Knowledge Distillation Methods for Low-Resource Machine Translation (2026), 0.999

**back-translation for low-resource languages**

1. A Joint Back-Translation and Transfer Learning Method for Low-Resource Neural Machine Translati (2020), 1.000
2. Evaluation of the effect of back-translation direction on machine translation quality for low-r (2025), 0.999
3. Back-Translation Still Matters: Leveraging Monolingual Data for Low-Resource Machine Translatio (2026), 0.998
4. Revisiting Back-Translation for Low-Resource Machine Translation Between Chinese and Vietnamese (2020), 0.997
5. Improving Low Resource Machine Translation via Round-Trip Reinforcement Learning (2026), 0.996

**multilingual pretraining for translation**

1. Low-Resource Machine Translation Systems for Indic Languages (2023), 0.668
2. IOL Research Machine Translation Systems for WMT23 Low-Resource Indic Language Translation Shar (2023), 0.628
3. A Data-Efficient Multilingual Neural Machine Translation Model for Low-Resource Indic Languages (2026), 0.406
4. Disentangling Pretrained Representation to Leverage Low-Resource Languages in Multilingual Mach (2024), 0.401
5. Disentangling Pretrained Representation to Incorporate Unseen Low-Resource Languages in Multili (2024), 0.384

**zero-shot translation**

1. Improving Zero-shot Multilingual Neural Machine Translation for Low-Resource Languages (2021), 0.980
2. Scaling Zero-shot Machine Translation on Low-Resource Languages with Linguistic Grammars (2026), 0.844
3. Google’s Multilingual Neural Machine Translation System: Enabling Zero-Shot Translation (2017), 0.839
4. Multilingual Neural Machine Translation for Low-Resource Languages (2018), 0.718
5. Fully Attentional Network for Low-Resource Academic Machine Translation and Post Editing (2022), 0.560

**unsupervised machine translation**

1. Machine Translation and Transliteration Involving Related and Low-resource Languages (2021), 0.745
2. Unsupervised Multimodal Machine Translation for Low-resource Distant Language Pairs (2024), 0.700
3. Visual Pivoting Unsupervised Multimodal Machine Translation in Low-Resource Distant Language Pa (2024), 0.564
4. Unsupervised Source Hierarchies for Low-Resource Neural Machine Translation (2018), 0.555
5. Cross-lingual Language Model Pretraining (2019), 0.519

**quality estimation for machine translation**

1. Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Estimation (2021), 0.957
2. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026), 0.861
3. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026), 0.861
4. Filtered Pseudo-parallel Corpus Improves Low-resource Neural Machine Translation (2019), 0.808
5. Quality Estimation for Machine Translation in Low-Resource Settings (2026), 0.781

**adam optimizer**

1. Adam: A Method for Stochastic Optimization (2015), 0.308
2. An explorative Investigation into Neural Machine Translation: the Case of Low-Resource Language (2020), 0.099
3. Transformer-Based Optimization for Text-to-Gloss in Low-Resource Neural Machine Translation (2025), 0.081
4. Decoupled Weight Decay Regularization (2017), 0.004

**speech translation**

1. AudioPaLM: A Large Language Model That Can Speak and Listen (2023), 0.441
2. Advances in natural language processing (2015), 0.338
3. XLS-R: Self-supervised Cross-lingual Speech Representation Learning at Scale (2022), 0.265
4. Transformer-Based Optimization for Text-to-Gloss in Low-Resource Neural Machine Translation (2025), 0.183
5. A Hybrid mT5-Based Machine Translation System for Kanuri–English Educational Translation in a L (2026), 0.181

(Titles are cut at 95 characters.)

### Results that look off-topic

The counts below are `ILIKE` counts on the title, and on title plus abstract, in `pc_pilot`.

- **quality estimation for machine translation:** by a strict title-keyword rule (the phrase must be in the title), the vector top 5 has no quality-estimation paper (BLEU, three records titled "Survey of Low-Resource Machine Translation", and a data-selection paper), while the keyword search finds real ones (e.g. "Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Estimation"). The corpus has 5 titles and 8 title-or-abstract mentions of "quality estimation" (a title-or-abstract rule finds 8 quality-estimation papers; `db/retrieval-diagnosis.md`), so there are papers to find. This is a vector miss by that strict rule. Likely cause (not tested): a short query, encoded without an abstract, lands near the dominant "machine translation, low-resource" region of this corpus.
- **back-translation for low-resource languages:** by a strict title-keyword rule, none of the vector top 5 is about back-translation (three "Survey of Low-Resource Machine Translation" records, two general low-resource MT papers), while four of the five keyword results are about back-translation (the fifth is about round-trip reinforcement learning). A title-or-abstract rule finds 75 back-translation papers, 16 of them with the phrase in the title (`db/retrieval-diagnosis.md`; the 13 titles and 59 mentions first reported here came from a pattern that missed "backtranslation"). Same likely cause.
- **speech translation:** the vector top 5 is off-topic ("Speech Acts" from 1969, Moses, Tacotron, two low-resource MT papers). The corpus has 0 titles and 3 title-or-abstract mentions of "speech translation", so there is almost nothing to retrieve; the keyword top 5 (AudioPaLM, XLS-R, ...) are the speech-related papers it has.
- **unsupervised machine translation:** the first two results are on topic; the fifth is "BLEU" (2001), a metric paper, and results 3 and 4 are general low-resource MT surveys. The corpus has 5 titles matching "unsupervised ... translation".
- **multilingual pretraining for translation:** looks reasonable (cross-lingual language model pretraining first); the keyword top 5 is weaker here (shared 0 of 5, scores 0.384 to 0.668).
- **adam optimizer:** the first result is the right paper (W2964121744, the kept Adam record) and the second is AdamW; results 3 to 5 are general machine-learning books. The keyword search returned only 4 rows, and two of them are unrelated low-resource MT papers.
- **Duplicates:** "Survey of Low-Resource Machine Translation" appears three times (W4283220248, W4225929449, W3198189804) in the top 5 of two queries. These are three records with different DOIs (a journal DOI, an arXiv DOI and a Zenodo DOI), so the loader did not reject them. I did not check whether they are versions of the same survey (see Known limits).
- **low-resource neural machine translation** looks on topic; **zero-shot translation** is mostly on topic (the first and fourth results name zero-shot translation, the others are multilingual or low-resource MT papers).

### EXPLAIN ANALYZE of a filtered vector query

Query "low-resource neural machine translation", `year >= 2020`, top 5, with `hnsw.ef_search = 100` and `hnsw.iterative_scan = strict_order`:

```
  Limit  (cost=405.67..437.14 rows=5 width=92) (actual time=0.698..0.805 rows=5 loops=1)
    Buffers: shared hit=646
    ->  Index Scan using idx_paper_embedding_hnsw on paper p  (cost=405.67..5628.91 rows=830 width=92) (actual time=0.697..0.802 rows=5 loops=1)
          Order By: (embedding <=> '[... 768 numbers ...]'::vector)
          Filter: ((embedding IS NOT NULL) AND (year >= '2020'::smallint))
          Rows Removed by Filter: 1
          Buffers: shared hit=646
  Planning:
    Buffers: shared hit=7
  Planning Time: 0.208 ms
  Execution Time: 0.823 ms
rows returned: 5
```

The HNSW index **was used** (`Index Scan using idx_paper_embedding_hnsw`), the year filter was applied to the index scan (1 row removed by the filter), and the filter did **not** return fewer than 5 rows (5 rows returned). Server-side execution time 0.823 ms.

**About the ~48 ms vector search time.** The server executes the vector query in about 1 ms (EXPLAIN ANALYZE above), but `search()` measured about 48 ms from Python. The cause is the size of the query parameter, not the index: against `pc_pilot`, `SELECT length(%s)` takes 0.3 to 0.4 ms for text parameters of up to 8,000 bytes and about 44 ms for 9,000 bytes or more, and the query vector is sent as 8,561 bytes of text. This is on a Windows host talking to the Docker container; I did not test other setups. Not fixed here (no code changes in Part 5).

## 4. Known limits

- **One duplicate record rejected.** 1,999 of 2,000 papers load. `W1522301498` is rejected as a duplicate DOI of `W2964121744` (the same Adam paper). The kept record has 0 references and no author affiliations, so its references are not loaded and citations to `W1522301498` are skipped. See `extraction/accuracy_report.md`. Other near-duplicate titles with different DOIs are not caught: 51 titles (compared case-insensitively) occur more than once among the loaded papers, including the three "Survey of Low-Resource Machine Translation" records above. Whether each is a true duplicate was not checked.
- **Citations stored vs skipped.** The file has 78,513 references; 11542 are stored and 66949 are skipped because the cited paper is not among the 1,999 loaded; the other 22 belong to the rejected record. The corpus covers only part of each paper's references, so citation counts inside the database are lower bounds.
- **Corpus skew.** 494 of 2,000 titles contain "low-resource"; Machine Translation covers 58.9% of the experiments and 31.9% have no task; only 40 of 1,055 experiments name a dataset.
- **Institutions.** 616 author institution conflicts (first value kept) and 2,396 of 8,157 authors with no institution; one institution is stored per author.
- **No retrieval accuracy measured.** The tables above are a spot check by eye of 8 queries; precision, recall and nDCG need the labeled query set, which does not exist yet. The two off-topic patterns found (short queries pulled toward the dominant theme, and little coverage for some topics such as speech translation) are observations, not measurements.
- **Query encoding.** Queries are encoded like papers; the `specter2_adhoc_query` adapter is not implemented.
- **Search latency.** About 48 ms per vector query from Python on this machine, caused by the size of the query parameter (see above); about 1 ms inside the database.

## 5. Query adapter (retrieval fixes, 2026-11-21)

Papers keep the stored proximity-adapter vectors (nothing was re-embedded and no stored vector was changed). Query text is now encoded with `allenai/specter2_adhoc_query` (revision `3f4448817028388648a74349ece07af4518ec5bd`, one 3,593,365-byte weights file downloaded from huggingface.co for this task) on the same pinned base model. The old behaviour stays selectable: `--query-adapter proximity` in `pilot_queries.py`, or `make_query_encoder("proximity")`, or the environment variable `PC_QUERY_ADAPTER=proximity` (an argument wins over the variable; the default for queries is `adhoc_query`). This section adds to sections 3 and 4; where "Query encoding" in section 4 says the adhoc adapter is not implemented, it is now.

**On-topic counts.** The same 8 queries, top 5 by vector search before (queries encoded like papers) and after (adhoc_query). A result counts as on-topic only if its full title matches a keyword rule, which is deliberately strict:

| Query | Rule (title, case-insensitive) |
| --- | --- |
| low-resource neural machine translation | "low-resource" or "low resource", and "neural machine translation" or "NMT" |
| back-translation for low-resource languages | "back-translation", "backtranslation" or "back translation" |
| multilingual pretraining for translation | "pretrain" or "pre-train", and one of multilingual, cross-lingual, monolingual, translation |
| zero-shot translation | "zero-shot" or "zero shot" |
| unsupervised machine translation | "unsupervised", and "translation" or "NMT" |
| quality estimation for machine translation | "quality estimation" |
| adam optimizer | the word "adam", or "optimi[sz]" |
| speech translation | "speech" and "translation" |

The rules miss papers that are on topic without those words (for example "Decoupled Weight Decay Regularization", which is AdamW, is not counted for "adam optimizer"), so the counts are lower bounds. They are a title check by one rule, not a relevance judgement.

| Query | on-topic in top 5: before | on-topic in top 5: after | top 5 shared before/after |
| --- | ---: | ---: | ---: |
| low-resource neural machine translation | 5 | 5 | 4 of 5 |
| back-translation for low-resource languages | 0 | 0 | 0 of 5 |
| multilingual pretraining for translation | 1 | 2 | 2 of 5 |
| zero-shot translation | 2 | 2 | 4 of 5 |
| unsupervised machine translation | 2 | 3 | 2 of 5 |
| quality estimation for machine translation | 0 | 1 | 1 of 5 |
| adam optimizer | 1 | 1 | 2 of 5 |
| speech translation | 0 | 0 | 1 of 5 |
| **total (of 40)** | 11 | 14 | |

**Are the two misses fixed?**

- **quality estimation for machine translation: partly.** By the strict title rule, the top 5 had 0 papers with "quality estimation" in the title before and has 1 after ("Quality Estimation for Machine Translation in Low-Resource Settings", rank 3). The corpus has 5 such papers by this title rule (a title-or-abstract rule finds 8); their ranks over all 1,999 papers went from [7, 18, 31, 36, 67] to [3, 8, 9, 22, 26]. Only the adapter changed between the two runs (same query text, same stored vectors), so this change comes from the adapter.
- **back-translation for low-resource languages: not fixed.** 0 on-topic results in the top 5 before and after, by the strict title rule (a title-or-abstract rule finds 75 back-translation papers). None of the 16 papers whose title contains back-translation is in the top 5, or the top 20, under either adapter; the best rank moved from 53 to 49. The adapter therefore did not fix this miss and I do not claim it as the cause or the cure.

**What I tried for the back-translation miss, and the evidence.** The ranks below are over all 1,999 papers (1 = best) for the papers whose title contains the phrase (16 for back-translation, 5 for quality estimation), using cosine similarity to the stored vectors:

| Query encoding | Phrase | Ranks of the target papers | In top 5 | In top 20 |
| --- | --- | --- | ---: | ---: |
| proximity, query as given | back-translation | [53, 58, 60, 82, 95, 144, 181, 195, 220, 250, 282, 299, 349, 446, 512, 820] | 0 | 0 |
| proximity, query as given | quality estimation | [7, 18, 31, 36, 67] | 0 | 2 |
| adhoc_query, query as given | back-translation | [49, 54, 66, 81, 117, 128, 129, 132, 161, 186, 196, 220, 377, 422, 499, 557] | 0 | 0 |
| adhoc_query, query as given | quality estimation | [3, 8, 9, 22, 26] | 1 | 3 |
| adhoc_query, short phrase | back-translation | [3, 18, 48, 54, 69, 76, 87, 99, 159, 178, 189, 201, 310, 340, 341, 414] | 1 | 2 |
| adhoc_query, short phrase | quality estimation | [15, 16, 41, 443, 454] | 0 | 2 |
| proximity, short phrase | back-translation | [9, 51, 67, 72, 98, 105, 109, 115, 116, 118, 119, 152, 233, 406, 427, 528] | 0 | 1 |
| proximity, short phrase | quality estimation | [261, 274, 276, 785, 1423] | 0 | 0 |

Encoding only the short phrase "back-translation" puts one target paper at rank 3 with the adhoc adapter (and at rank 9 with the proximity adapter), while the full query "back-translation for low-resource languages" puts the best one at rank 49 or 53. That is consistent with the words "for low-resource languages" pulling the query toward the dominant low-resource theme of this corpus (494 of 2,000 titles contain "low-resource"), but I did not test that cause directly. It also means the result depends on how the query is phrased, which an adapter cannot fix; a short-phrase query, a keyword or hybrid ranking, or query understanding on top would be the next things to try. Not done here.

**Caveats.** Same corpus skew as before. The on-topic counts use 8 queries and a strict title rule, so a change of one or two results is within what a different rule could move. Similarity scores are lower with the adhoc adapter (about 0.78 to 0.86 against about 0.92 to 0.98 before) because query and paper vectors now come from different adapters; only the order matters for ranking, and the scores of the two encodings should not be compared with each other.

## 6. Query latency (retrieval fixes, 2026-11-21)

The query vector used to be sent as an 8,561-byte text parameter, which cost about 44 ms on this Windows-to-Docker setup (section 3). `search()` now sends it in binary format as a `real[]` of float4 values (about 3 KB) and casts it in SQL (`%b::real[]::vector`), using `retrieval.search.vector_parameter()`. No new package is needed (the pgvector Python adapter is not installed). `check_query_vector()` (the text form) is kept but `search()` no longer uses it.

Median of 5 runs after one warm-up for each of the 8 queries, `search(top_k=5)` on `pc_pilot`, query vectors from the adhoc_query encoder; "before" is the `search()` of `origin/main` at the start of this task, "after" the new one, both run in the same session against the same database:

| Query | Before (text parameter) ms | After (binary parameter) ms | Same ids and order | Max score difference |
| --- | ---: | ---: | :---: | ---: |
| low-resource neural machine translation | 47.6 | 3.0 | yes | 0.00e+00 |
| back-translation for low-resource languages | 44.8 | 2.5 | yes | 0.00e+00 |
| multilingual pretraining for translation | 44.2 | 2.7 | yes | 0.00e+00 |
| zero-shot translation | 47.7 | 2.5 | yes | 0.00e+00 |
| unsupervised machine translation | 45.8 | 2.2 | yes | 0.00e+00 |
| quality estimation for machine translation | 46.9 | 4.2 | yes | 0.00e+00 |
| adam optimizer | 47.6 | 3.6 | yes | 0.00e+00 |
| speech translation | 45.9 | 2.4 | yes | 0.00e+00 |
| median over the 8 queries | 46.4 | 2.6 | | |

The ids and their order are identical for all 8 queries, and the maximum score difference is 0 (the tests also check scores within 1e-6 on synthetic data). The HNSW index is still used for the ordering with the new parameter form (test with the index forced as the only ordering path). Only `search()` was changed; other code with its own vector SQL (for example in `rag/`) is not touched.

This replaces the "Search latency" bullet of section 4 and the explanation of the ~48 ms in section 3: after the change the vector search takes about 2 to 4 ms from Python on this machine, which was measured on this one Windows setup only.

## 7. Same-title collapse (TEMPORARY WORKAROUND, retrieval fixes, 2026-11-21)

**This is a workaround, not a fix.** 51 titles occur more than once among the loaded papers (section 4), because the same paper appears as several OpenAlex records with different ids and DOIs. The real fix is de-duplication at ingest (Person 1; see `extraction/accuracy_report.md`, Limitations). Until then, `search(..., collapse_same_title=True)` and `keyword_search(..., collapse_same_title=True)` (CLI: `--collapse-titles`; `pilot_queries.py --collapse-titles`) keep only the best-scored record per normalized title (lowercase, punctuation stripped, whitespace collapsed; hyphens are stripped without leaving a space, so "Low-Resource" becomes "lowresource"). The default is **off**, so existing behaviour and tests do not change. No row is deleted or merged; the hidden records are still in the database and still returned when the option is off.

How it works: the search fetches more candidates than asked for (at least 5 times the requested count, at most 5,000), keeps the best-scored record per normalized title, and trims to the requested number, so it still returns `top_k` results when enough distinct titles exist (and fewer only when they do not). `offset` applies to the collapsed list. When two records have exactly the same score (for example identical vectors), the smaller `paper_id` is kept so the choice is stable; in the pilot database the records W4225929449 and W4283220248 have the same similarity to the back-translation query to six decimals, so which of them survives is decided by this rule and not by relevance. Titles that differ in more than punctuation, case and spacing (a subtitle, a different word) are not collapsed.

**Where duplicates appeared in the top 5** (8 pilot queries; vector search with the old proximity query encoding, with the new adhoc_query encoding, and keyword search):

- vector, proximity encoding: 2 of 8 queries had repeated titles;
- vector, adhoc_query encoding (the new default): 0 of 8 queries;
- keyword: 1 of 8 queries.

So with the new query encoding the pilot queries no longer show duplicates in the top 5, and the collapse changes nothing for them. The cases below are the ones where it did something:

**back-translation for low-resource languages** (vector, proximity): repeated titles in the top 5 2 before, 0 after; results returned 5 before, 5 after.

| Before | After |
| --- | --- |
| 1. W4283220248 (2022) Survey of Low-Resource Machine Translation | 1. W4225929449 (2021) Survey of Low-Resource Machine Translation |
| 2. W4225929449 (2021) Survey of Low-Resource Machine Translation | 2. W7117761584 (2018) Neural Machine Translation for Low-Resource Languages: Challenges and Solutions |
| 3. W3198189804 (2022) Survey of Low-Resource Machine Translation | 3. W2899317740 (2009) Creating a High-Quality Machine Translation System for a Low-Resource Language: |
| 4. W7117761584 (2018) Neural Machine Translation for Low-Resource Languages: Challenges and Solutions | 4. W2745341416 (2017) Neural machine translation for low-resource languages |
| 5. W2899317740 (2009) Creating a High-Quality Machine Translation System for a Low-Resource Language: | 5. W4225670297 (2021) Lesan -- Machine Translation for Low Resource Languages |

**quality estimation for machine translation** (vector, proximity): repeated titles in the top 5 2 before, 0 after; results returned 5 before, 5 after.

| Before | After |
| --- | --- |
| 1. W2101105183 (2001) BLEU | 1. W2101105183 (2001) BLEU |
| 2. W3198189804 (2022) Survey of Low-Resource Machine Translation | 2. W3198189804 (2022) Survey of Low-Resource Machine Translation |
| 3. W4283220248 (2022) Survey of Low-Resource Machine Translation | 3. W7155070965 (2026) LIFT: A Quality-Aware Data Selection Framework for Low-Resource Machine Translat |
| 4. W4225929449 (2021) Survey of Low-Resource Machine Translation | 4. W2123301721 (2005) METEOR: An Automatic Metric for MT Evaluation with Improved Correlation with Hum |
| 5. W7155070965 (2026) LIFT: A Quality-Aware Data Selection Framework for Low-Resource Machine Translat | 5. W7204966702 (2026) Quality Estimation for Machine Translation in Low-Resource Settings |

**quality estimation for machine translation** (keyword): repeated titles in the top 5 1 before, 0 after; results returned 5 before, 5 after.

| Before | After |
| --- | --- |
| 1. W3161646700 (2021) Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Es | 1. W3161646700 (2021) Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Es |
| 2. W7140086055 (2026) Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scena | 2. W7140086055 (2026) Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scena |
| 3. W7134820529 (2026) Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scena | 3. W2986030184 (2019) Filtered Pseudo-parallel Corpus Improves Low-resource Neural Machine Translation |
| 4. W2986030184 (2019) Filtered Pseudo-parallel Corpus Improves Low-resource Neural Machine Translation | 4. W7204966702 (2026) Quality Estimation for Machine Translation in Low-Resource Settings |
| 5. W7204966702 (2026) Quality Estimation for Machine Translation in Low-Resource Settings | 5. W7132432999 (2022) Translation memories as baselines for low-resource machine translation |

The collapsed lists still have 5 results; the extra candidates come from just below the original top 5.

## 8. Hybrid search (optional, default off; retrieval fixes, 2026-11-21)

`retrieval.search.search_hybrid(conn, text, query_vector, top_k=10, n_candidates=50, rrf_k=60, year_min, year_max, collapse_same_title)` takes the top 50 of vector search and the top 50 of keyword search and fuses them with reciprocal rank fusion: a paper's fused score is the sum, over the lists that contain it, of 1 / (60 + rank). A paper found by only one method still appears; equal scores are ordered by the smaller `paper_id`. Each result carries its vector rank, keyword rank and fused score (a rank is `None` when the paper is not in that list). On the command line it is `python -m retrieval search --mode hybrid --vector-file q.json --text "..."`; the default mode is `vector`, unchanged, and `search()` and `keyword_search()` are not modified. Nothing else (the demo, any caller) uses hybrid mode: it is **off unless asked for**.

Run on `pc_pilot` (read only) by `db/retrieval/pilot_hybrid.py`: the 8 pilot queries plus "back-translation" (the other two requested queries are among the 8, so there are 9 distinct queries). Queries are encoded with the adhoc_query adapter. Latency is the median of 5 runs after one warm-up, database calls only (hybrid = one vector query plus one keyword query):

| Query | Vector ms | Keyword ms | Hybrid ms |
| --- | ---: | ---: | ---: |
| low-resource neural machine translation | 3.0 | 261.5 | 273.9 |
| back-translation for low-resource languages | 2.3 | 232.5 | 242.8 |
| multilingual pretraining for translation | 2.1 | 228.1 | 236.0 |
| zero-shot translation | 2.1 | 227.4 | 237.0 |
| unsupervised machine translation | 2.6 | 231.2 | 240.0 |
| quality estimation for machine translation | 2.5 | 228.3 | 235.0 |
| adam optimizer | 2.5 | 227.3 | 236.0 |
| speech translation | 2.4 | 231.8 | 239.4 |
| back-translation | 3.1 | 239.0 | 245.9 |

The keyword search computes its full-text vectors on the fly (no index), so it dominates the hybrid time; the vector part is a few milliseconds.

Top 5 titles for the back-translation and quality-estimation queries (hybrid entries show the rank in each list; a dash means not in that list's top 50):

**back-translation for low-resource languages**

Vector:

1. Are Small Language Models the Silver Bullet to Low-Resource Languages Machine Translation? (2026)
2. Low-resource Machine Translation: what for? who for? An observational study on a dedicated Tetun lan (2025)
3. Machine Translation for Low-Resource Languages through Monolingual Data and LLM: A Case Study of Eng (2026)
4. Benchmarking Low-Resource Machine Translation Systems (2024)
5. Tulun: Transparent and Adaptable Low-resource Machine Translation (2025)

Keyword:

1. A Joint Back-Translation and Transfer Learning Method for Low-Resource Neural Machine Translation (2020)
2. Evaluation of the effect of back-translation direction on machine translation quality for low-resour (2025)
3. Back-Translation Still Matters: Leveraging Monolingual Data for Low-Resource Machine Translation wit (2026)
4. Revisiting Back-Translation for Low-Resource Machine Translation Between Chinese and Vietnamese (2020)
5. Improving Low Resource Machine Translation via Round-Trip Reinforcement Learning (2026)

Hybrid:

1. Investigating Neural Machine Translation for Low-Resource Languages: Using Bavarian as a Case Study (2024)[vector rank 19, keyword rank 8]
2. Exploring Low-Resource Machine Translation: Case Study of Lao-Vietnamese Translation (2024)[vector rank 21, keyword rank 11]
3. Neural machine translation for low-resource languages without parallel corpora (2017)[vector rank 30, keyword rank 13]
4. Low-Resource Machine Translation for Moroccan Arabic (2025)[vector rank 44, keyword rank 29]
5. A Joint Back-Translation and Transfer Learning Method for Low-Resource Neural Machine Translation (2020)[vector rank -, keyword rank 1]

**quality estimation for machine translation**

Vector:

1. Translation or Recitation? Calibrating Evaluation Scores for Machine Translation of Extremely Low-Re (2026)
2. BLEU (2001)
3. Quality Estimation for Machine Translation in Low-Resource Settings (2026)
4. Benchmarking Low-Resource Machine Translation Systems (2024)
5. Low-resource Machine Translation: what for? who for? An observational study on a dedicated Tetun lan (2025)

Keyword:

1. Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Estimation (2021)
2. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026)
3. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026)
4. Filtered Pseudo-parallel Corpus Improves Low-resource Neural Machine Translation (2019)
5. Quality Estimation for Machine Translation in Low-Resource Settings (2026)

Hybrid:

1. Quality Estimation for Machine Translation in Low-Resource Settings (2026)[vector rank 3, keyword rank 5]
2. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026)[vector rank 8, keyword rank 2]
3. Domain-Specific Quality Estimation for Machine Translation in Low-Resource Scenarios (2026)[vector rank 9, keyword rank 3]
4. Ensemble-based Transfer Learning for Low-resource Machine Translation Quality Estimation (2021)[vector rank 22, keyword rank 1]
5. A Systematic Review on Translation of Low Resource Languages Using Machine Translation System with R (2025)[vector rank 26, keyword rank 7]

**back-translation**

Vector:

1. Tulun: Transparent and Adaptable Low-resource Machine Translation (2025)
2. Neural Machine Translation for Low-Resource Languages: Challenges and Solutions (2018)
3. Neural Machine Translation of Low-Resource and Similar Languages with Backtranslation (2019)
4. Machine Translation for Low-Resource Languages through Monolingual Data and LLM: A Case Study of Eng (2026)
5. Low-resource Machine Translation: what for? who for? An observational study on a dedicated Tetun lan (2025)

Keyword:

1. A Hybrid Approach for Improved Low Resource Neural Machine Translation using Monolingual Data (2020)
2. Iterative Self-Learning for Enhanced Back-Translation in Low Resource Neural Machine Translation. (2020)
3. Evaluation of the effect of back-translation direction on machine translation quality for low-resour (2025)
4. Using Self-Training to Improve Back-Translation in Low Resource Neural Machine Translation (2020)
5. Revisiting Back-Translation for Low-Resource Machine Translation Between Chinese and Vietnamese (2020)

Hybrid:

1. Rethinking the Exploitation of Monolingual Data for Low-Resource Neural Machine Translation (2023)[vector rank 12, keyword rank 20]
2. Exploiting Out-of-Domain Parallel Data through Multilingual Transfer Learning for Low-Resource Neura (2019)[vector rank 30, keyword rank 8]
3. A Joint Back-Translation and Transfer Learning Method for Low-Resource Neural Machine Translation (2020)[vector rank 48, keyword rank 6]
4. Investigating Neural Machine Translation for Low-Resource Languages: Using Bavarian as a Case Study (2024)[vector rank 29, keyword rank 21]
5. Handling Syntactic Divergence in Low-resource Machine Translation (2019)[vector rank 32, keyword rank 22]

**Counts with a lexical rule.** Papers matching the rule of `db/retrieval-diagnosis.md` (the phrase back-translation, or quality estimation, in the title or abstract) in the top 5 and top 10 of each mode:

| Query | Papers matching the rule | vector top 5 | vector top 10 | keyword top 5 | keyword top 10 | hybrid top 5 | hybrid top 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| back-translation for low-resource languages | 75 | 0 | 0 | 5 | 10 | 4 | 6 |
| quality estimation for machine translation | 8 | 1 | 3 | 5 | 7 | 5 | 6 |
| back-translation | 75 | 1 | 1 | 5 | 10 | 5 | 9 |

**How to read this. The rule is lexical, so it favours keyword search, and this is not a blind evaluation.** The rule is made of the same words that keyword search matches, so keyword search is expected to score well on it; a high count shows that the paper contains the phrase, not that a person would judge it relevant. On these three queries the hybrid lists contain more rule-matching papers than vector search alone, but not more than keyword search alone (hybrid 4 of 5 against keyword 5 of 5 for "back-translation for low-resource languages"; 5 against 5 for the other two). The data also show a property of the fusion: a paper that one method ranks first and the other does not list at all gets at most 1/61, and can fall behind papers that are only mid-ranked in both lists (for "back-translation for low-resource languages", the paper ranked first by keyword search is fifth in the hybrid list, behind four papers with vector ranks 19 to 44 and keyword ranks 8 to 29).

**What has not been measured.** The benefit of hybrid mode has not been measured with blind labels: no human relevance judgements were used, and the 3 queries are a small set. Whether hybrid mode should be used anywhere, and with which parameters, needs the labelled query set.
