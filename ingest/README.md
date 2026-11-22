# ingest/

Ingestion and deduplication pipeline for Paper Compass (Person 1).

Fetches research papers from OpenAlex, cleans metadata, reconstructs abstracts from inverted indexes, normalizes venue types, extracts author IDs and institutions, merges duplicates, remaps citations, and emits JSON Lines adhering to Person 2's loader specifications (`db/proposals/paper-metadata-format.md`).

---

## 1. Multi-Stream Ingestion Architecture (Item 1)

To overcome pilot corpus insularity (where 494/500 papers were low-resource MT with only 7.4% internal citations), the ingestion pipeline uses a multi-stream query strategy across OpenAlex structured concept IDs:

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
  - **Internal Corpus Citation Edges:** 11,636 (**14.88% internal density**)

---

## 3. Corpus Direction Decision (Item 3)

- **Finding:** 461 of 1,975 papers (23.3%) specifically focus on low-resource MT. Retrieval queries in `db/retrieval-diagnosis.md` for "speech translation" (3 papers) and "quality estimation" (7 papers) suffered from retrieval starvation.
- **Team Decision:** Retain low-resource MT as the primary anchor domain, while enriching targeted streams for evaluation topics (`speech translation`, `quality estimation`) to ensure the retrieval benchmark and discovery pipeline have non-empty result sets.

---

## 4. Corpus Distributions (Deduplicated 1,975 Papers)

### Year Distribution

| Epoch | Years | Paper Count |
| :--- | :--- | :---: |
| Historical / Foundational | 1951 – 1999 | 348 |
| Statistical MT & Early Neural | 2000 – 2016 | 465 |
| Transformer & Pretraining Emergence | 2017 – 2019 | 214 |
| Modern Deep Learning & LLMs | 2020 – 2026 | 940 |
| Undated / Missing | — | 8 |

### Task Distribution (from Extractions)

| Task | Extraction Count | Share |
| :--- | :---: | :---: |
| **Machine Translation** | 609 | 58.9% |
| **Language Modeling** | 38 | 3.7% |
| **Question Answering** | 10 | 1.0% |
| **Cross-Lingual Transfer** | 9 | 0.9% |
| **Quality Estimation** | 7 | 0.7% |
| **Text Classification** | 7 | 0.7% |
| **Natural Language Inference** | 5 | 0.5% |
| **Text Summarization** | 5 | 0.5% |
| **Named Entity Recognition** | 4 | 0.4% |
| **Part-of-Speech Tagging** | 4 | 0.4% |
| Other Tasks | 2 | 0.2% |
| *No task* | 333 | 32.2% |

### Setting Distribution (from Extractions)

| Setting | Extraction Count | Share |
| :--- | :---: | :---: |
| **Low-resource** | 451 | 43.7% |
| **Multilingual** | 73 | 7.1% |
| **Supervised** | 42 | 4.1% |
| **Zero-shot** | 39 | 3.8% |
| **Cross-lingual** | 29 | 2.8% |
| **High-resource** | 24 | 2.3% |
| **Bilingual** | 19 | 1.8% |
| **Unsupervised** | 16 | 1.5% |
| **Semi-supervised** | 10 | 1.0% |
| **In-domain** | 6 | 0.6% |
| Other Settings | 1 | 0.1% |
| *No setting* | 323 | 31.3% |

---

## 5. Quickstart & Verification

```powershell
# 1. Run deduplication and citation remapping
python ingest/deduplicate.py

# 2. Verify corpus and loader integrity
python ingest/test_pilot_integrity.py
```
