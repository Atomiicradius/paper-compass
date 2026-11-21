"""Tests for the query-side encoder (allenai/specter2_adhoc_query).

Papers are embedded with the proximity adapter; queries should use the adhoc_query adapter. The fast tests
replace torch, adapters and transformers with small fakes, so they need none of them and load no model. One test
marked `slow` runs the real model for both adapters (needs the embeddings environment and the cached model files).
"""
import math
import sys
import types

import pytest

from embeddings import encoder as enc

DIM = 768


def install_fakes(monkeypatch, calls):
    """Fake torch / adapters / transformers that record what the encoder asks for."""
    torch = types.ModuleType("torch")
    torch.manual_seed = lambda seed: None

    class NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    torch.no_grad = NoGrad

    class FakeModel:
        def load_adapter(self, name, source=None, version=None, load_as=None, set_active=None):
            calls["load_adapter"] = {"name": name, "source": source, "version": version, "load_as": load_as,
                                     "set_active": set_active}

        def eval(self):
            return self

    class AutoAdapterModel:
        @staticmethod
        def from_pretrained(name, revision=None, use_safetensors=None):
            calls["base"] = {"name": name, "revision": revision, "use_safetensors": use_safetensors}
            return FakeModel()

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(name, revision=None):
            calls["tokenizer"] = {"name": name, "revision": revision}
            return object()

    adapters_module = types.ModuleType("adapters")
    adapters_module.AutoAdapterModel = AutoAdapterModel
    transformers_module = types.ModuleType("transformers")
    transformers_module.AutoTokenizer = AutoTokenizer
    for name, module in (("torch", torch), ("adapters", adapters_module), ("transformers", transformers_module)):
        monkeypatch.setitem(sys.modules, name, module)


def load_with_fakes(monkeypatch, encoder):
    calls = {}
    install_fakes(monkeypatch, calls)
    encoder._load()
    return calls


def test_the_paper_encoder_still_uses_the_proximity_adapter(monkeypatch):
    calls = load_with_fakes(monkeypatch, enc.SpecterEncoder())
    assert calls["load_adapter"] == {"name": "allenai/specter2", "source": "hf",
                                     "version": "2081559630a80fc5851d8f798a05ba81e9468089",
                                     "load_as": "proximity", "set_active": True}
    assert calls["base"]["name"] == "allenai/specter2_base"
    assert enc.SpecterEncoder.model_string.endswith("(proximity)")
    assert "allenai/specter2@" in enc.SpecterEncoder.model_string


def test_the_query_encoder_uses_the_adhoc_query_adapter(monkeypatch):
    calls = load_with_fakes(monkeypatch, enc.SpecterQueryEncoder())
    assert calls["load_adapter"]["name"] == "allenai/specter2_adhoc_query"
    assert calls["load_adapter"]["version"] == enc.QUERY_ADAPTER_REVISION
    assert calls["load_adapter"]["load_as"] == "adhoc_query" and calls["load_adapter"]["set_active"] is True
    assert calls["base"]["name"] == "allenai/specter2_base" and calls["base"]["revision"] == enc.BASE_REVISION
    assert "allenai/specter2_adhoc_query@" in enc.SpecterQueryEncoder.model_string
    assert enc.SpecterQueryEncoder.model_string != enc.SpecterEncoder.model_string


def test_the_query_revision_is_a_full_commit_hash():
    assert len(enc.QUERY_ADAPTER_REVISION) == 40 and set(enc.QUERY_ADAPTER_REVISION) <= set("0123456789abcdef")


def test_make_query_encoder_selects_the_adapter(monkeypatch):
    monkeypatch.delenv("PC_QUERY_ADAPTER", raising=False)
    assert type(enc.make_query_encoder()) is enc.SpecterQueryEncoder, "adhoc_query is the default for queries"
    assert type(enc.make_query_encoder("adhoc_query")) is enc.SpecterQueryEncoder
    assert type(enc.make_query_encoder("proximity")) is enc.SpecterEncoder, "the old behaviour stays selectable"
    monkeypatch.setenv("PC_QUERY_ADAPTER", "proximity")
    assert type(enc.make_query_encoder()) is enc.SpecterEncoder, "the environment setting is used"
    assert type(enc.make_query_encoder("adhoc_query")) is enc.SpecterQueryEncoder, "an argument wins over the env"
    with pytest.raises(ValueError, match="query adapter"):
        enc.make_query_encoder("nonsense")


@pytest.mark.slow
def test_real_model_both_adapters_give_768_dim_vectors_and_differ():
    paper = enc.SpecterEncoder()
    query = enc.SpecterQueryEncoder()
    text = "quality estimation for machine translation"
    p_vec, q_vec = paper.embed([text])[0], query.embed([text])[0]
    assert len(p_vec) == DIM and len(q_vec) == DIM
    assert all(math.isfinite(x) for x in p_vec + q_vec)
    assert p_vec != q_vec, "the two adapters must give different vectors for the same text"
    assert paper._model.active_adapters is not None and query._model.active_adapters is not None
    assert str(paper._model.active_adapters) != str(query._model.active_adapters)
