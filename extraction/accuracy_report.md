# Extraction Coverage and Accuracy Report (Phase 1)

**Owner:** Person 1 (Samarth Kulkarni — Data & Extraction)  
**Corpus Domain:** Natural Language Processing (Machine Translation, Representation Learning, Speech, QA)  
**Source:** OpenAlex API (Multi-stream concept ingestion, de-duplicated)  
**Corpus Size:** 1,975 unique papers (after de-duplication of 25 shared DOI and preprint duplicates)  
**Extractor Version:** `rules-v1` (with sentence co-occurrence, abstract-level dataset inheritance, threshold 0.70)  

---

## 1. Executive Summary & Review Feedback Resolution

This report documents the resolution of all feedback items from the Person 1 review:

1. **De-duplication at Ingest (Items 1 & 2):**
   - Merged records sharing a DOI (e.g. Adam `W1522301498` into `W2964121744`, retaining 22 references and full authorships).
   - Merged repeated titles across preprint and peer-reviewed conference versions (e.g. 3 copies of "Survey of Low-Resource Machine Translation" into Computational Linguistics journal record `W3198189804`; FLORES-101 preprint merged into TACL record `W3169369929`).
   - Merged **25 duplicate records** total (corpus adjusted from 2,000 to **1,975 unique papers**).
   - Remapped **179 citation references** across the corpus pointing from dropped IDs to kept IDs.
   - Audit trail saved to [`ingest/data/deduplication_log.json`](../ingest/data/deduplication_log.json).

2. **Rule-based check set (Item 4). No person labeled these abstracts:**
   - Sampled 50 abstracts from the deduplicated corpus (`seed=2026`).
   - Labeled them with two rule passes, both regular expressions in [`extraction/sample_and_label_50.py`](sample_and_label_50.py) that use only canonical names from `vocabulary.jsonl` (pass A "conservative": needs a cue in the title or nearby; pass B "inclusive": keeps every match).
   - The two passes gave the same labels for 44 of 50 papers (**88.0%**; the 6 papers that differ are in `extraction/data/rule_pass_differences.json`). This is the overlap of two rule sets, **not an inter-annotator agreement**.
   - The combined labels are in [`extraction/data/rule_based_check_set_50.jsonl`](data/rule_based_check_set_50.jsonl). **This is not independent ground truth**: the rules are written in the same style, from the same vocabulary, as the extractor, so the figures in section 3 compare two rule-based systems and are not accuracy measurements.
   - Still to do: a check set whose labels are written by people (for example 50 to 100 abstracts, two people, disagreements settled by discussion). Until then the report has **no measured extraction accuracy**; the coverage figures in section 2 remain valid.

3. **Dataset Coverage Improvement (Item 5):**
   - Identified that previous sentence-only extraction missed 70%+ of dataset mentions because authors state methods in early sentences and evaluate on datasets in later sentences.
   - Implemented abstract-level dataset inheritance for unambiguous datasets, increasing dataset extractions from **39 (3.8%) to 104 (10.1%)** across 623 papers.
   - Formally documented structural dataset sparsity in academic abstracts.

4. **Short-Alias Review & False-Match Audit (Item 6):**
   - Audited all 24 short aliases ($\le 3$ characters).
   - Discovered that standalone alias `APE` matched "Automatic Prompt Engineer (APE)" in prompt engineering papers (e.g. `W4308244910`). Replaced bare `APE` with `["automatic post-editing", "post-editing", "neural APE"]`.
   - Verified that all remaining 23 acronyms use case-sensitive uppercase word boundaries (`\b[A-Z]{2,3}\b`), preventing lowercase dictionary word collisions.
   - Confirmed `SMT` is strictly classified as a Method.

---

## 2. Extraction Coverage (Deduplicated 1,975-Paper Corpus)

| Metric | Count | Percentage |
| :--- | :---: | :---: |
| **Total Papers Processed** | 1,975 | 100.0% |
| **Papers with Extracted Experiments** | 623 | 31.5% |
| **Total Experiment Tuples** | 1,033 | — |
| **Experiments with `method`** | 1,033 | 100.0% |
| **Experiments with `task`** | 700 | 67.8% |
| **Experiments with `setting`** | 710 | 68.7% |
| **Experiments with `dataset`** | **104** | **10.1%** |

### Structural Dataset Sparsity in Academic Abstracts (Item 5)
Even with improved abstract-level inheritance:
- **104 of 1,033 experiment tuples (10.1%)** name an explicit benchmark dataset.
- In academic NLP literature, abstracts predominantly describe language pairs, resource constraints, or experimental regimes (e.g. *"evaluated on 4 low-resource Indian languages in zero-shot transfer"*) rather than formal dataset names (e.g. *Samanantar* or *FLORES-200*).
- **Contract Impact:** Confirms the proposal in [`db/proposals/method-setting-views.md`](../db/proposals/method-setting-views.md) to prioritize `method × task` and `method × setting` pairs for opportunity discovery while keeping `method × dataset` available where explicitly reported.

---

## 3. Comparison with the Rule-Based Check Set (50 Abstracts, Item 4)

**Read this first:** the check set was made by regular expressions, not by people, and it is not independent ground truth (see below). These figures show how closely the extractor and a second set of rules agree. They do not say how often the extractor is right on real abstracts.

Compared against [`extraction/data/rule_based_check_set_50.jsonl`](data/rule_based_check_set_50.jsonl) (53 rows from 50 papers) with `python extraction/evaluate.py --labels extraction/data/rule_based_check_set_50.jsonl`:

