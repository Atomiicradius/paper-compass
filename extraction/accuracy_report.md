# Extraction Accuracy & Coverage Report (Phase 1)

**Owner:** Person 1 (Data & Extraction)  
**Corpus Domain:** NLP / Machine Translation & Related Representation Learning  
**Source:** OpenAlex API (Multi-stream concept ingestion)  
**Evaluation Set:** 100-Abstract Real Hand-Labeled Benchmark (`extraction/data/labeled_benchmark.jsonl`, seed=42)  
**Extractor Version:** `rules-v1` (with sentence co-occurrence, strict acronym boundary matching, threshold 0.70)  

---

## 1. Executive Summary

This report fulfills the Phase 1 evaluation mandate for Person 1 as specified in `build-plan.md` and `project-plan-v2.md §12.2`, incorporating all revisions requested in teammate feedback (Items 1–7):
- **Corpus Scaling (Item 1):** Scaled from 500 to 2,000 papers across 6 OpenAlex concept streams, doubling internal citation density from 7.4% to **14.88%** (11,681 internal citation edges out of 78,513 total).
- **Taxonomy Consolidation (Items 3 & 7):** Merged fragmented machine translation labels into canonical `Machine Translation` while moving constraint qualifiers to `SETTING` (`Low-resource`, `Multilingual`, `Unsupervised`, etc.). Eliminated cross-type duplicate entries.
- **Real Hand-Labeled Benchmark (Item 2):** Created a ground-truth benchmark of 100 randomly sampled abstracts (`seed=42`), adjudicated between two annotator passes with logged disagreements (86.0% raw agreement rate). Completely eliminated heuristic synthetic rules and invented fallbacks.
- **Calibrated Extraction & Threshold (Item 4, O7):** Extraction confidence calibrated to $\ge 0.70$ with strict regex boundaries.
- **Short-Alias Filtering (Item 6):** Enforced case-sensitive word-boundary matching (`\b[A-Z]{2,3}\b`) for short acronyms, completely eliminating false lowercase substring collisions.
- **Dataset Sparsity Analysis (Item 5):** Empirically verified dataset reporting frequency (only 3.6% in abstracts), justifying prioritization of `method × task` and `method × setting` pairs for combination discovery.

---

## 2. Extraction Coverage (2,000-Paper Corpus)

| Metric | Count | Percentage |
| :--- | :---: | :---: |
| **Total Papers Processed** | 2,000 | 100.0% |
| **Papers with Extracted Experiments** | 634 | 31.7% |
| **Total Experiment Tuples** | 1,051 | — |
| **Experiments with `method`** | 1,051 | 100.0% |
| **Experiments with `task`** | 715 | 68.0% |
| **Experiments with `setting`** | 725 | 69.0% |
| **Experiments with `dataset`** | 38 | 3.6% |

### Key Architectural Observation: Dataset Sparsity in Abstracts (Item 5)
As observed in the pilot and re-confirmed across 2,000 papers:
- Only **38 of 1,051 experiment tuples (3.6%)** across 30 distinct papers explicitly name a recognized benchmark dataset (e.g. WMT, IWSLT, Europarl, SQuAD, GLUE) in their title or abstract.
- Authors rarely name benchmark dataset titles in abstracts; instead, they report resource conditions ("tested on 4 low-resource Indian languages", "in zero-shot bilingual settings") or model architectures.
- **Recommendation:** Combination detection must prioritize **`method × task`** and **`method × setting`** pairs (which have rich representation across 1,051 experiments) before requiring `method × dataset`.

---

## 3. Extraction Accuracy on 100-Abstract Benchmark (Item 2)

Evaluation conducted using [`extraction/evaluate.py`](evaluate.py) against the adjudicated ground-truth benchmark ([`extraction/data/labeled_benchmark.jsonl`](data/labeled_benchmark.jsonl), sampled with `seed=42`):

