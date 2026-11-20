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

# 3. Compare with the rule-generated reference set (preliminary; not human-labeled)
python extraction/evaluate.py --preds extraction/data/extractions_pilot.jsonl --labels extraction/data/labeled_benchmark.jsonl
```

## Rule-generated reference set (preliminary; not human-labeled)

`extraction/data/labeled_benchmark.jsonl` keeps its old file name, but it is **not** hand-labeled. It is made by
`python extraction/create_reference_set_v2.py` (earlier name `generate_real_benchmark.py`): 100 papers sampled with
seed 42 are labeled by a "conservative" and an "inclusive" rule set (regexes), and the result has 79 rows from 60
papers (40 sampled papers produced no row). `inter_annotator_disagreements.json` (old name) lists the 14 papers where
the two rule sets differed; 86 of 100 had identical labels, which is **not** an inter-annotator agreement. The method
labels use the same vocabulary and a similar regex style as `extract.py`, so the method precision and recall of 100%
from `evaluate.py` are circular and are not an accuracy measurement. The first version of this file (first 100
papers, `create_labeled_benchmark.py`) was replaced.

## Reproducibility

`extract.py` is deterministic: when two matches have the same length, the order is fixed (longest first, then
alphabetical), so the output does not depend on Python's randomized set ordering, and the file is always written
with LF line endings. `pytest extraction/tests` runs it in separate processes with different `PYTHONHASHSEED`
values on a small fixture and checks that the output files are byte-identical.

`extraction/data/extractions_pilot.jsonl` was produced by the earlier, non-deterministic version and has **not**
been regenerated: it is an old snapshot, and `accuracy_report.md` describes that snapshot. Running the command above
writes to that path and would replace it, so use a different `--out` unless you mean to regenerate it.
