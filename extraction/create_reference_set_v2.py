"""Generate the rule-generated reference set (preliminary; NOT human-labeled), version 2.

Despite the old file name `labeled_benchmark.jsonl`, nothing here is labeled by a person: every label comes
from the keyword and regex rules below. This script was called `generate_real_benchmark.py` before.

What it does:
- Samples 100 papers from ingest/data/papers_pilot.jsonl with a fixed seed (seed=42).
- Applies two rule sets to each sampled paper: "conservative rules" (a stricter condition on top of the
  same regexes) and "inclusive rules" (the regexes alone). The two rule sets use the same patterns, so
  they mostly agree by construction.
- Combines them into one set of rows (see "Combining the two rule sets" below) and writes
  extraction/data/labeled_benchmark.jsonl and extraction/data/inter_annotator_disagreements.json (the
  papers where the two rule sets gave different labels; the file keeps its old name).
- Uses only canonical names from ingest/data/vocabulary.jsonl.

Limits: the method labels use the same vocabulary and a similar regex style as extraction/extract.py, so
comparing the extractor with these labels is circular and is not an accuracy measurement. A sampled paper
with no task and no method under the combined rules gets no row at all (see the `continue` below).
"""

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

INPUT_PAPERS = Path("ingest/data/papers_pilot.jsonl")
VOCAB_PATH = Path("ingest/data/vocabulary.jsonl")
OUTPUT_BENCHMARK = Path("extraction/data/labeled_benchmark.jsonl")
DISAGREEMENT_LOG = Path("extraction/data/inter_annotator_disagreements.json")


