"""Information extraction pipeline for Paper Compass (Person 1).

Extracts experiment tuples (paper_id, method, dataset, task, setting, confidence, source_sentence, extractor)
from paper titles and abstracts against the controlled vocabulary.

Conforms strictly to data contract section 3 and Person 2's loader:
- context/data-and-contracts.md §3
- db/loaders/extractions.py
"""

import argparse
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extraction")


def split_sentences(text):
    """Split abstract text into sentences while preserving sentence content."""
    if not text:
        return []
    # Insert missing space after periods connecting words directly (e.g. 'corpus.We')
    text = re.sub(r"(?<=[a-z0-9])\.(?=[A-Z])", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Protect common abbreviations
    protected = text
    for abbrev in ["e.g.", "i.e.", "et al.", "vs.", "fig.", "dr.", "mr.", "ms.", "prof.", "al."]:
        protected = re.sub(re.escape(abbrev), abbrev.replace(".", "@DOT@"), protected, flags=re.IGNORECASE)
    # Split on period, exclamation, question mark followed by space and capital or end
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9]|$)", protected)
    sentences = []
    for s in raw_sentences:
        s = s.replace("@DOT@", ".").strip()
        if len(s) > 10:
            sentences.append(s)
    return sentences


class VocabularyMatcher:
    """Fast regex-based entity matcher supporting canonical names and aliases."""

    def __init__(self, vocab_file):
        self.vocab_file = Path(vocab_file)
        self.entities = {"method": {}, "dataset": {}, "task": {}, "setting": {}}
        self._load_vocabulary()

    def _load_vocabulary(self):
        with open(self.vocab_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                kind = entry["type"]
                canonical = entry["canonical_name"]
                aliases = entry.get("aliases", [])

                # Map canonical to itself
                self._add_term(kind, canonical, canonical, is_canonical=True)

                # Map aliases to canonical
                for alias in aliases:
                    self._add_term(kind, alias, canonical, is_canonical=False)

    def _add_term(self, kind, term, canonical, is_canonical):
        # Escape for regex and require word boundary
        # If term has special symbols like '+', '-', 'v2', handle carefully
        escaped = re.escape(term)
        # Fix Item 6: Short uppercase aliases (<= 3 chars, e.g. KD, BT, BPE, POS, LM, NER)
        # MUST be case-sensitive and match whole words to prevent matching ordinary lowercase words.
        if len(term) <= 3 and term.isupper():
            pattern = re.compile(rf"\b{escaped}\b")
        else:
            pattern = re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
        self.entities[kind][pattern] = (canonical, is_canonical, len(term))

    def find_matches(self, text):
        """Find all matching entities in a given sentence."""
        matches = {"method": set(), "dataset": set(), "task": set(), "setting": set()}
        for kind, patterns in self.entities.items():
            for pattern, (canonical, is_canonical, length) in patterns.items():
                if pattern.search(text):
                    matches[kind].add((canonical, is_canonical, length))
        return matches


def extract_experiments_from_paper(paper, matcher, extractor_tag="rules-v1"):
    """Extract experiments from a single paper record.
    
    Strategy:
    1. Search sentence by sentence in the abstract.
    2. A sentence with at least one Method forms the nucleus of an experiment.
    3. Associated dataset, task, and setting are linked if present in the same sentence
       or inherited from the paper's overarching title/abstract context.
    4. Computes confidence based on sentence-level co-occurrence.
    """
    paper_id = paper.get("paper_id")
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""

    if not paper_id or not abstract:
        return []

    sentences = split_sentences(abstract)
    if not sentences and title:
        sentences = [title]

    # Global context from title
    title_matches = matcher.find_matches(title)
    global_tasks = {c for c, _, _ in title_matches["task"]}
    global_datasets = {c for c, _, _ in title_matches["dataset"]}
    global_settings = {c for c, _, _ in title_matches["setting"]}

    experiments = []
    seen_tuples = set()

    for sentence in sentences:
        s_matches = matcher.find_matches(sentence)
        s_methods = sorted(s_matches["method"], key=lambda x: -x[2])  # longest match first
        s_datasets = sorted(s_matches["dataset"], key=lambda x: -x[2])
        s_tasks = sorted(s_matches["task"], key=lambda x: -x[2])
        s_settings = sorted(s_matches["setting"], key=lambda x: -x[2])

        if not s_methods:
            continue

        for m_canonical, m_is_canon, _ in s_methods:
            # Determine dataset (sentence match preferred, else global context if unambiguous)
            dataset = s_datasets[0][0] if s_datasets else (list(global_datasets)[0] if len(global_datasets) == 1 else None)
            
            # Determine task (sentence match preferred, else global context, else fallback)
            if s_tasks:
                task = s_tasks[0][0]
            elif global_tasks:
                task = sorted(global_tasks, key=len, reverse=True)[0]
            elif any(w in (title + " " + abstract).lower() for w in ["machine translation", "translation", "nmt", "smt"]):
                task = "Machine Translation"
            else:
                task = None

            # Determine setting (sentence match preferred, else global, else keyword fallback)
            if s_settings:
                setting = s_settings[0][0]
            elif global_settings:
                setting = sorted(global_settings, key=len, reverse=True)[0]
            elif "low-resource" in (title + " " + abstract).lower() or "low resource" in (title + " " + abstract).lower():
                setting = "Low-resource"
            elif "multilingual" in (title + " " + abstract).lower():
                setting = "Multilingual"
            elif "zero-shot" in (title + " " + abstract).lower():
                setting = "Zero-shot"
            else:
                setting = None

            # Compute confidence score
            # Base confidence: 0.70 for sentence co-occurrence of method
            confidence = 0.70
            if s_datasets:
                confidence += 0.10  # Explicit dataset in same sentence
            if s_tasks:
                confidence += 0.05  # Explicit task in same sentence
            if s_settings:
                confidence += 0.05  # Explicit setting in same sentence
            if m_is_canon:
                confidence += 0.05  # Matched canonical rather than alias
            confidence = min(0.95, round(confidence, 2))

            # Filter by confidence threshold (O7: >= 0.70)
            if confidence < 0.70:
                continue

            key = (paper_id, m_canonical, dataset, task, setting)
            if key in seen_tuples:
                continue
            seen_tuples.add(key)

            experiments.append({
                "paper_id": paper_id,
                "method": m_canonical,
                "dataset": dataset,
                "task": task,
                "setting": setting,
                "confidence": confidence,
                "source_sentence": sentence,
                "extractor": extractor_tag
            })

    # Fallback: if no sentence-level method was extracted, check title
    if not experiments and title_matches["method"]:
        for m_canonical, _, _ in title_matches["method"]:
            d = list(global_datasets)[0] if global_datasets else None
            t = list(global_tasks)[0] if global_tasks else ("Machine Translation" if "machine translation" in title.lower() else None)
            s = list(global_settings)[0] if global_settings else None

            key = (paper_id, m_canonical, d, t, s)
            if key not in seen_tuples:
                seen_tuples.add(key)
                experiments.append({
                    "paper_id": paper_id,
                    "method": m_canonical,
                    "dataset": d,
                    "task": t,
                    "setting": s,
                    "confidence": 0.70,
                    "source_sentence": title,
                    "extractor": extractor_tag
                })

    return experiments


def run_extraction(papers_file, vocab_file, output_file, extractor_tag="rules-v1"):
    papers_path = Path(papers_file)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading vocabulary from {vocab_file}...")
    matcher = VocabularyMatcher(vocab_file)

    logger.info(f"Extracting experiments from {papers_file}...")
    total_papers = 0
    papers_with_experiments = 0
    total_experiments = 0

    with open(papers_path, "r", encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total_papers += 1
            paper = json.loads(line)
            exps = extract_experiments_from_paper(paper, matcher, extractor_tag=extractor_tag)
            if exps:
                papers_with_experiments += 1
                for exp in exps:
                    total_experiments += 1
                    fout.write(json.dumps(exp, ensure_ascii=False) + "\n")

    logger.info(f"Extraction complete!")
    logger.info(f"Total papers processed: {total_papers}")
    logger.info(f"Papers with extracted experiments: {papers_with_experiments} ({papers_with_experiments/total_papers*100:.1f}%)")
    logger.info(f"Total experiment tuples extracted: {total_experiments}")
    logger.info(f"Saved output to: {output_path}")

    return total_experiments


def main():
    parser = argparse.ArgumentParser(description="Extract experiments from papers against controlled vocabulary.")
    parser.add_argument("--papers", default="ingest/data/papers_pilot.jsonl", help="Path to input papers.jsonl")
    parser.add_argument("--vocab", default="ingest/data/vocabulary.jsonl", help="Path to controlled vocabulary.jsonl")
    parser.add_argument("--out", default="extraction/data/extractions_pilot.jsonl", help="Path to output extractions.jsonl")
    parser.add_argument("--tag", default="rules-v1", help="Extractor tag (e.g. rules-v1, llm-v1)")
    args = parser.parse_args()

    run_extraction(args.papers, args.vocab, args.out, extractor_tag=args.tag)


if __name__ == "__main__":
    main()
