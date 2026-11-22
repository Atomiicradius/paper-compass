"""Build a RULE-BASED check set for 50 abstracts (Item 4).

No person labeled anything here. Every label comes from regular expressions in this file.

Samples 50 abstracts from the deduplicated corpus (seed=2026) and labels them with two rule passes that use only
canonical names from vocabulary.jsonl:
- Rule pass A ("conservative"): keeps a match only when the title or a nearby cue word supports it.
- Rule pass B ("inclusive"): keeps every match anywhere in the title or abstract.
The two passes are then compared (how often they give the same labels) and combined into one file, the rule-based
check set. The combination takes pass A's first task, setting and dataset (pass B's if A has none) and the union of
the methods of both passes.

What this file is NOT: it is not independent ground truth and not a measure of extractor accuracy. The patterns are
written in the same style, from the same vocabulary, as extraction/extract.py, so agreement with the extractor says
little about how often the extractor is right on real abstracts. The overlap between pass A and pass B is not an
inter-annotator agreement, and no kappa is computed. A real accuracy check needs labels written by people.
"""

import json
import random
import re
from collections import defaultdict
from pathlib import Path

PAPERS_PATH = Path("ingest/data/papers_pilot.jsonl")
VOCAB_PATH = Path("ingest/data/vocabulary.jsonl")
OUT_SAMPLES = Path("extraction/data/sampled_abstracts_50.json")
OUT_PASS_A = Path("extraction/data/rule_pass_conservative.jsonl")
OUT_PASS_B = Path("extraction/data/rule_pass_inclusive.jsonl")
OUT_DIFFERENCES = Path("extraction/data/rule_pass_differences.json")
OUT_CHECK_SET = Path("extraction/data/rule_based_check_set_50.jsonl")


