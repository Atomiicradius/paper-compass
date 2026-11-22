# ingest/

Ingestion and deduplication pipeline for Paper Compass (Person 1).

Fetches research papers from OpenAlex, cleans metadata, reconstructs abstracts from inverted indexes, normalizes venue types, extracts author IDs and institutions, merges duplicates, remaps citations, and emits JSON Lines adhering to Person 2's loader specifications (`db/proposals/paper-metadata-format.md`).

---

## 1. Multi-Stream Ingestion Architecture (Item 1)

To overcome pilot corpus insularity (where 494/500 papers were low-resource MT with only 7.4% internal citations; this is from the first 500-paper pilot corpus, which is not in the repository, so it was not recomputed), the ingestion pipeline uses a multi-stream query strategy across OpenAlex structured concept IDs:

1. **Stream 1: Seed MT (`search="machine translation low-resource"`)** — 500 low-resource MT papers forming the initial seed corpus.
2. **Stream 2: Foundational MT Top-Cited (`concepts.id:C204321447`)** — Top-cited machine translation works across NLP history (sorted by `cited_by_count:desc`).
3. **Stream 3: Recent MT Advances (`concepts.id:C204321447`, 2020–2026)** — Modern neural translation architectures, multilingual models, and benchmark evaluation papers.
4. **Stream 4: Representation Learning & Pre-training (`concepts.id:C41008148`)** — Foundational NLP pretraining works (e.g. BERT, RoBERTa, Transformers, GloVe, Word2Vec) that MT architectures heavily cite.
5. **Stream 5: Speech Translation & Audio-to-Text (`concepts.id:C28490314`)** — Multimodal and speech-to-text translation systems.
6. **Stream 6: Question Answering & Natural Language Understanding (`concepts.id:C199360897`)** — QA, reading comprehension, and cross-lingual NLI transfer papers.

---

## 2. Ingestion De-duplication (Items 1 & 2 Completed)

Implemented in [`ingest/deduplicate.py`](deduplicate.py):
- **Pass 1: Shared DOI Merge:** Records sharing a DOI are merged. The record with more references and fuller authorship metadata is retained (e.g., Adam `W1522301498` references and affiliations merged into `W2964121744`).
- **Pass 2: Repeated Titles with Different DOIs:** Papers sharing a normalized title are evaluated for author overlap, abstract similarity, and year proximity ($|y_1 - y_2| \le 3$). Published conference/journal records are favored over arXiv preprints or repository entries (e.g. 3 copies of "Survey of Low-Resource Machine Translation" merged into `W3198189804`; FLORES-101 preprint merged into `W3169369929`).
- **Citation Remapping:** All citations across the corpus pointing to dropped IDs are remapped to the kept IDs. If a target is in the corpus, the edge is preserved; self-citations are dropped.
- **Deduplication Audit Trail:** Full merge log saved to [`ingest/data/deduplication_log.json`](data/deduplication_log.json).
  - **Initial Papers:** 2,000
  - **Duplicates Merged:** 25
  - **Final Unique Papers:** **1,975**
  - **Citations Remapped:** 179
  - **Internal Corpus Citation Edges in the final file:** 11,523 of 78,188 references (**14.74%**). (`deduplicate.py` prints 11,636 because it counts an edge before repeated edges are merged, and the 14.88% in decision 26 was measured on the earlier 2,000-paper corpus: 11,681 of 78,513.)

---

## 3. Corpus Direction Decision (Item 3)

- **Finding:** 485 of 1,975 papers (24.6%) mention both "low-resource" and "machine translation" in the title or abstract (477, or 24.2%, have "low-resource" in the title). Both figures count a match of those words, not a reading of each paper. Quality estimation is rare: `db/retrieval-diagnosis.md` finds 5 papers with the phrase in the title and 8 in the title or abstract on `pc_pilot` (1,999 papers); this folder's 1,975 papers have 7 in the title or abstract. A keyword search of title and abstract finds 7 papers on speech translation, which that diagnosis does not cover.
- **Decision (decision 39):** Retain low-resource MT as the primary anchor domain. Enriching the corpus for `speech translation` and `quality estimation`, so that the retrieval benchmark and discovery pipeline have non-empty result sets, is **proposed and not done yet**: the corpus in this folder has no paper that was not in the earlier 2,000-paper corpus (0 added, 25 duplicates dropped). The OpenAlex queries to add have still to be chosen.

---

## 4. Corpus Distributions (Deduplicated 1,975 Papers)

### Year Distribution

| Epoch | Years | Paper Count |
| :--- | :--- | :---: |
| Historical / Foundational | 1951 – 1999 | 349 |
| Statistical MT & Early Neural | 2000 – 2016 | 474 |
| Transformer & Pretraining Emergence | 2017 – 2019 | 215 |
| Modern Deep Learning & LLMs | 2020 – 2026 | 929 |
| Undated / Missing | — | 8 |

### Task Distribution (from the 1,033 extraction rows)

| Task | Extraction Count | Share |
| :--- | :---: | :---: |
| **Machine Translation** | 604 | 58.5% |
| **Language Modeling** | 38 | 3.7% |
| **Question Answering** | 10 | 1.0% |
| **Cross-Lingual Transfer** | 9 | 0.9% |
| **Text Classification** | 7 | 0.7% |
| **Quality Estimation** | 5 | 0.5% |
| **Natural Language Inference** | 5 | 0.5% |
| **Text Summarization** | 5 | 0.5% |
| **Named Entity Recognition** | 4 | 0.4% |
| **Part-of-Speech Tagging** | 4 | 0.4% |
| **Sentiment Analysis** | 4 | 0.4% |
| **Paraphrase Generation** | 3 | 0.3% |
| **Automatic Post-Editing** | 1 | 0.1% |
| **Word Alignment** | 1 | 0.1% |
| *No task* | 333 | 32.2% |

### Setting Distribution (from the 1,033 extraction rows)

| Setting | Extraction Count | Share |
| :--- | :---: | :---: |
| **Low-resource** | 447 | 43.3% |
| **Multilingual** | 72 | 7.0% |
| **Supervised** | 41 | 4.0% |
| **Zero-shot** | 39 | 3.8% |
| **Cross-lingual** | 29 | 2.8% |
| **High-resource** | 24 | 2.3% |
| **Bilingual** | 19 | 1.8% |
| **Unsupervised** | 16 | 1.5% |
| **Semi-supervised** | 10 | 1.0% |
| **In-domain** | 6 | 0.6% |
| **Out-of-domain** | 4 | 0.4% |
| **Few-shot** | 3 | 0.3% |
| *No setting* | 323 | 31.3% |

---

## 5. Quickstart & Verification

```powershell
# 1. Run deduplication and citation remapping.
#    CAUTION: it reads and OVERWRITES ingest/data/papers_pilot.jsonl, extraction/data/extractions_pilot.jsonl and
#    ingest/data/deduplication_log.json. It is meant to run once, on the original 2,000-paper file. Run again on the
#    deduplicated file it finds 0 duplicates and rewrites the audit log with zeros (the papers file does not change).
python ingest/deduplicate.py

# 2. Verify corpus and loader integrity
python ingest/test_pilot_integrity.py
```

Checked on 2026-11-22: `deduplicate.py` run twice on the original 2,000-paper file (taken from `origin/main`) wrote byte-identical papers, extractions and log, and the papers and log equal the committed files. Its extractions output (1,042 tuples) is not the committed extractions file: that file (1,033 tuples) is the output of `extraction/extract.py` run on the deduplicated corpus.
