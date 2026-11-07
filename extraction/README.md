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

## Commands

```powershell
# 1. Run extraction over pilot papers
python extraction/extract.py --papers ingest/data/papers_pilot.jsonl --vocab ingest/data/vocabulary.jsonl --out extraction/data/extractions_pilot.jsonl

# 2. Check coverage report
python extraction/evaluate.py --preds extraction/data/extractions_pilot.jsonl

# 3. Compare with the rule-generated reference set (preliminary; the file keeps its old name labeled_benchmark.jsonl)
python extraction/evaluate.py --preds extraction/data/extractions_pilot.jsonl --labels extraction/data/labeled_benchmark.jsonl
```

## Reproducibility

`extract.py` is deterministic: when two matches have the same length, the order is fixed (longest first, then
alphabetical), so the output does not depend on Python's randomized set ordering, and the file is always written
with LF line endings. `pytest extraction/tests` runs it in separate processes with different `PYTHONHASHSEED`
values on a small fixture and checks that the output files are byte-identical.

`extraction/data/extractions_pilot.jsonl` was produced by the earlier, non-deterministic version and has **not**
been regenerated: it is an old snapshot, and `accuracy_report.md` describes that snapshot. Running the command above
writes to that path and would replace it, so use a different `--out` unless you mean to regenerate it.
