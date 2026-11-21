"""The SPECTER2 encoder: base model + proximity adapter, pinned to exact Hugging Face revisions.

torch, transformers and adapters are imported only when the model is first used, so importing this
module (and running the tests with a stub encoder) needs none of them.
"""

BASE_MODEL = "allenai/specter2_base"
BASE_REVISION = "3447645e1def9117997203454fa4495937bfbd83"
ADAPTER = "allenai/specter2"  # the "proximity" adapter, recommended for similarity and retrieval
ADAPTER_REVISION = "2081559630a80fc5851d8f798a05ba81e9468089"
# The adapter SPECTER2 recommends for SHORT QUERIES (papers are embedded with the proximity adapter above).
QUERY_ADAPTER = "allenai/specter2_adhoc_query"
QUERY_ADAPTER_REVISION = "3f4448817028388648a74349ece07af4518ec5bd"
QUERY_ADAPTERS = ("adhoc_query", "proximity")
MAX_LENGTH = 512


def model_string():
    """The value stored in paper.embedding_model."""
    return f"{BASE_MODEL}@{BASE_REVISION}+{ADAPTER}@{ADAPTER_REVISION} (proximity)"


class SpecterEncoder:
    """Paper-side encoder: the proximity adapter. Subclasses change only the three adapter attributes below."""
    model_string = model_string()
    adapter, adapter_revision, adapter_name = ADAPTER, ADAPTER_REVISION, "proximity"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._torch = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from adapters import AutoAdapterModel
        from transformers import AutoTokenizer

        torch.manual_seed(0)
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, revision=BASE_REVISION)
        # use_safetensors=False: load exactly the pinned pytorch_model.bin, never an unpinned
        # safetensors conversion that transformers might look up on the Hub.
        model = AutoAdapterModel.from_pretrained(BASE_MODEL, revision=BASE_REVISION, use_safetensors=False)
        model.load_adapter(self.adapter, source="hf", version=self.adapter_revision, load_as=self.adapter_name,
                           set_active=True)
        model.eval()
        self._model = model

    @property
    def sep_token(self):
        self._load()
        return self._tokenizer.sep_token

    def embed(self, texts):
        """Return one embedding (list of floats) per text: the first-token (CLS) vector of the last layer."""
        self._load()
        inputs = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt",
                                 return_token_type_ids=False, max_length=MAX_LENGTH)
        with self._torch.no_grad():
            output = self._model(**inputs)
        return output.last_hidden_state[:, 0, :].tolist()


class SpecterQueryEncoder(SpecterEncoder):
    """Query-side encoder: the same base model with the adhoc_query adapter. Only for query text; stored paper
    vectors are made by SpecterEncoder and are never touched by this class."""
    model_string = f"{BASE_MODEL}@{BASE_REVISION}+{QUERY_ADAPTER}@{QUERY_ADAPTER_REVISION} (adhoc_query)"
    adapter, adapter_revision, adapter_name = QUERY_ADAPTER, QUERY_ADAPTER_REVISION, "adhoc_query"


def make_query_encoder(adapter=None):
    """The encoder for query text. adapter: "adhoc_query" (default) or "proximity" (the old behaviour: queries
    encoded like papers). An argument wins over the PC_QUERY_ADAPTER environment variable."""
    import os
    adapter = adapter or os.environ.get("PC_QUERY_ADAPTER") or "adhoc_query"
    if adapter not in QUERY_ADAPTERS:
        raise ValueError(f"query adapter must be one of {', '.join(QUERY_ADAPTERS)}, got {adapter!r}")
    return SpecterQueryEncoder() if adapter == "adhoc_query" else SpecterEncoder()
