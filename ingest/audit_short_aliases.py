import json
import re

papers = [json.loads(line) for line in open("ingest/data/papers_pilot.jsonl", encoding="utf-8")]

short_aliases = [
    ("APE", "Automatic Post-Editing", "task"),
    ("BPE", "Byte-Pair Encoding", "method"),
    ("BT", "Back-translation", "method"),
    ("CLM", "Causal Language Modeling", "method"),
    ("GRU", "Gated Recurrent Unit", "method"),
    ("KD", "Knowledge Distillation", "method"),
    ("LM", "Language Modeling", "task"),
    ("MLM", "Masked Language Modeling", "method"),
    ("MMT", "Machine Translation", "task"),
    ("MRT", "Minimum Risk Training", "method"),
    ("MT", "Machine Translation", "task"),
    ("MTL", "Multi-Task Learning", "method"),
    ("NER", "Named Entity Recognition", "task"),
    ("NLI", "Natural Language Inference", "task"),
    ("NMT", "Machine Translation", "task"),
    ("POS", "Part-of-Speech Tagging", "task"),
    ("QA", "Question Answering", "task"),
    ("QE", "Quality Estimation", "task"),
    ("RNN", "Recurrent Neural Network", "method"),
    ("SMT", "Statistical Machine Translation", "method"),
    ("SPM", "SentencePiece", "method"),
    ("SWA", "Weight Averaging", "method"),
    ("WMT", "WMT", "dataset"),
    ("XLM", "Cross-Lingual Language Model Pretraining", "method"),
]

print(f"{'Alias':5} | {'Case-Sens (\\b[A-Z]\\b)':20} | {'Case-Insens':12} | {'Diff (eliminated)':18} | {'Sample Match'}")
print("-" * 90)

for alias, canon, kind in short_aliases:
    cs_pat = re.compile(rf"\b{alias}\b")
    ci_pat = re.compile(rf"\b{alias}\b", re.IGNORECASE)
    
    cs_hits = []
    ci_count = 0
    
    for p in papers:
        text = (p.get("title") or "") + ". " + (p.get("abstract") or "")
        m_cs = list(cs_pat.finditer(text))
        m_ci = list(ci_pat.finditer(text))
        
        if m_cs:
            for m in m_cs:
                start = max(0, m.start() - 25)
                end = min(len(text), m.end() + 25)
                snippet = text[start:end].replace("\n", " ").strip()
                cs_hits.append(snippet)
        ci_count += len(m_ci)
        
    diff = ci_count - len(cs_hits)
    sample = cs_hits[0][:40] + "..." if cs_hits else "(no hits)"
    print(f"{alias:5} | {len(cs_hits):20} | {ci_count:12} | {diff:18} | {sample}")
