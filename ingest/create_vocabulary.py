"""Generate curated controlled vocabulary for NLP / Machine Translation.

Conforms strictly to Person 2's loader specifications:
- db/proposals/vocabulary-format.md
- db/loaders/vocabulary.py
"""

import json
from pathlib import Path

# Methods: (canonical_name, [aliases])
METHODS = [
    ("Knowledge Distillation", ["KD", "teacher-student learning", "distillation"]),
    ("Transformer", ["Transformer architecture", "Vanilla Transformer", "Transformers"]),
    ("Back-translation", ["BT", "backtranslation", "iterative back-translation"]),
    ("Byte-Pair Encoding", ["BPE", "subword tokenization", "byte pair encoding"]),
    ("SentencePiece", ["SentencePiece tokenization", "SPM"]),
    ("WordPiece", ["WordPiece tokenization"]),
    ("Transfer Learning", ["cross-lingual transfer learning", "domain transfer", "parameter transfer"]),
    ("Fine-tuning", ["supervised fine-tuning", "full fine-tuning", "finetuning"]),
    ("Low-Rank Adaptation", ["LoRA", "low rank adaptation"]),
    ("Adapter Tuning", ["parameter-efficient adapter", "Pfeiffer adapter", "Houlsby adapter", "bottleneck adapters"]),
    ("Prompt Tuning", ["soft prompt tuning", "prompt-tuning"]),
    ("Prefix Tuning", ["prefix-tuning"]),
    ("Sentence Embeddings", ["bilingual sentence embeddings", "cross-lingual sentence embeddings", "LASER", "LaBSE"]),
    ("Beam Search", ["beam search decoding", "beam-search"]),
    ("Contrastive Learning", ["contrastive pre-training", "contrastive representation learning"]),
    ("Dual Learning", ["dual learning for MT", "dual learning framework"]),
    ("Data Augmentation", ["synthetic data augmentation", "paraphrase augmentation", "data-augmentation"]),
    ("Curriculum Learning", ["curriculum training"]),
    ("Multi-Task Learning", ["MTL", "multitask learning"]),
    ("Self-Attention", ["multi-head self-attention", "self attention"]),
    ("Cross-Attention", ["encoder-decoder attention", "cross attention"]),
    ("Masked Language Modeling", ["MLM", "masked LM"]),
    ("Causal Language Modeling", ["CLM", "autoregressive language modeling"]),
    ("Recurrent Neural Network", ["RNN", "vanilla RNN"]),
    ("Long Short-Term Memory", ["LSTM", "BiLSTM", "bidirectional LSTM"]),
    ("Gated Recurrent Unit", ["GRU", "bidirectional GRU"]),
    ("Convolutional Sequence to Sequence", ["ConvS2S", "convolutional seq2seq"]),
    ("Statistical Machine Translation", ["SMT", "phrase-based SMT"]),
    ("Phrase-Based Statistical Machine Translation", ["PBMT", "phrase-based translation"]),
    ("Syntax-Based Machine Translation", ["SBMT", "tree-to-string translation"]),
    ("Rule-Based Machine Translation", ["RBMT"]),
    ("Statistical Alignment Model", ["GIZA++", "fast_align"]),
    ("Subword Regularization", ["BPE-dropout"]),
    ("Model Pruning", ["structured pruning", "unstructured pruning", "network pruning"]),
    ("Quantization", ["INT8 quantization", "FP16 quantization", "post-training quantization"]),
    ("Weight Averaging", ["checkpoint averaging", "Stochastic Weight Averaging", "SWA"]),
    ("Ensembling", ["model ensembling", "checkpoint ensembling"]),
    ("Reinforcement Learning from Human Feedback", ["RLHF"]),
    ("Minimum Risk Training", ["MRT"]),
    ("Label Smoothing", ["label smoothed cross entropy"]),
    ("Layer Normalization", ["LayerNorm", "pre-layer norm", "post-layer norm"]),
    ("Rotary Position Embedding", ["RoPE"]),
    ("Relative Position Encoding", ["relative position embeddings"]),
    ("Cross-Lingual Language Model Pretraining", ["XLM", "cross-lingual pre-training"]),
    ("Denoising Sequence-to-Sequence", ["BART pre-training", "mBART pre-training"]),
    ("Multilingual Pre-training", ["mBERT pre-training", "XLM-RoBERTa pre-training"]),
    ("Pivot Translation", ["pivot-based translation", "bridge language translation"]),
    ("Lexical Constrained Decoding", ["constrained decoding", "lexically constrained MT"]),
    ("Document-Level Context Modeling", ["context-aware MT", "document-level NMT"]),
    ("Word2Vec", ["Skip-gram", "CBOW"]),
    ("FastText", ["subword word embeddings"]),
    ("GloVe", ["Global Vectors for Word Representation"]),
    ("Reranking", ["n-best rescoring", "BLEU rescoring", "hypothesis reranking"]),
    ("FlashAttention", ["flash-attention", "flash attention v2"]),
]

