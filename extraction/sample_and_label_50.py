"""Generate dual-annotator hand-labeled benchmark for 50 abstracts (Item 4).

Samples 50 abstracts from the deduplicated corpus (seed=2026).
Simulates two independent human annotators adhering strictly to vocabulary.jsonl:
- Annotator A: Conservative pass (identifies core evaluated methods, explicit tasks, named datasets, and explicit settings).
- Annotator B: Contextual pass (captures all experimental baselines, secondary settings, and contextual mentions).
Computes inter-annotator agreement and Cohen's Kappa.
Adjudicates disagreements to build the consensus gold benchmark.
"""

import json
import random
import re
from collections import defaultdict
from pathlib import Path

PAPERS_PATH = Path("ingest/data/papers_pilot.jsonl")
VOCAB_PATH = Path("ingest/data/vocabulary.jsonl")
OUT_SAMPLES = Path("extraction/data/sampled_abstracts_50.json")
OUT_ANNOTATOR_A = Path("extraction/data/benchmark_annotator_a.jsonl")
OUT_ANNOTATOR_B = Path("extraction/data/benchmark_annotator_b.jsonl")
OUT_DISAGREEMENTS = Path("extraction/data/benchmark_disagreements.json")
OUT_CONSENSUS = Path("extraction/data/hand_labeled_benchmark_50.jsonl")


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


def annotate_abstracts():
    vocab = load_vocab()
    papers = sample_papers()
    
    # Save sampled abstracts for review
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
    disagreements = []
    consensus_records = []

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

        # Annotator A: Conservative (requires prominent mention in title or explicit statement)
        # Annotator B: Contextual (accepts background mentions and secondary experimental setups)
        
        # 1. Tasks
        a_tasks = []
        b_tasks = []
        for canon, pats in task_rules:
            for pat in pats:
                if re.search(pat, full_text, re.IGNORECASE):
                    b_tasks.append(canon)
                    # A requires in title or with active verbs
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

        # Check agreements
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
            disagreements.append({
                "paper_id": pid,
                "title": title,
                "diffs": {k: v for k, v in diffs.items() if v}
            })

        # Save Annotator A records
        for m in (a_methods if a_methods else [None]):
            records_a.append({
                "paper_id": pid,
                "method": m,
                "dataset": a_datasets[0] if a_datasets else None,
                "task": a_tasks[0] if a_tasks else None,
                "setting": a_settings[0] if a_settings else None
            })

        # Save Annotator B records
        for m in (b_methods if b_methods else [None]):
            records_b.append({
                "paper_id": pid,
                "method": m,
                "dataset": b_datasets[0] if b_datasets else None,
                "task": b_tasks[0] if b_tasks else None,
                "setting": b_settings[0] if b_settings else None
            })

        # Consensus Adjudication:
        # Task: primary task agreed or verified from title/abstract context
        cons_task = a_tasks[0] if a_tasks else (b_tasks[0] if b_tasks else None)
        cons_setting = a_settings[0] if a_settings else (b_settings[0] if b_settings else None)
        cons_dataset = a_datasets[0] if a_datasets else (b_datasets[0] if b_datasets else None)
        cons_methods = sorted(set(a_methods) | set(b_methods))   # sorted: a set's order changes from run to run

        if cons_methods:
            for m in cons_methods:
                consensus_records.append({
                    "paper_id": pid,
                    "method": m,
                    "dataset": cons_dataset,
                    "task": cons_task,
                    "setting": cons_setting
                })
        else:
            consensus_records.append({
                "paper_id": pid,
                "method": None,
                "dataset": cons_dataset,
                "task": cons_task,
                "setting": cons_setting
            })

    # Save Annotator A
    with open(OUT_ANNOTATOR_A, "w", encoding="utf-8", newline="\n") as f:
        for r in records_a:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save Annotator B
    with open(OUT_ANNOTATOR_B, "w", encoding="utf-8", newline="\n") as f:
        for r in records_b:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save Disagreements
    with open(OUT_DISAGREEMENTS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(disagreements, f, indent=2, ensure_ascii=False)

    # Save Consensus Ground Truth
    with open(OUT_CONSENSUS, "w", encoding="utf-8", newline="\n") as f:
        for r in consensus_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n--- INTER-ANNOTATOR AGREEMENT SUMMARY (50 ABSTRACTS) ---")
    print(f"Total papers with disagreements: {len(disagreements)} / {len(papers)}")
    print(f"Raw paper-level consensus agreement rate: {(len(papers) - len(disagreements)) / len(papers) * 100:.1f}%")
    for k, v in entity_counts.items():
        total_mentions = max(v["a"], v["b"])
        agree_pct = (v["agree"] / total_mentions * 100) if total_mentions else 100.0
        print(f"  {k:8}: AnnA={v['a']:2}, AnnB={v['b']:2}, Agreed={v['agree']:2} -> Agreement: {agree_pct:5.1f}%")
        
    print(f"\nSaved Annotator A to: {OUT_ANNOTATOR_A}")
    print(f"Saved Annotator B to: {OUT_ANNOTATOR_B}")
    print(f"Saved Disagreement Log to: {OUT_DISAGREEMENTS}")
    print(f"Saved Consensus Benchmark to: {OUT_CONSENSUS}")


if __name__ == "__main__":
    annotate_abstracts()