def load_vocab():
    vocab = {"method": {}, "dataset": {}, "task": {}, "setting": {}}
    for line in open(VOCAB_PATH, encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        t = row["type"]
        canon = row["canonical_name"]
        vocab[t][canon.lower()] = canon
        for a in row.get("aliases", []):
            vocab[t][a.lower()] = canon
    return vocab


def build_reference_set():
    vocab = load_vocab()

    # Sample 100 papers with seed 42
    papers = [json.loads(line) for line in open(INPUT_PAPERS, encoding="utf-8") if line.strip()]
    random.seed(42)
    sample_papers = random.sample(papers, 100)

    # Rules for the tasks (canonical names only):
    task_patterns = [
        ("Machine Translation", [r"\bmachine translation\b", r"\btranslation\b", r"\bnmt\b", r"\bsmt\b", r"\bbitext\b"]),
        ("Language Modeling", [r"\blanguage model(?:ing|s)?\b", r"\bllm(?:s)?\b", r"\bmasked language model\b", r"\bcausal language model\b"]),
        ("Question Answering", [r"\bquestion answering\b", r"\bqa\b"]),
        ("Speech Translation", [r"\bspeech translation\b", r"\bend-to-end speech translation\b", r"\bast\b"]),
        ("Quality Estimation", [r"\bquality estimation\b"]),
        ("Text Summarization", [r"\bsummarization\b", r"\bsummarizing\b"]),
        ("Named Entity Recognition", [r"\bnamed entity recognition\b"]),
        ("Natural Language Inference", [r"\bnatural language inference\b"]),
        ("Sentiment Analysis", [r"\bsentiment analysis\b"]),
        ("Cross-Lingual Transfer", [r"\bcross-lingual transfer\b", r"\bcross-lingual representation\b"]),
        ("Text Classification", [r"\btext classification\b", r"\bdocument classification\b"]),
        ("Word Alignment", [r"\bword alignment\b"]),
        ("Automatic Post-Editing", [r"\bautomatic post-editing\b", r"\bape\b"]),
        ("Part-of-Speech Tagging", [r"\bpart-of-speech\b", r"\bpos tagging\b"]),
        ("Dependency Parsing", [r"\bdependency parsing\b"]),
    ]

    setting_patterns = [
        ("Low-resource", [r"\blow-resource\b", r"\blow resource\b", r"\bresource-constrained\b", r"\bscarce resource\b"]),
        ("Multilingual", [r"\bmultilingual\b", r"\bmany-to-many\b", r"\bone-to-many\b", r"\bmany-to-one\b"]),
        ("Zero-shot", [r"\bzero-shot\b", r"\bzero shot\b"]),
        ("Few-shot", [r"\bfew-shot\b", r"\bfew shot\b"]),
        ("Unsupervised", [r"\bunsupervised\b"]),
        ("Supervised", [r"\bsupervised\b"]),
        ("Cross-lingual", [r"\bcross-lingual\b", r"\bcross lingual\b"]),
        ("Semi-supervised", [r"\bsemi-supervised\b"]),
        ("High-resource", [r"\bhigh-resource\b", r"\bhigh resource\b"]),
        ("Bilingual", [r"\bbilingual\b"]),
        ("In-domain", [r"\bin-domain\b"]),
        ("Out-of-domain", [r"\bout-of-domain\b"]),
    ]

    # a1_* = conservative rules (the regex must match AND a stricter condition must hold)
    # a2_* = inclusive rules (the regex alone)
    disagreements = []
    gold_records = []


    for idx, p in enumerate(sample_papers):
        pid = p["paper_id"]
        title = p["title"] or ""
        abstract = p["abstract"] or ""
        text = f"{title}. {abstract}".lower()

        # Identify Tasks
        a1_tasks = []
        a2_tasks = []
        for canon, pats in task_patterns:
            for pat in pats:
                if re.search(pat, text):
                    a2_tasks.append(canon)
                    # conservative rules: the pattern is in the title, or the text contains one of these words
                    if re.search(pat, title.lower()) or "task" in text or "we propose" in text or "evaluate" in text:
                        a1_tasks.append(canon)
                    break
        a1_tasks = list(dict.fromkeys(a1_tasks))
        a2_tasks = list(dict.fromkeys(a2_tasks))

        # Identify Settings
        a1_settings = []
        a2_settings = []
        for canon, pats in setting_patterns:
            for pat in pats:
                if re.search(pat, text):
                    a2_settings.append(canon)
                    if re.search(pat, title.lower()) or "setting" in text or "scenario" in text or "data" in text:
                        a1_settings.append(canon)
                    break
        a1_settings = list(dict.fromkeys(a1_settings))
        a2_settings = list(dict.fromkeys(a2_settings))

        # Identify Datasets (exact matching against canonical dataset names or aliases > 3 chars)
        a1_datasets = []
        a2_datasets = []
        for d_key, canon_d in vocab["dataset"].items():
            if len(d_key) <= 3:
                continue
            if re.search(rf"\b{re.escape(d_key)}\b", text):
                a2_datasets.append(canon_d)
                if "dataset" in text or "corpus" in text or "benchmark" in text or "test on" in text or "evaluated on" in text:
                    a1_datasets.append(canon_d)
        a1_datasets = list(dict.fromkeys(a1_datasets))
        a2_datasets = list(dict.fromkeys(a2_datasets))

        # Identify Methods
        a1_methods = []
        a2_methods = []
        for m_key, canon_m in vocab["method"].items():
            if len(m_key) <= 3:
                # strict uppercase boundary
                if re.search(rf"\b{re.escape(m_key.upper())}\b", f"{title}. {abstract}"):
                    a2_methods.append(canon_m)
                    if "propose" in text or "use" in text or "model" in text or "approach" in text:
                        a1_methods.append(canon_m)
            else:
                if re.search(rf"\b{re.escape(m_key)}\b", text):
                    a2_methods.append(canon_m)
                    if "propose" in text or "method" in text or "model" in text or "baseline" in text or "architecture" in text or "via" in text or "using" in text:
                        a1_methods.append(canon_m)
        a1_methods = list(dict.fromkeys(a1_methods))
        a2_methods = list(dict.fromkeys(a2_methods))

        # Record the papers where the two rule sets differ
        diff_task = set(a1_tasks) ^ set(a2_tasks)
        diff_setting = set(a1_settings) ^ set(a2_settings)
        diff_method = set(a1_methods) ^ set(a2_methods)
        diff_dataset = set(a1_datasets) ^ set(a2_datasets)

        if diff_task or diff_setting or diff_method or diff_dataset:
            disagreements.append({
                "paper_id": pid,
                "title": title,
                "diff_task": list(diff_task),
                "diff_setting": list(diff_setting),
                "diff_method": list(diff_method),
                "diff_dataset": list(diff_dataset)
            })

        # Combining the two rule sets: the conservative result if it is not empty, else the first inclusive one.
        # Methods are the union of both.
        consensus_tasks = a1_tasks if a1_tasks else a2_tasks[:1]
        consensus_settings = a1_settings if a1_settings else a2_settings[:1]
        consensus_datasets = a1_datasets if a1_datasets else a2_datasets[:1]
        consensus_methods = list(set(a1_methods) | set(a2_methods))

        # A paper with no task and no method under the combined rules gets no row (it is dropped)
        if not consensus_tasks and not consensus_methods:
            continue

        primary_task = consensus_tasks[0] if consensus_tasks else None
        primary_setting = consensus_settings[0] if consensus_settings else None
        primary_dataset = consensus_datasets[0] if consensus_datasets else None

        if consensus_methods:
            for m in consensus_methods:
                gold_records.append({
                    "paper_id": pid,
                    "method": m,
                    "dataset": primary_dataset,
                    "task": primary_task,
                    "setting": primary_setting
                })
        else:
            # Paper has task/setting but no vocabulary method
            gold_records.append({
                "paper_id": pid,
                "method": None,
                "dataset": primary_dataset,
                "task": primary_task,
                "setting": primary_setting
            })

    # Save benchmark
    with open(OUTPUT_BENCHMARK, "w", encoding="utf-8", newline="\n") as f:
        for r in gold_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(DISAGREEMENT_LOG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(disagreements, f, indent=2, ensure_ascii=False)

    papers_with_rows = len({r["paper_id"] for r in gold_records})
    print(f"Generated rule-generated reference set with {len(gold_records)} rows from {papers_with_rows} of {len(sample_papers)} sampled papers.")
    print(f"Sampled papers where the conservative and inclusive rules gave different labels: {len(disagreements)} / {len(sample_papers)}")
    print(f"{len(sample_papers) - len(disagreements)} of {len(sample_papers)} sampled papers had identical labels under both rule sets (not an inter-annotator agreement).")
    print(f"Benchmark saved to {OUTPUT_BENCHMARK}")
    print(f"Rule differences saved to {DISAGREEMENT_LOG}")


if __name__ == "__main__":
    build_reference_set()
