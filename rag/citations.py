"""Citation markers and their verification.

MARKER FORMAT
A paper is cited by writing its id inside a marker:  [paper:ID]
  * `[paper:` in lower case, then the id, then `]`, all on ONE line.
  * The id is one or more characters other than whitespace, `[` and `]`. Punctuation inside the id is
    fine (for example [paper:10.1234/abc-1] or [paper:MOCK_P001]). Ids are case-sensitive.
  * No space after the colon. `[paper: W1]`, `[Paper:W1]`, `[paper:]` and a marker split across a line
    break are NOT valid markers; they are counted as malformed (see verify_citations).
  * Only markers count. An id written in the prose without a marker (for example "W123 shows ...") is
    ignored by both functions. This is a limitation: the check cannot see uncited ids, so text generators
    must be told to cite with markers only.
"""
import re

MARKER = re.compile(r"\[paper:([^\[\]\s]+)\]")
MARKER_START = re.compile(r"\[paper:", re.IGNORECASE)   # case-insensitive so [Paper:W1] is caught as malformed


def _text(text):
    if not isinstance(text, str):
        raise ValueError(f"text must be a string, got {type(text).__name__}")
    return text


def extract_paper_ids(text):
    """The paper ids cited with valid [paper:ID] markers, without duplicates, in order of first appearance.

    Malformed markers (a space after the colon, wrong case, an empty id, an unclosed marker, a marker split
    across lines) yield no id. A bare id in the prose is not a citation. Empty text gives [].
    Raises ValueError if text is not a string.
    """
    seen = []
    for match in MARKER.finditer(_text(text)):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def verify_citations(text, allowed_ids):
    """Check that every cited paper is in the allowed set (the retrieved evidence).

    Returns a dict:
      ok                      False if any cited id is not in allowed_ids, or if any malformed marker exists
                              (a citation that cannot be read cannot be verified); otherwise True
      cited                   ids from valid markers, no duplicates, in order of first appearance
      unknown                 the cited ids that are not in allowed_ids (same order)
      uncited_markers_count   number of "[paper:" openings that did not form a valid marker
      has_no_citations        True if no valid marker was found; an answer that names no papers is ok
                              (if it has no malformed markers) but flagged

    allowed_ids is any iterable of ids; matching is exact (case-sensitive). Raises ValueError if text is not
    a string or allowed_ids is not iterable.
    """
    text = _text(text)
    try:
        allowed = set(allowed_ids)
    except TypeError:
        raise ValueError("allowed_ids must be an iterable of paper ids") from None
    cited = extract_paper_ids(text)
    unknown = [pid for pid in cited if pid not in allowed]
    malformed = len(MARKER_START.findall(text)) - len(MARKER.findall(text))
    return {"ok": not unknown and malformed == 0, "cited": cited, "unknown": unknown,
            "uncited_markers_count": malformed, "has_no_citations": not cited}
