# ingest/

Ingestion pipeline for Paper Compass (Person 1).

Fetches research papers from OpenAlex, cleans metadata, reconstructs abstracts from inverted indexes, normalizes venue types, extracts author IDs and institutions, and emits JSON Lines adhering to Person 2's loader specifications (`db/proposals/paper-metadata-format.md`).

---

## 1. Multi-Stream Ingestion Architecture (Item 1)

To overcome pilot corpus insularity (where 494/500 papers were low-resource MT with only 7.4% internal citations), the ingestion pipeline uses a multi-stream query strategy across OpenAlex structured concept IDs:

1. **Stream 1: Seed MT (`search="machine translation low-resource"`)** — 500 low-resource MT papers forming the initial seed corpus.
2. **Stream 2: Foundational MT Top-Cited (`concepts.id:C204321447`)** — Top-cited machine translation works across NLP history (sorted by `cited_by_count:desc`).
3. **Stream 3: Recent MT Advances (`concepts.id:C204321447`, 2020–2026)** — Modern neural translation architectures, multilingual models, and benchmark evaluation papers.
4. **Stream 4: Representation Learning & Pre-training (`concepts.id:C41008148`)** — Foundational NLP pretraining works (e.g. BERT, RoBERTa, Transformers, GloVe, Word2Vec) that MT architectures heavily cite.
5. **Stream 5: Speech Translation & Audio-to-Text (`concepts.id:C28490314`)** — Multimodal and speech-to-text translation systems.
6. **Stream 6: Question Answering & Natural Language Understanding (`concepts.id:C199360897`)** — QA, reading comprehension, and cross-lingual NLI transfer papers.

### Scaling & Citation Connectivity

- **Total Unique Papers:** 2,000
- **Total Authors:** 10,679
- **Total Citation References:** 78,513
- **Internal Corpus Citations:** 11,681
- **Internal Citation Density:** **14.88%** (more than doubled from 7.4% in the 500-paper pilot).

---

## 2. Corpus Distributions

### Year Distribution

The 2,000-paper corpus spans foundational NLP (1950s–2000s) to modern transformer architectures (2017–2026):

| Epoch | Years | Paper Count |
| :--- | :--- | :---: |
| Historical / Foundational | 1951 – 1999 | 338 |
| Statistical MT & Early Neural | 2000 – 2016 | 450 |
| Transformer & Pretraining Emergence | 2017 – 2019 | 216 |
| Modern Deep Learning & LLMs | 2020 – 2026 | 988 |
| Undated / Missing | — | 8 |

### Task Distribution (from Extractions)

| Task | Extraction Count | Share |
| :--- | :---: | :---: |
| **Machine Translation** | 618 | 86.4% |
| **Language Modeling** | 38 | 5.3% |
| **Question Answering** | 10 | 1.4% |
| **Cross-Lingual Transfer** | 9 | 1.3% |
| **Quality Estimation** | 7 | 1.0% |
| **Text Classification** | 7 | 1.0% |
| **Natural Language Inference** | 5 | 0.7% |
| **Text Summarization** | 5 | 0.7% |
| **Named Entity Recognition** | 4 | 0.6% |
| **Sentiment Analysis** | 4 | 0.6% |
| Other Tasks | 8 | 1.1% |

### Setting Distribution (from Extractions)

| Setting | Extraction Count | Share |
| :--- | :---: | :---: |
| **Low-resource** | 451 | 62.2% |
| **Multilingual** | 77 | 10.6% |
| **Supervised** | 42 | 5.8% |
| **Zero-shot** | 39 | 5.4% |
| **Cross-lingual** | 29 | 4.0% |
| **High-resource** | 24 | 3.3% |
| **Unsupervised** | 21 | 2.9% |
| **Bilingual** | 19 | 2.6% |
| **Semi-supervised** | 10 | 1.4% |
| **In-domain** | 6 | 0.8% |
| Other Settings | 7 | 1.0% |

---

## 3. Quickstart & Usage

Run from repository root:

```powershell
# Fetch / scale papers from OpenAlex
python ingest/fetch_openalex.py --count 2000 --out ingest/data/papers_pilot.jsonl

# Validate loader compliance
python db/test_pilot_loaders.py
```

## Schema output

Every line in `papers_pilot.jsonl` is a JSON object with:
- `paper_id`: Clean OpenAlex work ID (e.g. `W3123456789`)
- `title`: Paper title
- `abstract`: Full text reconstructed from inverted index (or null)
- `year`: Publication year (1950..2100)
- `doi`: Clean DOI (e.g. `10.1234/...`)
- `venue`: Venue display name
- `venue_type`: One of `conference`, `journal`, `workshop`, `preprint`, `other`
- `authors`: List of authors with `name`, `external_id` (OpenAlex `A...` ID), `institution`, and 1-based `order`
- `references`: List of cited `paper_id` strings (`W...`)
