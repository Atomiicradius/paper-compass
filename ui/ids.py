"""Paper ID handling for the UI.

The API takes plain OpenAlex IDs (W123...). The graph endpoint labels its nodes "Paper:W123", so an ID copied
from the graph (or from a pasted OpenAlex URL) must be reduced to the plain ID before it is sent to the API.
"""

from __future__ import annotations

_URL_PREFIX = "https://openalex.org/"


def normalize_paper_id(raw: str) -> str:
    s = (raw or "").strip()
    if s.lower().startswith(_URL_PREFIX):
        s = s[len(_URL_PREFIX):]
    if s.lower().startswith("paper:"):
        s = s[len("paper:"):]
    return s.strip()


def paper_id_from_node(node: dict) -> str:
    return normalize_paper_id(node["id"])
