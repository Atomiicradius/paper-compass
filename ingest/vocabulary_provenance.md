# Vocabulary Provenance & Taxonomy Specification

**Owner:** Person 1 (Data & Ingestion)  
**Corpus Domain:** Natural Language Processing (Machine Translation, Representation Learning, Speech, QA)  
**Standard Adherence:** Conforms to `db/proposals/vocabulary-format.md` and `context/data-and-contracts.md`  

---

## 1. Overview & Provenance Sources

The controlled vocabulary in [`ingest/data/vocabulary.jsonl`](data/vocabulary.jsonl) defines the closed entity universe for entity extraction and database loading. Every entity has been sourced and verified against established scientific taxonomy databases and NLP benchmark registries:

1. **Papers with Code (PwC) Taxonomy:**
   - Methods, evaluation benchmarks, and task hierarchies curated from PwC NLP / Machine Translation tasks.
2. **ACL Anthology & SREC Guidelines:**
   - Standard NLP task definitions from the Association for Computational Linguistics (ACL), EMNLP, NAACL, and EACL workshop proceedings.
3. **OpenAlex Concept Hierarchy:**
   - Root concept IDs:
     - `C204321447` (Machine translation)
     - `C41008148` (Computer science / NLP representations)
     - `C28490314` (Speech recognition & translation)
     - `C199360897` (Question answering)
4. **WMT (Conference on Machine Translation) & IWSLT Shared Tasks:**
   - Official dataset, test suite, and evaluation campaign designations (WMT14–WMT23, IWSLT, FLORES-101/200).

---

## 2. Orthogonal Taxonomy Scheme (Item 3 & 7 Resolution)

To avoid semantic overlap and label noise (e.g., distinguishing between "Neural Machine Translation", "Machine Translation", and "Low-Resource Machine Translation"), the vocabulary strictly separates orthogonal dimensions:

- **`TASK`**: *What problem is being solved?* (e.g. `Machine Translation`, `Speech Translation`, `Question Answering`).
- **`SETTING`**: *Under what data or resource constraint?* (e.g. `Low-resource`, `Multilingual`, `Zero-shot`, `Supervised`).
- **`METHOD`**: *What algorithm or architecture is evaluated?* (e.g. `Transformer`, `Back-translation`, `Adapter Tuning`).
- **`DATASET`**: *On what benchmark corpus?* (e.g. `WMT14`, `FLORES-200`, `SQuAD`).

### Disambiguation & Cross-Type Deduplication:
- **Bitext Mining:** Formerly duplicated as both a method and a task. Resolved strictly as a **Task** (the objective of identifying parallel sentences from comparable corpora).
- **Word Alignment:** Formerly duplicated. Resolved strictly as a **Task**; algorithms performing alignment are mapped to the method **`Statistical Alignment Model`** (e.g. GIZA++, fast_align).
- **Unsupervised / Low-Resource Machine Translation:** Removed as compound task names. All translation tasks map to canonical **`Machine Translation`**, with `Unsupervised` and `Low-resource` captured exclusively in **`setting`**.

---

## 3. Entity Provenance Catalog

### 3.1 Tasks (18 Canonical Entities)
| Canonical Name | Sourced From | Key Aliases / Acronyms | Description / Role |
| :--- | :--- | :--- | :--- |
| `Machine Translation` | ACL / OpenAlex `C204321447` | MT, NMT, Neural Machine Translation, SMT, MMT | Cross-lingual text translation |
| `Speech Translation` | OpenAlex `C28490314` | spoken language translation, speech-to-text translation | Audio to foreign text translation |
| `Quality Estimation` | WMT Shared Tasks | QE, translation quality estimation | Predicting translation quality without reference |
| `Automatic Post-Editing` | WMT Shared Tasks | APE, post-editing | Automated correction of machine-generated text |
| `Bitext Mining` | ACL / BUCC Workshops | parallel sentence extraction, bitext filtering | Extracting parallel sentence pairs |
| `Cross-Lingual Transfer` | EMNLP / XTREME | cross-lingual generalization, cross-lingual transfer | Zero-shot or few-shot transfer across languages |
| `Language Modeling` | PwC / OpenAlex | LM, autoregressive generation | Generative token probability modeling |
| `Word Alignment` | ACL Anthology | bilingual word alignment, word-level alignment | Token-level mapping between source and target |
| `Named Entity Recognition` | CoNLL / PwC | NER, entity extraction | Token classification into semantic categories |
| `Part-of-Speech Tagging` | Penn Treebank / PwC | POS tagging, POS | Grammatical category tagging |
| `Dependency Parsing` | Universal Dependencies | syntactic parsing | Structural grammatical relation prediction |
| `Text Summarization` | PwC / DUC / TAC | abstractive summarization, extractive summarization | Condensing documents into concise summaries |
| `Question Answering` | PwC / SQuAD | QA, reading comprehension | Extractive or generative QA |
| `Sentiment Analysis` | SemEval / PwC | sentiment classification | Polarity identification in text |
| `Natural Language Inference` | SNLI / MultiNLI / XNLI | NLI, textual entailment | Premise-hypothesis relationship classification |
| `Paraphrase Generation` | ACL Anthology | paraphrasing | Rewriting text preserving semantics |
| `Text Classification` | PwC | document classification | Categorizing whole documents into topics |
| `Morphological Analysis` | SIGMORPHON | morphology tagging | Subword/affix linguistic decomposition |

