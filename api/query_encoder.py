"""Query-text encoder for POST /search.

Papers are embedded by Person 2's db/embeddings (SPECTER2 + proximity adapter). A query vector is
only comparable with paper vectors from the same model, so the repository checks the encoder's
model_string against paper.embedding_model before running a vector search.

Which adapter to use for queries (proximity vs specter2_adhoc_query) is still open on Person 2's side;
until it is decided the proximity encoder from db/embeddings is used.

Configuration:
    PC_QUERY_ENCODER=specter2 (default) | none
"""

from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from typing import Protocol

# needed by db.embeddings.encoder.SpecterEncoder; it imports them only when the model is first used
REQUIRED_PACKAGES = ("torch", "transformers", "adapters")


class QueryEncoder(Protocol):
    model_string: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@lru_cache(maxsize=1)
def get_query_encoder() -> QueryEncoder | None:
    """The query encoder, or None when it is switched off or its packages are not installed.

    The model itself (about 0.9 GB) is loaded on the first vector search, not here.
    """
    if os.environ.get("PC_QUERY_ENCODER", "specter2") == "none":
        return None
    if any(importlib.util.find_spec(m) is None for m in REQUIRED_PACKAGES):
        return None
    from db.embeddings.encoder import SpecterEncoder

    return SpecterEncoder()
