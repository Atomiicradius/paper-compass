"""Evaluation script for extraction precision, recall, F1, and entity coverage.

Generates evaluation metrics per entity type (method, dataset, task, setting)
and overall paper coverage as specified in build-plan.md and project-plan-v2.md §12.2.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def evaluate(predictions_file, labels_file=None):
    preds_by_paper = defaultdict(list)
    total_papers_with_preds = set()
    entity_counts = defaultdict(int)

    with open(predictions_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            pid = r["paper_id"]
            preds_by_paper[pid].append(r)
            total_papers_with_preds.add(pid)
            for k in ("method", "dataset", "task", "setting"):
                if r.get(k):
                    entity_counts[k] += 1

    print("=" * 60)
    print("EXTRACTION COVERAGE REPORT")
    print("=" * 60)
    print(f"Total experiment predictions: {sum(len(v) for v in preds_by_paper.values())}")
    print(f"Distinct papers with extractions: {len(total_papers_with_preds)}")
    print("\nEntity extraction frequency:")
    for k in ("method", "dataset", "task", "setting"):
        print(f"  - {k:<10}: {entity_counts[k]} extractions")

    if not labels_file or not Path(labels_file).exists():
        print("\nNote: Ground-truth labeled benchmark file not provided.")
        print("To compute precision/recall/F1, supply --labels with labeled JSONL benchmark.")
        return

    # If ground-truth labels provided
    gold_by_paper = defaultdict(list)
    with open(labels_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                gold_by_paper[r["paper_id"]].append(r)

    print("\n" + "=" * 60)
    print("EXTRACTION ACCURACY REPORT (Precision / Recall / F1)")
    print("=" * 60)

    for kind in ("method", "dataset", "task", "setting"):
        tp, fp, fn = 0, 0, 0
        for pid, golds in gold_by_paper.items():
            gold_vals = {g[kind].lower().strip() for g in golds if g.get(kind)}
            pred_vals = {p[kind].lower().strip() for p in preds_by_paper.get(pid, []) if p.get(kind)}

            tp += len(gold_vals & pred_vals)
            fp += len(pred_vals - gold_vals)
            fn += len(gold_vals - pred_vals)

        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) else 0.0

        print(f"{kind.capitalize():<10} -> Precision: {prec*100:5.1f}% | Recall: {rec*100:5.1f}% | F1: {f1*100:5.1f}% (TP={tp}, FP={fp}, FN={fn})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preds", default="extraction/data/extractions_pilot.jsonl")
    parser.add_argument("--labels", default=None, help="Path to hand-labeled abstracts JSONL")
    args = parser.parse_args()
    evaluate(args.preds, args.labels)
