"""A deterministic text summary of an evidence chain. A fixed template: no LLM, no randomness.

The wording follows AGENTS.md: observations first, then one hedged inference ("potentially underexplored",
"candidate research opportunity"), never "definitely unexplored", "guaranteed research gap" or "nobody has
done this". Papers are named only with [paper:ID] markers (see citations.py), and only papers from the
evidence, so the text can be checked with verify_citations.
"""
import re

REQUIRED = ("pair", "corpus", "yearly", "roles", "limitations")
RECENT_YEARS = 3


def _clean(value):
    """Corpus text (names, titles, sentences) made safe to place in the summary: whitespace collapsed to
    single spaces, and anything that looks like a citation marker disarmed, so corpus text can never create
    or damage a [paper:ID] marker."""
    return re.sub(r"\[paper:", "(paper:", " ".join(str(value).split()), flags=re.IGNORECASE)


def _papers(n):
    return f"{n} paper" if n == 1 else f"{n} papers"


def _corpus_section(evidence):
    a, b = evidence["pair"]["a"], evidence["pair"]["b"]
    c = evidence["corpus"]
    name_a, name_b = _clean(a["name"]), _clean(b["name"])
    lines = [
        f"- Analyzed corpus: papers published up to {c['cutoff_year']} in which both a {a['kind']} and a "
        f"{b['kind']} were extracted ({_papers(c['universe_size'])}).",
        f'- "{name_a}" ({a["kind"]}) is used in {_papers(c["n_a"])} and "{name_b}" ({b["kind"]}) in '
        f'{_papers(c["n_b"])}.',
        f"- The two are used together in {_papers(c['observed'])} (in one experiment); if they were combined "
        f"independently, about {c['expected']:.1f} papers would be expected.",
    ]
    recent = evidence["yearly"][-RECENT_YEARS:]
    if recent:
        series = "; ".join(f"{y['year']}: {y['a']} / {y['b']} / {y['both']}" for y in recent)
        lines.append(f'- Papers per year in the most recent years (using "{name_a}" / using "{name_b}" / using '
                     f"both): {series}.")
    else:
        lines.append("- No papers with a known year were found for this pair.")
    return lines


def _inference(evidence):
    c = evidence["corpus"]
    if c["universe_size"] == 0 or c["n_a"] == 0 or c["n_b"] == 0:
        return ("There is too little extracted data in the analyzed corpus to draw an inference about this "
                "research-element combination.")
    counts = f"{c['observed']} observed versus about {c['expected']:.1f} expected"
    if c["observed"] < c["expected"]:
        return (f"This research-element combination is potentially underexplored in the analyzed corpus "
                f"({counts}); it is a candidate research opportunity for review, not a proven research gap.")
    return (f"In the analyzed corpus this research-element combination is not weakly represented ({counts}), "
            f"so it is not flagged as a candidate research opportunity.")


def _closest_section(evidence):
    a, b = evidence["pair"]["a"], evidence["pair"]["b"]
    name_a, name_b = _clean(a["name"]), _clean(b["name"])
    papers = evidence["roles"]["nearest_existing"]
    if not papers:
        return ["- No closely related papers were found in the analyzed corpus."]
    lines = []
    for p in papers:
        uses = p.get("uses")
        if p["tier"] == "exact" or uses == "both":
            what = f'uses both "{name_a}" and "{name_b}" in one experiment'
        elif uses == "a":
            what = (f'uses "{name_a}" but not "{name_b}"; its embedding is similar to papers that use '
                    f'"{name_b}" (similarity {p["similarity"]:.2f})')
        elif uses == "b":
            what = (f'uses "{name_b}" but not "{name_a}"; its embedding is similar to papers that use '
                    f'"{name_a}" (similarity {p["similarity"]:.2f})')
        else:
            what = f"is a close match (similarity {p['similarity']:.2f})"
        lines.append(f"- [paper:{p['paper_id']}] {_clean(p['title'])} ({p['year']}): {what}.")
        if p.get("source_sentence"):
            lines.append(f'  Source sentence: "{_clean(p["source_sentence"])}"')
    return lines


def summarize_evidence(evidence):
    """A readable summary of a build_evidence dict, built from a fixed template (no LLM). The input is not
    modified and the same input always gives the same text.

    Four sections, each a "## " heading:
      What the corpus shows      counts as observations: corpus size, n_a, n_b, observed versus expected, and
                                 the most recent years
      What the system infers     one sentence. If observed < expected: the combination is potentially
                                 underexplored in the analyzed corpus and is a candidate for review, not a
                                 proven gap. If observed >= expected: it is not weakly represented and is
                                 not flagged. If the universe or either element has no papers: too little
                                 data for an inference.
      Closest existing work      the nearest_existing papers, each with a [paper:ID] marker, what it uses, and
                                 its stored source sentence (verbatim apart from whitespace) when there is one
      Limitations                the evidence's limitations, one bullet each

    Only papers listed in evidence["roles"]["nearest_existing"] are named, so verify_citations(text,
    collect_paper_ids(evidence)) passes. Corpus text is disarmed so it cannot forge a marker.
    Raises ValueError if evidence is not a dict or lacks one of: pair, corpus, yearly, roles, limitations.
    """
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a dict as returned by build_evidence")
    for key in REQUIRED:
        if key not in evidence:
            raise ValueError(f"evidence is missing {key!r}")
    sections = [
        ("What the corpus shows", _corpus_section(evidence)),
        ("What the system infers", [_inference(evidence)]),
        ("Closest existing work", _closest_section(evidence)),
        ("Limitations", [f"- {_clean(item)}" for item in evidence["limitations"]]),
    ]
    return "\n\n".join(f"## {title}\n" + "\n".join(lines) for title, lines in sections) + "\n"