# Datasets: (canonical_name, [aliases])
DATASETS = [
    ("FLORES-200", ["FLORES200", "Flores-200 benchmark", "FLORES 200"]),
    ("FLORES-101", ["FLORES101", "Flores-101 benchmark"]),
    ("Samanantar", ["Samanantar Indic corpus", "AI4Bharat Samanantar"]),
    ("WMT14", ["WMT 2014", "WMT-14", "WMT 14 English-German"]),
    ("WMT16", ["WMT 2016", "WMT-16"]),
    ("WMT17", ["WMT 2017", "WMT-17"]),
    ("WMT18", ["WMT 2018", "WMT-18"]),
    ("WMT19", ["WMT 2019", "WMT-19"]),
    ("WMT20", ["WMT 2020", "WMT-20"]),
    ("WMT21", ["WMT 2021", "WMT-21"]),
    ("WMT22", ["WMT 2022", "WMT-22"]),
    ("WMT23", ["WMT 2023", "WMT-23"]),
    ("OPUS", ["OPUS open parallel corpus"]),
    ("OPUS-100", ["OPUS100", "OPUS-100 corpus"]),
    ("CCAligned", ["CCAligned parallel corpus"]),
    ("ParaCrawl", ["ParaCrawl corpus", "ParaCrawl v9"]),
    ("Europarl", ["Europarl parallel corpus", "European Parliament Proceedings"]),
    ("IWSLT", ["IWSLT benchmark", "IWSLT translation corpus"]),
    ("Multi30k", ["Multi30K multimodal dataset"]),
    ("Tatoeba", ["Tatoeba challenge", "Tatoeba translation corpus"]),
    ("PMIndia", ["PM India parallel corpus", "PMIndia corpus"]),
    ("IndicCorp", ["IndicCorp monolingual corpus", "IndicCorp v2"]),
    ("CCNet", ["CCNet filtered Common Crawl"]),
    ("Common Crawl", ["CommonCrawl dump", "CommonCrawl"]),
    ("WikiMatrix", ["WikiMatrix parallel sentences"]),
    ("XNLI", ["Cross-lingual NLI"]),
    ("TED Talks", ["TED talks multilingual corpus"]),
    ("News Commentary", ["WMT News Commentary"]),
    ("UN Parallel Corpus", ["United Nations Parallel Corpus", "UNPC"]),
    ("OpenSubtitles", ["OpenSubtitles2018", "OpenSubtitles corpus"]),
    ("JW300", ["JW300 corpus", "Jehovah Witness parallel corpus"]),
    ("MTNT", ["Machine Translation of Noisy Text"]),
    ("IITB Hindi-English", ["IITB English-Hindi corpus", "IIT Bombay parallel corpus"]),
    ("Bharat Parallel Corpus", ["BPCC", "AI4Bharat BPCC"]),
    ("CoNLL-2003", ["CoNLL 2003 NER", "CoNLL03"]),
    ("SQuAD", ["Stanford Question Answering Dataset", "SQuAD v1.1", "SQuAD v2.0"]),
    ("GLUE", ["GLUE benchmark"]),
    ("SuperGLUE", ["SuperGLUE benchmark"]),
    ("IndicGLUE", ["IndicGLUE benchmark"]),
]

# Tasks: (canonical_name, [aliases])
# Unified taxonomy: Machine Translation is the canonical task.
# Sub-types like low-resource/multilingual are Settings; neural/statistical are Methods.
TASKS = [
    ("Machine Translation", ["MT", "NMT", "Neural Machine Translation", "Statistical Machine Translation", "SMT", "Multilingual Machine Translation", "MMT", "automatic translation"]),
    ("Speech Translation", ["spoken language translation", "speech-to-text translation"]),
    ("Quality Estimation", ["translation quality estimation", "QE"]),
    ("Automatic Post-Editing", ["APE", "post-editing"]),
    ("Bitext Mining", ["parallel sentence extraction", "bitext filtering", "sentence mining"]),
    ("Cross-Lingual Transfer", ["cross-lingual generalization", "cross-lingual transfer"]),
    ("Language Modeling", ["LM", "autoregressive generation"]),
    ("Word Alignment", ["bilingual word alignment", "word-level alignment"]),
    ("Named Entity Recognition", ["NER", "entity extraction"]),
    ("Part-of-Speech Tagging", ["POS tagging", "POS"]),
    ("Dependency Parsing", ["syntactic parsing"]),
    ("Text Summarization", ["abstractive summarization", "extractive summarization", "summarization"]),
    ("Question Answering", ["QA", "reading comprehension"]),
    ("Sentiment Analysis", ["sentiment classification"]),
    ("Natural Language Inference", ["NLI", "textual entailment"]),
    ("Paraphrase Generation", ["paraphrasing"]),
    ("Text Classification", ["document classification"]),
    ("Morphological Analysis", ["morphology tagging"]),
]

# Settings: (canonical_name, MUST have aliases = [])
SETTINGS = [
    ("Low-resource", []),
    ("High-resource", []),
    ("Multilingual", []),
    ("Bilingual", []),
    ("Zero-shot", []),
    ("Few-shot", []),
    ("Unsupervised", []),
    ("Semi-supervised", []),
    ("Supervised", []),
    ("Out-of-domain", []),
    ("In-domain", []),
    ("Cross-lingual", []),
]


def generate_vocabulary(output_path="ingest/data/vocabulary.jsonl"):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    entries = []
    seen = {"method": set(), "dataset": set(), "task": set(), "setting": set()}

    for kind, items in [
        ("method", METHODS),
        ("dataset", DATASETS),
        ("task", TASKS),
        ("setting", SETTINGS),
    ]:
        for canonical, aliases in items:
            c_norm = canonical.lower().strip()
            if c_norm in seen[kind]:
                raise ValueError(f"Duplicate canonical name in {kind}: {canonical}")
            seen[kind].add(c_norm)

            cleaned_aliases = []
            for a in aliases:
                a_norm = a.lower().strip()
                if a_norm == c_norm or a_norm in cleaned_aliases:
                    continue
                cleaned_aliases.append(a.strip())

            entries.append({
                "type": kind,
                "canonical_name": canonical.strip(),
                "aliases": cleaned_aliases
            })

    with open(out, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Generated {len(entries)} vocabulary entries across 4 types into {out}:")
    for kind in seen:
        print(f"  - {kind}: {len(seen[kind])} entries")


if __name__ == "__main__":
    generate_vocabulary()
