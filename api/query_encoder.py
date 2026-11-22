"""Query-text encoder for POST /search.

Papers are embedded by Person 2's db/embeddings (SPECTER2 base model + the "proximity" adapter). A query is
encoded with Person 2's query-side encoder (`make_query_encoder`): the same base model with the
`specter2_adhoc_query` adapter by default, which is built for short query text. Both encoders write into the same
vector space, so a query vector is comparable with the stored paper vectors. The repository therefore checks the
stored `paper.embedding_model` against `paper_model_string` (what the papers were made with), not against the
query adapter's own `model_string`.

Configuration:
    PC_QUERY_ENCODER=specter2 (default) | none
    PC_QUERY_ADAPTER=adhoc_query (default) | proximity   (read by db.embeddings.encoder.make_query_encoder)
"""

from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from typing import Protocol

# needed by db.embeddings.encoder; it imports them only when the model is first used
REQUIRED_PACKAGES = ("torch", "transformers", "adapters")


class QueryEncoder(Protocol):
    model_string: str          # what encoded the query (reported in the response)
    paper_model_string: str    # the model the stored paper embeddings must come from (checked by the repository)

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SpecterQueryEncoderAdapter:
    """Wraps Person 2's query encoder and adds the paper-side model string used for the compatibility check."""

    def __init__(self, inner):
        from db.embeddings.encoder import model_string as paper_model_string

        self._inner = inner
        self.model_string: str = inner.model_string
        self.paper_model_string: str = paper_model_string()

    @property
    def loaded(self) -> bool:
        """True once the model is in memory (the first embed call loads it, which takes about 30 seconds)."""
        return getattr(self._inner, "_model", None) is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed(texts)


@lru_cache(maxsize=1)
def get_query_encoder() -> QueryEncoder | None:
    """The query encoder, or None when it is switched off or its packages are not installed.

    The model itself (about 0.9 GB) is loaded on the first vector search, not here.
    """
    if os.environ.get("PC_QUERY_ENCODER", "specter2") == "none":
        return None
    if any(importlib.util.find_spec(m) is None for m in REQUIRED_PACKAGES):
        return None
    from db.embeddings.encoder import make_query_encoder

    return SpecterQueryEncoderAdapter(make_query_encoder())