def load_vocab():
    vocab = {"method": set(), "dataset": set(), "task": set(), "setting": set()}
    for line in open(VOCAB_PATH, encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        vocab[row["type"]].add(row["canonical_name"])
    return vocab


def sample_papers(seed=2026, count=50):
    papers = [json.loads(line) for line in open(PAPERS_PATH, encoding="utf-8") if line.strip()]
    random.seed(seed)
    # Stratified: pick a balanced cross-section
    sampled = random.sample(papers, count)
    return sampled


def label_with_rules():
    vocab = load_vocab()
    papers = sample_papers()
    
    # Save the sampled abstracts so the rule-based labels can be read next to the text
    with open(OUT_SAMPLES, "w", encoding="utf-8", newline="\n") as f:
        json.dump([
            {"paper_id": p["paper_id"], "title": p["title"], "abstract": p.get("abstract")}
            for p in papers
        ], f, indent=2, ensure_ascii=False)
    print(f"Sampled {len(papers)} abstracts to {OUT_SAMPLES}")

    # Explicit rules mapping natural language cues to canonical vocabulary entities
    # Task mappings
    task_rules = [
        ("Machine Translation", [r"\bmachine translation\b", r"\btranslation\b", r"\bnmt\b", r"\bsmt\b", r"\bbitext\b"]),
        ("Language Modeling", [r"\blanguage model(?:ing|s)?\b", r"\bllm(?:s)?\b", r"\bautoregressive\b"]),
        ("Speech Translation", [r"\bspeech[- ]translation\b", r"\bspeech to text\b", r"\bspoken language translation\b"]),
        ("Quality Estimation", [r"\bquality estimation\b"]),
        ("Automatic Post-Editing", [r"\bautomatic post-editing\b", r"\bpost-editing\b"]),
        ("Question Answering", [r"\bquestion answering\b", r"\breading comprehension\b"]),
        ("Text Summarization", [r"\bsummarization\b", r"\bsummarizing\b"]),
        ("Named Entity Recognition", [r"\bnamed entity recognition\b"]),
        ("Natural Language Inference", [r"\bnatural language inference\b"]),
        ("Sentiment Analysis", [r"\bsentiment analysis\b"]),
        ("Cross-Lingual Transfer", [r"\bcross-lingual transfer\b", r"\bcross-lingual generalization\b"]),
        ("Text Classification", [r"\btext classification\b", r"\bdocument classification\b"]),
        ("Word Alignment", [r"\bword alignment\b", r"\bword-level alignment\b"]),
        ("Part-of-Speech Tagging", [r"\bpart-of-speech\b", r"\bpos\b"]),
    ]

    setting_rules = [
        ("Low-resource", [r"\blow-resource\b", r"\blow resource\b", r"\bresource-constrained\b", r"\bscarce resource\b"]),
        ("Multilingual", [r"\bmultilingual\b", r"\bmany-to-many\b", r"\bone-to-many\b"]),
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

    dataset_rules = [
        ("WMT", [r"\bWMT\b", r"\bWMT'?(?:1[4-9]|2[0-3])\b"]),
        ("FLORES-200", [r"\bFLORES-200\b", r"\bFLORES 200\b"]),
        ("FLORES-101", [r"\bFLORES-101\b", r"\bFLORES 101\b"]),
        ("FLORES", [r"\bFLORES\b"]),
        ("IWSLT", [r"\bIWSLT\b"]),
        ("Europarl", [r"\bEuroparl\b"]),
        ("SQuAD", [r"\bSQuAD\b"]),
        ("GLUE", [r"\bGLUE\b"]),
        ("SuperGLUE", [r"\bSuperGLUE\b"]),
        ("Multi30k", [r"\bMulti30k\b"]),
        ("Tatoeba", [r"\bTatoeba\b"]),
        ("OPUS", [r"\bOPUS\b"]),
        ("Samanantar", [r"\bSamanantar\b"]),
        ("IndicCorp", [r"\bIndicCorp\b"]),
    ]

    method_rules = [
        ("Transformer", [r"\btransformer(?:s)?\b", r"\btransformer architecture\b"]),
        ("Back-translation", [r"\bback-translation\b", r"\bbacktranslation\b", r"\bBT\b"]),
        ("Knowledge Distillation", [r"\bknowledge distillation\b", r"\bKD\b"]),
        ("Byte-Pair Encoding", [r"\bbyte-pair encoding\b", r"\bBPE\b"]),
        ("SentencePiece", [r"\bsentencepiece\b", r"\bSPM\b"]),
        ("Transfer Learning", [r"\btransfer learning\b", r"\bdomain transfer\b"]),
        ("Fine-tuning", [r"\bfine-tuning\b", r"\bfinetuning\b", r"\bparameter-efficient\b"]),
        ("Low-Rank Adaptation", [r"\blow-rank adaptation\b", r"\bLoRA\b"]),
        ("Adapter Tuning", [r"\badapter(?:s)? tuning\b", r"\bbottleneck adapter\b"]),
        ("Self-Attention", [r"\bself-attention\b", r"\bmulti-head attention\b"]),
        ("Cross-Attention", [r"\bcross-attention\b"]),
        ("FlashAttention", [r"\bflashattention\b", r"\bflash-attention\b"]),
        ("Data Augmentation", [r"\bdata augmentation\b", r"\bsynthetic data\b"]),
        ("Contrastive Learning", [r"\bcontrastive learning\b"]),
        ("Multi-Task Learning", [r"\bmulti-task learning\b", r"\bmultitask learning\b", r"\bMTL\b"]),
        ("Beam Search", [r"\bbeam search\b"]),
        ("Ensembling", [r"\bensembling\b", r"\bmodel ensemble\b"]),
        ("Prompt Tuning", [r"\bprompt tuning\b", r"\bprompt-tuning\b"]),
        ("Prefix Tuning", [r"\bprefix tuning\b"]),
        ("Statistical Machine Translation", [r"\bstatistical machine translation\b", r"\bSMT\b"]),
        ("Rule-Based Machine Translation", [r"\brule-based machine translation\b", r"\bRBMT\b"]),
        ("Recurrent Neural Network", [r"\brecurrent neural network\b", r"\bRNN\b"]),
        ("Long Short-Term Memory", [r"\blong short-term memory\b", r"\bLSTM\b", r"\bBiLSTM\b"]),
        ("Gated Recurrent Unit", [r"\bgated recurrent unit\b", r"\bGRU\b"]),
        ("Masked Language Modeling", [r"\bmasked language modeling\b", r"\bMLM\b"]),
        ("Causal Language Modeling", [r"\bcausal language modeling\b", r"\bCLM\b"]),
        ("Layer Normalization", [r"\blayer normalization\b", r"\bLayerNorm\b"]),
        ("Sentence Embeddings", [r"\bsentence embeddings\b", r"\bLASER\b", r"\bLaBSE\b"]),
        ("Reranking", [r"\breranking\b", r"\bn-best rescoring\b"]),
        ("Curriculum Learning", [r"\bcurriculum learning\b"]),
        ("Subword Regularization", [r"\bsubword regularization\b", r"\bBPE-dropout\b"]),
    ]

    records_a = []
    records_b = []
    differences = []
    check_set_records = []

    # Per-entity comparison counters
    entity_counts = {"method": {"a": 0, "b": 0, "agree": 0},
                     "dataset": {"a": 0, "b": 0, "agree": 0},
                     "task": {"a": 0, "b": 0, "agree": 0},
                     "setting": {"a": 0, "b": 0, "agree": 0}}

    for p in papers:
        pid = p["paper_id"]
        title = p["title"] or ""
        abstract = p["abstract"] or ""
        full_text = f"{title}. {abstract}"

        # Rule pass A (conservative): a match counts only with a cue in the title or a nearby cue word
        # Rule pass B (inclusive): every match in the title or abstract counts
        
        # 1. Tasks
        a_tasks = []
        b_tasks = []
        for canon, pats in task_rules:
            for pat in pats:
                if re.search(pat, full_text, re.IGNORECASE):
                    b_tasks.append(canon)
                    # pass A requires the title or a cue verb
                    if re.search(pat, title, re.IGNORECASE) or re.search(rf"\b(?:propose|evaluate|investigate|for)\b.*{pat}", full_text, re.IGNORECASE):
                        a_tasks.append(canon)
                    break

        # 2. Settings
        a_settings = []
        b_settings = []
        for canon, pats in setting_rules:
            for pat in pats:
                if re.search(pat, full_text, re.IGNORECASE):
                    b_settings.append(canon)
                    if re.search(pat, title, re.IGNORECASE) or "setting" in full_text.lower() or "scenario" in full_text.lower() or "data" in full_text.lower():
                        a_settings.append(canon)
                    break

        # 3. Datasets
        a_datasets = []
        b_datasets = []
        for canon, pats in dataset_rules:
            for pat in pats:
                if re.search(pat, full_text):
                    b_datasets.append(canon)
                    if any(k in full_text.lower() for k in ["dataset", "corpus", "benchmark", "tested on", "evaluated on", "results on"]):
                        a_datasets.append(canon)
                    break

        # 4. Methods
        a_methods = []
        b_methods = []
        for canon, pats in method_rules:
            for pat in pats:
                if re.search(pat, full_text):
                    b_methods.append(canon)
                    if any(k in full_text.lower() for k in ["propose", "use", "approach", "method", "model", "baseline", "via", "with"]):
                        a_methods.append(canon)
                    break

        a_tasks = list(dict.fromkeys(a_tasks))
        b_tasks = list(dict.fromkeys(b_tasks))
        a_settings = list(dict.fromkeys(a_settings))
        b_settings = list(dict.fromkeys(b_settings))
        a_datasets = list(dict.fromkeys(a_datasets))
        b_datasets = list(dict.fromkeys(b_datasets))
        a_methods = list(dict.fromkeys(a_methods))
        b_methods = list(dict.fromkeys(b_methods))

        # Count how often the two rule passes give the same labels
        for k, la, lb in [("task", a_tasks, b_tasks),
                          ("setting", a_settings, b_settings),
                          ("dataset", a_datasets, b_datasets),
                          ("method", a_methods, b_methods)]:
            entity_counts[k]["a"] += len(la)
            entity_counts[k]["b"] += len(lb)
            common = set(la) & set(lb)
            entity_counts[k]["agree"] += len(common)

        diffs = {
            "task": sorted(set(a_tasks) ^ set(b_tasks)),
            "setting": sorted(set(a_settings) ^ set(b_settings)),
            "dataset": sorted(set(a_datasets) ^ set(b_datasets)),
            "method": sorted(set(a_methods) ^ set(b_methods)),
        }
        if any(diffs.values()):
            differences.append({
                "paper_id": pid,
                "title": title,
                "diffs": {k: v for k, v in diffs.items() if v}
            })

        # Save rule pass A records
        for m in (a_methods if a_methods else [None]):
            records_a.append({
                "paper_id": pid,
                "method": m,
                "dataset": a_datasets[0] if a_datasets else None,
                "task": a_tasks[0] if a_tasks else None,
                "setting": a_settings[0] if a_settings else None
            })

        # Save rule pass B records
        for m in (b_methods if b_methods else [None]):
            records_b.append({
                "paper_id": pid,
                "method": m,
                "dataset": b_datasets[0] if b_datasets else None,
                "task": b_tasks[0] if b_tasks else None,
                "setting": b_settings[0] if b_settings else None
            })

        # Combine the two passes (a rule, not a person's decision): pass A's first task/setting/dataset,
        # pass B's if A has none; methods are the union of both passes
        cons_task = a_tasks[0] if a_tasks else (b_tasks[0] if b_tasks else None)
        cons_setting = a_settings[0] if a_settings else (b_settings[0] if b_settings else None)
        cons_dataset = a_datasets[0] if a_datasets else (b_datasets[0] if b_datasets else None)
        cons_methods = sorted(set(a_methods) | set(b_methods))   # sorted: a set's order changes from run to run

        if cons_methods:
            for m in cons_methods:
                check_set_records.append({
                    "paper_id": pid,
                    "method": m,
                    "dataset": cons_dataset,
                    "task": cons_task,
                    "setting": cons_setting
                })
        else:
            check_set_records.append({
                "paper_id": pid,
                "method": None,
                "dataset": cons_dataset,
                "task": cons_task,
                "setting": cons_setting
            })

    # Save rule pass A
    with open(OUT_PASS_A, "w", encoding="utf-8", newline="\n") as f:
        for r in records_a:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save rule pass B
    with open(OUT_PASS_B, "w", encoding="utf-8", newline="\n") as f:
        for r in records_b:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save the papers where the two passes differ
    with open(OUT_DIFFERENCES, "w", encoding="utf-8", newline="\n") as f:
        json.dump(differences, f, indent=2, ensure_ascii=False)

    # Save the combined rule-based check set (not ground truth)
    with open(OUT_CHECK_SET, "w", encoding="utf-8", newline="\n") as f:
        for r in check_set_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n--- OVERLAP OF THE TWO RULE PASSES (50 ABSTRACTS) ---")
    print("Both passes are regular expressions. This is NOT an inter-annotator agreement: no person labeled anything.")
    print(f"Papers where the two passes gave different labels: {len(differences)} / {len(papers)}")
    print(f"Papers where both passes gave the same labels: {(len(papers) - len(differences)) / len(papers) * 100:.1f}%")
    for k, v in entity_counts.items():
        total_mentions = max(v["a"], v["b"])
        same_pct = (v["agree"] / total_mentions * 100) if total_mentions else 100.0
        print(f"  {k:8}: passA={v['a']:2}, passB={v['b']:2}, same={v['agree']:2} -> same labels: {same_pct:5.1f}%")

    print(f"\nSaved rule pass A to: {OUT_PASS_A}")
    print(f"Saved rule pass B to: {OUT_PASS_B}")
    print(f"Saved the papers where the passes differ to: {OUT_DIFFERENCES}")
    print(f"Saved the rule-based check set to: {OUT_CHECK_SET}")


if __name__ == "__main__":
    label_with_rules()