### 3.2 Methods (54 Canonical Entities)
- **Architectures:** `Transformer`, `Recurrent Neural Network`, `Long Short-Term Memory`, `Gated Recurrent Unit`, `Convolutional Sequence to Sequence`.
- **Pre-training Objectives:** `Masked Language Modeling`, `Causal Language Modeling`, `Cross-Lingual Language Model Pretraining`, `Denoising Sequence-to-Sequence`, `Multilingual Pre-training`.
- **Parameter-Efficient Tuning (PEFT):** `Low-Rank Adaptation`, `Adapter Tuning`, `Prompt Tuning`, `Prefix Tuning`, `Fine-tuning`, `Transfer Learning`.
- **Data & Semi-Supervised Methods:** `Back-translation`, `Dual Learning`, `Data Augmentation`, `Knowledge Distillation`, `Contrastive Learning`, `Curriculum Learning`, `Multi-Task Learning`.
- **Tokenization:** `Byte-Pair Encoding`, `SentencePiece`, `WordPiece`, `Subword Regularization`.
- **Decoding & Optimization:** `Beam Search`, `Reranking`, `Lexical Constrained Decoding`, `Minimum Risk Training`, `Label Smoothing`, `Weight Averaging`, `Ensembling`, `Model Pruning`, `Quantization`.
- **Attention & Positional Encodings:** `Self-Attention`, `Cross-Attention`, `FlashAttention`, `Rotary Position Embedding`, `Relative Position Encoding`, `Layer Normalization`.
- **Legacy & Statistical baselines:** `Statistical Machine Translation`, `Phrase-Based Statistical Machine Translation`, `Syntax-Based Machine Translation`, `Rule-Based Machine Translation`, `Statistical Alignment Model`, `Pivot Translation`, `Word2Vec`, `FastText`, `GloVe`, `Sentence Embeddings`.

### 3.3 Datasets (41 Canonical Entities)
- **Standard Evaluation Suites:** `WMT` (WMT14–WMT23), `FLORES` (FLORES-101, FLORES-200), `IWSLT`, `Tatoeba`, `TED Talks`.
- **Web & Crawled Corpora:** `Common Crawl`, `CCNet`, `CCAligned`, `ParaCrawl`, `WikiMatrix`, `OpenSubtitles`, `OPUS`, `OPUS-100`.
- **Parliamentary & Multilingual Corpora:** `Europarl`, `UN Parallel Corpus`, `JW300`, `News Commentary`.
- **Indic & Low-Resource Benchmarks:** `Samanantar`, `Bharat Parallel Corpus`, `IndicCorp`, `IndicGLUE`, `IITB Hindi-English`, `PMIndia`.
- **NLU / Downstream Benchmarks:** `GLUE`, `SuperGLUE`, `SQuAD`, `XNLI`, `CoNLL-2003`, `Multi30k`, `MTNT`.

### 3.4 Settings (12 Canonical Entities)
- **Data Availability Regimes:** `Low-resource`, `High-resource`.
- **Supervision Types:** `Supervised`, `Unsupervised`, `Semi-supervised`, `Zero-shot`, `Few-shot`.
- **Linguistic Scopes:** `Multilingual`, `Bilingual`, `Cross-lingual`.
- **Domain Scopes:** `In-domain`, `Out-of-domain`.