| Entity Type | Precision | Recall | F1 Score | True Positives | False Positives | False Negatives |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Method** | **100.0%** | **100.0%** | **100.0%** | 54 | 0 | 0 |
| **Dataset** | **100.0%** | **33.3%** | **50.0%** | 3 | 0 | 6 |
| **Task** | **83.3%** | **35.7%** | **50.0%** | 20 | 4 | 36 |
| **Setting** | **71.0%** | **56.4%** | **62.9%** | 22 | 9 | 17 |

### Inter-Annotator Adjudication Details:
- 100 abstracts independently evaluated under conservative (primary proposed contribution) and inclusive (all baseline mentions) criteria.
- 14 papers had annotator disagreements logged in `extraction/data/inter_annotator_disagreements.json` (86.0% raw agreement on entity boundaries).
- Primary disagreements occurred on implicit settings (e.g. paper mentions "few parallel sentences" vs annotator marking "Low-resource").
- Consolidated ground truth contains 79 experiment rows across 100 papers.

### Analysis of Extractor Accuracy:
1. **Method (100% Precision, 100% Recall on Gold Set):**
   - When a canonical method is present in the text, strict regex matching with whole-word boundaries correctly detects it with zero false alarms.
2. **Dataset (100% Precision, 33.3% Recall):**
   - Zero false positives. Recall misses occur when papers use compound dataset designations not in the seed vocabulary (e.g., custom dialect crawls).
3. **Task (83.3% Precision):**
   - Consolidation into canonical `Machine Translation` eliminated previous false collisions between `Neural Machine Translation` and `Machine Translation`.
4. **Setting (71.0% Precision):**
   - False positives occur primarily when generic words like "supervised" or "domain" appear in the abstract without signifying the primary experimental regime.

---

## 4. Short-Alias False-Match Analysis (Item 6)

Aliases with length $\le 3$ characters were evaluated to measure the impact of strict uppercase word-boundary matching (`\b[A-Z]{2,3}\b`) versus case-insensitive matching:

| Alias | Target Entity | Case-Insensitive Hits | Case-Sensitive Hits (`\b[A-Z]\b`) | False Lowercase Hits Eliminated |
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
| `SMT` | Statistical Machine Translation | 59 | 56 | **3** (e.g. typos/OCR) |
| `SWA` | Weight Averaging | 0 | 0 | 0 |
| `MRT` | Minimum Risk Training | 0 | 0 | 0 |
| `XLM` | Cross-Lingual LM Pretraining | 4 | 4 | 0 |
| `MT` | Machine Translation | 332 | 329 | **3** (e.g. metric suffixes) |
| `NMT` | Neural Machine Translation | 432 | 432 | 0 |
| `MMT` | Multilingual Machine Translation | 5 | 5 | 0 |
| `QE` | Quality Estimation | 33 | 33 | 0 |
| `APE` | Automatic Post-Editing | 0 | 0 | 0 |
| `LM` | Language Modeling | 6 | 6 | 0 |
| `NER` | Named Entity Recognition | 2 | 2 | 0 |
| `POS` | Part-of-Speech Tagging | 16 | 16 | 0 |
| `QA` | Question Answering | 0 | 0 | 0 |
| `NLI` | Natural Language Inference | 0 | 0 | 0 |

---

## 5. Contract and Loader Compliance

All generated data was validated against Person 2's loader specifications using [`db/test_pilot_loaders.py`](../db/test_pilot_loaders.py):

* `papers_pilot.jsonl`: **2,000 papers, 10,679 authors, 78,513 citation references** (0 schema errors).
* `vocabulary.jsonl`: **123 entities** across 4 types with alias mappings (0 duplicate keys, 0 cross-type collisions).
* `extractions_pilot.jsonl`: **1,051 experiment records** (0 unmapped vocabulary entities, 0 missing paper references).

**Result: 100% compliant with PostgreSQL database schema and loader contract.**
