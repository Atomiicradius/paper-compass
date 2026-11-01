"""Check that the SPECTER2 proximity adapter is really active when embedding.

Compares embeddings with the adapter active against the base model alone, and against the saved
embeddings from embed_test.py. Reads only from the local cache.
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
os.environ["HF_HOME"] = str(DATA / "hf_cache")
os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np  # noqa: E402
import torch  # noqa: E402
from adapters import AutoAdapterModel  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

papers = [json.loads(line) for line in open(DATA / "abstracts.jsonl", encoding="utf-8")][:8]
tokenizer = AutoTokenizer.from_pretrained("allenai/specter2_base")
model = AutoAdapterModel.from_pretrained("allenai/specter2_base")
print("adapters before load:", list(model.adapters_config.adapters.keys()))
model.load_adapter("allenai/specter2", source="hf", load_as="proximity", set_active=True)
model.eval()
print("adapters after load:", list(model.adapters_config.adapters.keys()))
print("active_adapters:", model.active_adapters)


def embed():
    texts = [p["title"] + tokenizer.sep_token + p["abstract"] for p in papers]
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt",
                       return_token_type_ids=False, max_length=512)
    with torch.no_grad():
        return model(**inputs).last_hidden_state[:, 0, :].numpy()


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


with_adapter = embed()
saved = np.load(DATA / "embeddings.npy")[:8]
print("cosine(with adapter now, saved embed_test embeddings): min",
      f"{(unit(with_adapter) * unit(saved)).sum(axis=1).min():.6f}")

model.set_active_adapters(None)
print("active_adapters after deactivating:", model.active_adapters)
base_only = embed()
cos = (unit(with_adapter) * unit(base_only)).sum(axis=1)
print(f"cosine(adapter vs base only): min {cos.min():.4f} mean {cos.mean():.4f} "
      "(clearly below 1 means the adapter changes the output)")
