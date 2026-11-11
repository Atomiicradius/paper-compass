# extraction/

Information extraction pipeline for Paper Compass (Person 1).

Extracts experiment rows `(paper_id, method, dataset, task, setting, confidence, source_sentence, extractor)` from paper abstracts and titles, linking them directly to the controlled vocabulary and aliases.

## Output Schema

Conforms to `context/data-and-contracts.md §3`:
```json
{
  "paper_id": "W2337363174",
  "method": "Transfer Learning",
  "dataset": null,
  "task": "Neural Machine Translation",
  "setting": "Low-resource",
  "confidence": 0.8,
  "source_sentence": "We present a transfer learning method that significantly improves BLEU scores across a range of low-resource languages.",
  "extractor": "rules-v1"
}
```

## Task Taxonomy & Assignment Rules

To eliminate label overlap and false sparsity artifacts (e.g., distinguishing "Neural Machine Translation" vs "Machine Translation"), tasks, settings, and methods follow a strictly orthogonal taxonomy:

1. **Task is the Objective:**
   - Canonical task `Machine Translation` encompasses all translation variants (NMT, SMT, multilingual MT, rule-based MT).
   - Other canonical tasks include `Speech Translation`, `Quality Estimation`, `Automatic Post-Editing`, `Bitext Mining`, `Word Alignment`, `Cross-Lingual Transfer`, `Language Modeling`, `Named Entity Recognition`, `Text Summarization`, `Question Answering`, `Part-of-Speech Tagging`, etc.
2. **Setting is the Constraint/Data Condition:**
   - `Low-resource`, `High-resource`, `Multilingual`, `Zero-shot`, `Few-shot`, `Unsupervised`, `Cross-lingual`, `In-domain`, `Out-of-domain`.
   - A paper addressing low-resource neural translation is labeled `Task: Machine Translation` and `Setting: Low-resource`.
3. **Method is the Technical Mechanism:**
   - Architecture or algorithmic approach (`Transformer`, `Knowledge Distillation`, `Back-translation`, `LoRA`, `Adapter Tuning`, `Byte-Pair Encoding`, `Transfer Learning`).

## Short-Alias Matching Rules (Case-Sensitivity)

To avoid false matches on common English words (such as `"pos"`, `"lm"`, or `"st"`):
- All aliases with length $\le 3$ characters (`KD`, `BT`, `BPE`, `SPM`, `MTL`, `MLM`, `CLM`, `RNN`, `GRU`, `SMT`, `SWA`, `MRT`, `XLM`, `MT`, `NMT`, `MMT`, `QE`, `APE`, `LM`, `NER`, `POS`, `QA`, `NLI`) are matched **case-sensitively** with whole-word boundaries: `\b[A-Z]{2,3}\b`.
- Ambiguous two-letter acronyms (such as `ST` for Speech Translation) have been removed from the vocabulary to guarantee 0 false positives.

## Commands

```powershell
# 1. Run extraction over pilot papers
python extraction/extract.py --papers ingest/data/papers_pilot.jsonl --vocab ingest/data/vocabulary.jsonl --out extraction/data/extractions_pilot.jsonl

# 2. Check coverage report
python extraction/evaluate.py --preds extraction/data/extractions_pilot.jsonl

# 3. Evaluate precision and recall against labeled benchmarks
python extraction/evaluate.py --preds extraction/data/extractions_pilot.jsonl --labels extraction/data/labeled_benchmark.jsonl
```
