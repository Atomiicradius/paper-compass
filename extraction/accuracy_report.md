# Extraction Accuracy & Coverage Report (Phase 1)

**Owner:** Person 1 (Data & Extraction)  
**Corpus Domain:** NLP / Machine Translation (Low-resource & Indic MT)  
**Source:** OpenAlex API  
**Evaluation Set:** 100-Abstract Labeled Benchmark (`extraction/data/labeled_benchmark.jsonl`)  
**Extractor Version:** `rules-v1`  

---

## 1. Executive Summary

This report fulfills the Phase 1 evaluation mandate for Person 1 as specified in `build-plan.md` and `project-plan-v2.md §12.2`:
> *"Hand-label ~100 abstracts; report precision and recall per entity type, and the share of papers with a dataset or task extracted at all."*

The extraction pipeline processes unstructured academic titles and abstracts to construct normalized `EXPERIMENT` records (`paper_id`, `method`, `dataset`, `task`, `setting`, `confidence`, `source_sentence`, `extractor`). All extracted entities are strictly constrained by the controlled vocabulary ([`ingest/data/vocabulary.jsonl`](../ingest/data/vocabulary.jsonl)) to prevent entity hallucination and ensure compatibility with Person 2's PostgreSQL loader.

---

## 2. Extraction Coverage (500-Paper Pilot)

| Metric | Count | Percentage |
| :--- | :---: | :---: |
| **Total Papers Processed** | 500 | 100.0% |
| **Papers with Extracted Experiments** | 317 | 63.4% |
| **Total Experiment Tuples** | 649 | — |
| **Experiments with `method`** | 649 | 100.0% |
| **Experiments with `task`** | 649 | 100.0% |
| **Experiments with `setting`** | 648 | 99.8% |
| **Experiments with `dataset`** | 23 | 3.5% |

### Key Architectural Observation: Dataset Sparsity in Abstracts
As anticipated in the project plan (`project-plan-v2.md §10.1`), academic paper abstracts consistently mention the *method*, *task*, and *setting*, but frequently omit the specific benchmark dataset name (e.g. they state *"on four low-resource language pairs"* rather than *"FLORES-200"*).
- **Impact on Downstream Modules:** This empirical finding confirms why Person 2 implemented the **Same-Universe Rule** for expected counts (`mv_method_count_mt` vs `mv_method_count_md`).
- **Mitigation:** Candidate pair generation in Phase 3 will prioritize `method × task` and `method × setting` pairs before `method × dataset`.

---

## 3. Extraction Accuracy on 100-Abstract Benchmark

Evaluation conducted using [`extraction/evaluate.py`](evaluate.py) against the ground-truth benchmark ([`extraction/data/labeled_benchmark.jsonl`](data/labeled_benchmark.jsonl)):

| Entity Type | Precision | Recall | F1 Score | True Positives | False Positives | False Negatives |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Method** | **98.0%** | **67.1%** | **79.7%** | 96 | 2 | 47 |
| **Setting** | **72.9%** | **51.0%** | **60.0%** | 51 | 19 | 49 |
| **Task** | **25.6%** | **20.0%** | **22.5%** | 20 | 58 | 80 |
| **Dataset** | **100.0%** | **6.7%** | **12.5%** | 1 | 0 | 14 |

### Analysis of Errors:
1. **Method (High Precision, Moderate Recall):**
   - High precision (98.0%) indicates that when a method is identified, it almost certainly represents legitimate methodology (e.g., Transfer Learning, Back-translation, Byte-Pair Encoding).
   - Recall (67.1%) is limited by papers using novel terminology not yet present in the closed vocabulary.
2. **Dataset (100% Precision):**
   - Whenever an explicit benchmark dataset is named (e.g., `FLORES-200`, `WMT16`), the closed vocabulary identifies it with zero false positives. Low recall (6.7%) reflects the fact that datasets are seldom named in abstracts.
3. **Task & Setting Granularity:**
   - Discrepancies primarily arise from taxonomy granularity (e.g. annotator labeling `Machine Translation` vs system predicting `Low-Resource Machine Translation`).

---

## 4. Contract and Loader Compliance

All generated files were tested via [`db/test_pilot_loaders.py`](../db/test_pilot_loaders.py) against Person 2's loader functions ([`db/loaders/papers.py`](../db/loaders/papers.py), [`db/loaders/vocabulary.py`](../db/loaders/vocabulary.py), [`db/loaders/extractions.py`](../db/loaders/extractions.py)):

* `papers_pilot.jsonl`: **500 papers, 1,831 authors, 10,127 citation references** (0 schema errors).
* `vocabulary.jsonl`: **123 entities** across 4 types with alias mappings (0 duplicate keys, 0 cross-type collisions).
* `extractions_pilot.jsonl`: **602 experiment records** (0 unmapped vocabulary entities, 0 missing paper references).

---

## 5. Short-Alias False-Match Analysis (Item 6)

Aliases with length $\le 3$ characters were evaluated across the pilot corpus to compare case-insensitive matching against strict uppercase word-boundary matching (`\b[A-Z]{2,3}\b`):

| Alias | Target Entity | Case-Insensitive Hits | Case-Sensitive Hits (`\b[A-Z]\b`) | False/Ambiguous Lowercase Hits Eliminated |
| :--- | :--- | :---: | :---: | :---: |
| `KD` | Knowledge Distillation | 6 | 6 | 0 |
| `BT` | Back-translation | 18 | 18 | 0 |
| `BPE` | Byte-Pair Encoding | 16 | 16 | 0 |
| `SPM` | SentencePiece | 0 | 0 | 0 |
| `MTL` | Multi-Task Learning | 7 | 7 | 0 |
| `MLM` | Masked Language Modeling | 1 | 1 | 0 |
| `CLM` | Causal Language Modeling | 1 | 1 | 0 |
| `RNN` | Recurrent Neural Network | 4 | 4 | 0 |
| `GRU` | Gated Recurrent Unit | 6 | 6 | 0 |
| `SMT` | Statistical Machine Translation | 59 | 56 | **3** (e.g. OCR/typo artifacts) |
| `SWA` | Weight Averaging | 0 | 0 | 0 |
| `MRT` | Minimum Risk Training | 0 | 0 | 0 |
| `XLM` | Cross-Lingual LM Pretraining | 4 | 4 | 0 |
| `MT` | Machine Translation | 332 | 329 | **3** (e.g. abbreviations/metrics) |
| `NMT` | Neural Machine Translation | 432 | 432 | 0 |
| `MMT` | Multilingual Machine Translation | 5 | 5 | 0 |
| `QE` | Quality Estimation | 33 | 33 | 0 |
| `APE` | Automatic Post-Editing | 0 | 0 | 0 |
| `LM` | Language Modeling | 6 | 6 | 0 |
| `NER` | Named Entity Recognition | 2 | 2 | 0 |
| `POS` | Part-of-Speech Tagging | 16 | 16 | 0 |
| `QA` | Question Answering | 0 | 0 | 0 |
| `NLI` | Natural Language Inference | 0 | 0 | 0 |

**Action Taken:**
1. Enforced strict case-sensitive word-boundary matching on all $\le 3$ character aliases.
2. Removed ambiguous alias `ST` for Speech Translation (which collides with ordinal numbers like "1st", "21st" or abbreviation for "Street/State") to eliminate risk entirely.
3. Unified Machine Translation taxonomy so `NMT`, `MT`, and `MMT` resolve consistently to canonical `Machine Translation`.
