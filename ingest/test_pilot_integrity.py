"""Dry-run integrity checker for the pilot data (run from anywhere: python ingest/test_pilot_integrity.py).

Checks, with its own rules written to mirror the format rules of Person 2's loaders (it does not import the
loaders):
1. ingest/data/vocabulary.jsonl: valid types, settings without aliases
2. ingest/data/papers_pilot.jsonl: unique paper_id, title, venue_type, author order
3. extraction/data/extractions_pilot.jsonl: every paper_id exists in the papers file
4. every entity name in the extractions maps to a canonical vocabulary name or an alias

Every check is counted. The script prints PASS only when every failure count is zero; otherwise it prints the
failures and exits with a non-zero status. The three paths can be overridden (--vocab, --papers, --extractions).
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

INGEST_DIR = Path(__file__).resolve().parent
ROOT_DIR = INGEST_DIR.parent

VOCAB_PATH = ROOT_DIR / "ingest" / "data" / "vocabulary.jsonl"
PAPERS_PATH = ROOT_DIR / "ingest" / "data" / "papers_pilot.jsonl"
EXTRACTIONS_PATH = ROOT_DIR / "extraction" / "data" / "extractions_pilot.jsonl"

VENUE_TYPES = ("conference", "journal", "workshop", "preprint", "other")
TYPES = ("method", "dataset", "task", "setting")

# every failure kind, in the order they are reported (all are printed, also when 0)
FAILURE_KINDS = (
    "vocabulary: line is not a JSON object",
    "vocabulary: unknown type or missing canonical_name",
    "vocabulary: setting has aliases",
    "papers: line is not a JSON object",
    "papers: missing or duplicate paper_id",
    "papers: missing title",
    "papers: invalid venue_type",
    "papers: author without a name or an integer order",
    "extractions: line is not a JSON object",
    "extractions: paper_id not in the papers file",
    "extractions: entity not in the vocabulary or its aliases",
)


class Failures:
    """Counts failures per kind and keeps the first few examples of each."""

    def __init__(self):
        self.counts = Counter()
        self.examples = defaultdict(list)

    def add(self, kind, message):
        assert kind in FAILURE_KINDS, kind
        self.counts[kind] += 1
        if len(self.examples[kind]) < 5:
            self.examples[kind].append(message)

    def total(self):
        return sum(self.counts.values())


def read_rows(path, kind, failures):
    """Yield (line number, object) for each non-empty line; a line that is not a JSON object is a failure."""
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                failures.add(kind, f"line {number}: invalid JSON ({exc.msg})")
                continue
            if not isinstance(row, dict):
                failures.add(kind, f"line {number}: not a JSON object")
                continue
            yield number, row


def check_vocabulary(path, failures):
    canonical = {t: set() for t in TYPES}
    aliases = {t: set() for t in TYPES}
    entries = 0
    for number, row in read_rows(path, "vocabulary: line is not a JSON object", failures):
        entries += 1
        kind, name = row.get("type"), row.get("canonical_name")
        if kind not in TYPES or not isinstance(name, str) or not name.strip():
            failures.add("vocabulary: unknown type or missing canonical_name", f"line {number}: {row.get('type')!r}, {name!r}")
            continue
        canonical[kind].add(name.lower().strip())
        row_aliases = row.get("aliases") or []
        if kind == "setting" and row_aliases:
            failures.add("vocabulary: setting has aliases", f"line {number}: {name!r} has {len(row_aliases)} alias(es)")
        aliases[kind].update(a.lower().strip() for a in row_aliases if isinstance(a, str))
    return entries, canonical, aliases


def check_papers(path, failures):
    paper_ids, papers, authors, references = set(), 0, 0, 0
    for number, row in read_rows(path, "papers: line is not a JSON object", failures):
        papers += 1
        pid = row.get("paper_id")
        if not isinstance(pid, str) or not pid or pid in paper_ids:
            failures.add("papers: missing or duplicate paper_id", f"line {number}: {pid!r}")
        else:
            paper_ids.add(pid)
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            failures.add("papers: missing title", f"line {number}: paper {pid!r}")
        if row.get("venue_type") and row["venue_type"] not in VENUE_TYPES:
            failures.add("papers: invalid venue_type", f"line {number}: {row['venue_type']!r}")
        for author in row.get("authors") or []:
            order = author.get("order") if isinstance(author, dict) else None
            if not isinstance(author, dict) or not author.get("name") or isinstance(order, bool) or not isinstance(order, int):
                failures.add("papers: author without a name or an integer order", f"line {number}: paper {pid!r}")
            authors += 1
        references += len(row.get("references") or [])
    return paper_ids, papers, authors, references


def check_extractions(path, paper_ids, canonical, aliases, failures):
    experiments = 0
    for number, row in read_rows(path, "extractions: line is not a JSON object", failures):
        experiments += 1
        if row.get("paper_id") not in paper_ids:
            failures.add("extractions: paper_id not in the papers file", f"line {number}: {row.get('paper_id')!r}")
        for kind in TYPES:
            value = row.get(kind)
            if value:
                normalized = str(value).lower().strip()
                if normalized not in canonical[kind] and normalized not in aliases[kind]:
                    failures.add("extractions: entity not in the vocabulary or its aliases",
                                 f"line {number}: {kind} {value!r}")
    return experiments


def run_checks(vocab_path=VOCAB_PATH, papers_path=PAPERS_PATH, extractions_path=EXTRACTIONS_PATH):
    """Run every check. Returns (what was read, Failures)."""
    failures = Failures()
    entries, canonical, aliases = check_vocabulary(vocab_path, failures)
    paper_ids, papers, authors, references = check_papers(papers_path, failures)
    experiments = check_extractions(extractions_path, paper_ids, canonical, aliases, failures)
    read = {"vocabulary entries": entries, "papers": papers, "authors": authors, "citation edges": references,
            "experiments": experiments}
    return read, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dry-run integrity check of the pilot data files.")
    parser.add_argument("--vocab", default=str(VOCAB_PATH))
    parser.add_argument("--papers", default=str(PAPERS_PATH))
    parser.add_argument("--extractions", default=str(EXTRACTIONS_PATH))
    args = parser.parse_args(argv)

    read, failures = run_checks(args.vocab, args.papers, args.extractions)
    print("=" * 60)
    print("PILOT DATA INTEGRITY (dry run: this script's own checks, it does not call the loaders)")
    print("=" * 60)
    print(f"1. Vocabulary: {read['vocabulary entries']} entries read.")
    print(f"2. Papers: {read['papers']} papers read ({read['authors']} authors, {read['citation edges']} citation edges).")
    print(f"3. Extractions: {read['experiments']} experiments read.")
    print("\nFailure counts (every one must be 0):")
    for kind in FAILURE_KINDS:
        print(f"   {failures.counts[kind]:5d}  {kind}")
    if failures.total() == 0:
        print("\nRESULT: PASS (every failure count is 0)")
        print("=" * 60)
        return 0
    print(f"\nRESULT: FAIL ({failures.total()} failures)")
    for kind in FAILURE_KINDS:
        for example in failures.examples[kind]:
            print(f"   {kind}: {example}")
        if failures.counts[kind] > len(failures.examples[kind]):
            print(f"   {kind}: ... and {failures.counts[kind] - len(failures.examples[kind])} more")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