| Entity Type | Precision | Recall | F1 Score | True Positives (TP) | False Positives (FP) | False Negatives (FN) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Method** | 63.6% | 100.0% | 77.8% | 14 | 8 | 0 |
| **Task** | 90.9% | 43.5% | 58.8% | 10 | 1 | 13 |
| **Setting** | 75.0% | 47.4% | 58.1% | 9 | 3 | 10 |
| **Dataset** | 50.0% | 100.0% | 66.7% | 1 | 1 | 0 |

The dataset row rests on a single true positive and a single false positive; it says nothing.

### How the check set was made
- 50 abstracts sampled with a fixed seed (`seed=2026`).
- **Rule pass A ("conservative"):** keeps a match only when the title or a nearby cue word supports it.
- **Rule pass B ("inclusive"):** keeps every match in the title or abstract.
- The combined file takes pass A's first task, setting and dataset (pass B's when A has none) and the union of the methods of both passes. This is a rule, not a person's decision.
- **Overlap of the two passes (not an agreement between people):**
  - Method: 100.0% (14/14)
  - Setting: 94.3% (33/35)
  - Task: 84.4% (27/32)
  - Papers with identical labels from both passes: **88.0%** (44/50).
- The 6 papers where the passes differ are listed in [`extraction/data/rule_pass_differences.json`](data/rule_pass_differences.json).

### Why this is not independent ground truth
1. The patterns in `sample_and_label_50.py` and in `extract.py` come from the same vocabulary and have the same style, so they tend to make the same mistakes. The method recall of 100% is therefore expected and is not a result.
2. The check set can only contain labels that a regular expression can find. It cannot show what the extractor misses or gets wrong in a way a regex also would.
3. No kappa or other chance-corrected agreement is computed, because there are no two human labelers.

### Reading the differences (not verified against human labels)
1. **Method (precision 63.6%):** the 8 extra methods are probably methods that an abstract mentions as background or as a baseline, which pass A drops. This has not been checked by reading the abstracts.
2. **Task (recall 43.5%):** probably because some abstracts describe a task without repeating the exact keyword in the same sentence. Not checked.
3. **Setting (recall 47.4%):** probably because settings are described in words that are not canonical vocabulary terms (for example "scarce parallel pairs"). Not checked.

---

## 4. Short-Alias False-Match Analysis & Review (Item 6)

All 24 short aliases ($\le 3$ characters) were audited across the 1,975-paper corpus. Standalone alias `APE` was removed from the vocabulary to eliminate false prompt engineering collisions.

| Alias | Target Entity | Case-Sensitive Hits (`\b[A-Z]\b`) | Case-Insensitive Hits | Non-Uppercase Hits Eliminated | Status & Action |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `KD` | Knowledge Distillation (method) | 10 | 10 | 0 | Retained (clean) |
| `BT` | Back-translation (method) | 18 | 18 | 0 | Retained (clean) |
| `BPE` | Byte-Pair Encoding (method) | 16 | 16 | 0 | Retained (clean) |
| `SPM` | SentencePiece (method) | 0 | 0 | 0 | Retained |
| `MTL` | Multi-Task Learning (method) | 7 | 7 | 0 | Retained (clean) |
| `MLM` | Masked Language Modeling (method) | 13 | 14 | 1 | Retained (clean) |
| `CLM` | Causal Language Modeling (method) | 1 | 1 | 0 | Retained (clean) |
| `RNN` | Recurrent Neural Network (method) | 24 | 25 | 1 | Retained (clean) |
| `GRU` | Gated Recurrent Unit (method) | 9 | 9 | 0 | Retained (clean) |
| `SMT` | Statistical Machine Translation (method) | 61 | 64 | 3 | Retained (method only) |
| `SWA` | Weight Averaging (method) | 0 | 0 | 0 | Retained |
| `MRT` | Minimum Risk Training (method) | 0 | 0 | 0 | Retained |
| `XLM` | Cross-Lingual LM Pretraining (method) | 9 | 9 | 0 | Retained (clean) |
| `MT` | Machine Translation (task) | 330 | 336 | 6 | Retained (clean) |
| `NMT` | Machine Translation (task) | 449 | 449 | 0 | Retained (clean) |
| `MMT` | Machine Translation (task) | 5 | 5 | 0 | Retained (clean) |
| `QE` | Quality Estimation (task) | 27 | 27 | 0 | Retained (clean) |
| `APE` | Automatic Post-Editing (task) | 0 | 3 | **3** | **Removed bare alias** (collided with Automatic Prompt Engineer) |
| `LM` | Language Modeling (task) | 37 | 38 | 1 | Retained (clean) |
| `NER` | Named Entity Recognition (task) | 36 | 36 | 0 | Retained (clean) |
| `POS` | Part-of-Speech Tagging (task) | 21 | 21 | 0 | Retained (clean) |
| `QA` | Question Answering (task) | 39 | 40 | 1 | Retained (clean) |
| `NLI` | Natural Language Inference (task) | 5 | 5 | 0 | Retained (clean) |
| `WMT` | WMT (dataset) | 27 | 27 | 0 | Retained (clean) |

---

## 5. Verification & Loader Integrity

Tested with [`ingest/test_pilot_integrity.py`](../ingest/test_pilot_integrity.py):
- **Vocabulary:** 125 entries (0 errors).
- **Papers:** 1,975 de-duplicated papers (10,566 authors, 78,188 citation references, 0 errors).
- **Extractions:** 1,033 experiment tuples (0 unmapped entities, 0 missing paper references).
- **Result:** **100% PASS on all format and integrity checks.**
