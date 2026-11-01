"""Measure whether SPECTER2 runs here at a usable speed and gives sensible embeddings.

Setup follows the model card: allenai/specter2_base + the "proximity" adapter allenai/specter2,
input = title + [SEP] + abstract, max_length 512, embedding = last_hidden_state[:, 0, :].
This is a measurement, not a decision. Nothing is written to PostgreSQL.

Usage (from db/experiments/embeddings/):  .venv\\Scripts\\python.exe embed_test.py
"""
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
os.environ["HF_HOME"] = str(DATA / "hf_cache")  # self-contained cache; set before importing transformers

import numpy as np  # noqa: E402
import torch  # noqa: E402
import transformers  # noqa: E402
import adapters  # noqa: E402
from adapters import AutoAdapterModel  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

BASE, ADAPTER, MAX_LENGTH, HIDDEN_EXPECTED = "allenai/specter2_base", "allenai/specter2", 512, 768
EXCLUDE_WORDS = ["survey", "review", "introduction", "overview", "progress", "tutorial"]
REPEATS = 3


# --- Windows helpers (no extra packages) -------------------------------------------------------

class MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def free_ram_gb():
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / 1024 ** 3, status.ullTotalPhys / 1024 ** 3


def peak_ram_gb():
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    counters = ProcessMemory()
    counters.cb = ctypes.sizeof(ProcessMemory)
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.PeakWorkingSetSize / 1024 ** 3


OVERLAYS = {"00000000-0000-0000-0000-000000000000": "Balanced",
            "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best power efficiency",
            "ded574b5-45a0-4f42-8737-46345c09c238": "Best performance"}


def power_info():
    status = PowerStatus()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    plugged = {0: "on battery", 1: "plugged in"}.get(status.ACLineStatus, "unknown")
    try:
        scheme = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True).stdout.strip()
    except OSError:
        scheme = "unknown"
    overlay = "not detected"
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes")
        name = "ActiveOverlayAcPowerScheme" if status.ACLineStatus == 1 else "ActiveOverlayDcPowerScheme"
        guid = winreg.QueryValueEx(key, name)[0].lower()
        overlay = f"{OVERLAYS.get(guid, 'unrecognised overlay')} ({guid})"
    except OSError:
        pass
    return plugged, status.BatteryLifePercent, scheme, overlay


def cpu_name():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except OSError:
        return platform.processor()


def folder_mb(path):
    # symlinks are skipped: the Hugging Face cache links snapshot files to blobs, which would double count
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file() and not f.is_symlink()) / 1e6


# --- model ------------------------------------------------------------------------------------

def load_model():
    tokenizer = AutoTokenizer.from_pretrained(BASE)
    model = AutoAdapterModel.from_pretrained(BASE)
    model.load_adapter(ADAPTER, source="hf", load_as="proximity", set_active=True)
    model.eval()
    return tokenizer, model


def make_text(tokenizer, paper):
    return paper["title"] + tokenizer.sep_token + (paper.get("abstract") or "")


def embed(tokenizer, model, papers, batch_size):
    out = []
    with torch.no_grad():
        for start in range(0, len(papers), batch_size):
            batch = [make_text(tokenizer, p) for p in papers[start:start + batch_size]]
            inputs = tokenizer(batch, padding=True, truncation=True, return_tensors="pt",
                               return_token_type_ids=False, max_length=MAX_LENGTH)
            out.append(model(**inputs).last_hidden_state[:, 0, :].cpu().numpy())
    return np.concatenate(out)


def timed_passes(tokenizer, model, papers, batch_size):
    """Warm up once, then time REPEATS full passes over all papers. Returns seconds per paper."""
    embed(tokenizer, model, papers[:8], batch_size)
    per_paper = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        embed(tokenizer, model, papers, batch_size)
        per_paper.append((time.perf_counter() - start) / len(papers))
    return per_paper


# --- neighbour / similarity analysis ----------------------------------------------------------

def neighbour_analysis(emb, labels, k=5):
    labels = np.array(labels)
    unit = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    sim = unit @ unit.T
    n = len(labels)
    np.fill_diagonal(sim, -np.inf)
    top = np.argsort(-sim, axis=1)[:, :k]
    same = labels[top] == labels[:, None]
    per_topic = {t: float(same[labels == t].mean()) for t in sorted(set(labels))}
    same_pair = labels[:, None] == labels[None, :]
    off_diag = ~np.eye(n, dtype=bool)
    sim0 = np.where(off_diag, sim, 0.0)
    within = float(sim0[same_pair & off_diag].mean())
    between = float(sim0[~same_pair].mean())
    within_topic = {t: float(sim0[(labels == t)[:, None] & (labels == t)[None, :] & off_diag].mean())
                    for t in sorted(set(labels))}
    counts = {t: int((labels == t).sum()) for t in sorted(set(labels))}
    baseline = float(np.mean([(counts[t] - 1) / (n - 1) for t in labels]))
    return {"n": n, "same_overall": float(same.mean()), "same_per_topic": per_topic,
            "within": within, "between": between, "within_per_topic": within_topic,
            "counts": counts, "random_baseline": baseline}


def stats(values):
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0), min(values), max(values)


# --- main -------------------------------------------------------------------------------------

def main():
    torch.manual_seed(0)
    np.random.seed(0)
    papers = [json.loads(line) for line in open(DATA / "abstracts.jsonl", encoding="utf-8")]
    labels = [p["topic_label"] for p in papers]
    log = {}

    free_gb, total_gb = free_ram_gb()
    plugged, battery_pct, scheme, overlay = power_info()
    print(f"RAM free at start: {free_gb:.1f} GB of {total_gb:.1f} GB")
    print(f"power: {plugged}, battery {battery_pct}%, {scheme}; mode overlay: {overlay}")
    log.update(free_gb=free_gb, total_gb=total_gb, plugged=plugged, battery_pct=battery_pct,
               scheme=scheme, overlay=overlay)

    cache_before = folder_mb(DATA / "hf_cache") if (DATA / "hf_cache").exists() else 0.0
    start = time.perf_counter()
    tokenizer, model = load_model()
    log["first_load_s"] = time.perf_counter() - start
    log["downloaded_this_run"] = cache_before < 1.0
    print(f"first model load: {log['first_load_s']:.1f} s (cache before: {cache_before:.0f} MB)")

    hidden = model.config.hidden_size
    log["hidden_size"] = hidden
    print(f"config.hidden_size = {hidden} (schema vector({HIDDEN_EXPECTED}))")
    if hidden != HIDDEN_EXPECTED:
        print("!!!!!! HIDDEN SIZE DIFFERS FROM THE SCHEMA'S vector(768) !!!!!!")

    # position 0 must be the CLS token
    probe = tokenizer([make_text(tokenizer, papers[0])], truncation=True, max_length=MAX_LENGTH,
                      return_tensors="pt", return_token_type_ids=False)
    first_id = int(probe["input_ids"][0][0])
    log.update(first_token_id=first_id, cls_token_id=tokenizer.cls_token_id,
               first_token=tokenizer.convert_ids_to_tokens(first_id), sep_token=tokenizer.sep_token)
    print(f"first token id {first_id} ({log['first_token']}) vs cls_token_id {tokenizer.cls_token_id}: "
          f"{'MATCH' if first_id == tokenizer.cls_token_id else 'MISMATCH'}")

    # truncation
    full_lengths = [len(tokenizer(make_text(tokenizer, p), truncation=False)["input_ids"]) for p in papers]
    truncated = [(p["openalex_id"], n) for p, n in zip(papers, full_lengths) if n > MAX_LENGTH]
    log.update(token_min=min(full_lengths), token_max=max(full_lengths),
               token_mean=statistics.mean(full_lengths), truncated=truncated)
    print(f"tokens per input: min {min(full_lengths)}, mean {statistics.mean(full_lengths):.0f}, "
          f"max {max(full_lengths)}; truncated at {MAX_LENGTH}: {len(truncated)}")

    threads, interop = torch.get_num_threads(), torch.get_num_interop_threads()
    log.update(threads=threads, interop=interop)
    print(f"torch threads: {threads} (interop {interop})")

    log["bs1"] = timed_passes(tokenizer, model, papers, 1)
    log["bs8"] = timed_passes(tokenizer, model, papers, 8)
    print("bs=1 s/paper:", [f"{x:.3f}" for x in log["bs1"]])
    print("bs=8 s/paper:", [f"{x:.3f}" for x in log["bs8"]])

    emb1 = embed(tokenizer, model, papers, 1)
    emb8 = embed(tokenizer, model, papers, 8)
    unit1 = emb1 / np.linalg.norm(emb1, axis=1, keepdims=True)
    unit8 = emb8 / np.linalg.norm(emb8, axis=1, keepdims=True)
    log["batch_cosine_min"] = float((unit1 * unit8).sum(axis=1).min())
    log["output_dim"] = int(emb1.shape[1])
    log["has_nan"] = bool(np.isnan(emb1).any())
    log["norm_mean"] = float(np.linalg.norm(emb1, axis=1).mean())
    np.save(DATA / "embeddings.npy", emb1)
    with open(DATA / "ids.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump([p["openalex_id"] for p in papers], f)
    print(f"saved embeddings {emb1.shape} (batch-size-1 run) and ids; batch1-vs-batch8 min cosine "
          f"{log['batch_cosine_min']:.6f}")

    log["peak_ram_gb"] = peak_ram_gb()
    log["cache_mb"] = folder_mb(DATA / "hf_cache")

    # quality
    log["all"] = neighbour_analysis(emb1, labels)
    keep = [i for i, p in enumerate(papers) if not any(w in p["title"].lower() for w in EXCLUDE_WORDS)]
    log["filtered"] = neighbour_analysis(emb1[keep], [labels[i] for i in keep])
    log["excluded_titles"] = [papers[i]["title"] for i in range(len(papers)) if i not in set(keep)]

    # second load, now from the local cache only
    start = time.perf_counter()
    load_model()
    log["cached_load_s"] = time.perf_counter() - start
    print(f"cached model load: {log['cached_load_s']:.1f} s")

    log["versions"] = {"python": sys.version.split()[0], "torch": torch.__version__,
                       "transformers": transformers.__version__, "adapters": adapters.__version__,
                       "numpy": np.__version__, "cpu": cpu_name(), "logical_cpus": os.cpu_count(),
                       "platform": platform.platform()}
    with open(DATA / "metrics.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(log, f, indent=1, default=str)
    write_results(log, len(papers))
    print("wrote results.md")


def write_results(log, n_papers):
    v = log["versions"]
    m1, s1, lo1, hi1 = stats(log["bs1"])
    m8, s8, lo8, hi8 = stats(log["bs8"])

    def extrapolate(sec, count):
        return f"{sec * count / 60:.1f} min"

    def topic_table(res):
        rows = ["| Topic | Papers | Same-topic fraction in top-5 | Mean cosine to same-topic papers |",
                "|---|---|---|---|"]
        for t, c in res["counts"].items():
            low = " (under 10!)" if c < 10 else ""
            rows.append(f"| {t} | {c}{low} | {res['same_per_topic'][t]:.2f} | {res['within_per_topic'][t]:.3f} |")
        return "\n".join(rows)

    a, b = log["all"], log["filtered"]
    dim_note = "matches the schema's vector(768)" if log["output_dim"] == 768 else "DOES NOT MATCH vector(768)"
    trunc = log["truncated"]
    trunc_text = (f"{len(trunc)} of {n_papers} inputs; full lengths in tokens: "
                  + ", ".join(str(n) for _, n in trunc)) if trunc else f"none of {n_papers} inputs"
    lines = f"""# SPECTER2 embedding experiment (open decision O3)

Measurement only, not a decision. Real abstracts from OpenAlex ({n_papers} papers, 4 topics, English, 2015 or later).
Setup: `allenai/specter2_base` + proximity adapter `allenai/specter2` (full SPECTER2 setup, as on the model card),
input `title + [SEP] + abstract`, `max_length=512`, embedding = `last_hidden_state[:, 0, :]`, `model.eval()`,
`torch.no_grad()`, seed 0, CPU only, torch build without CUDA.

## Environment

| Item | Value |
|---|---|
| Python | {v['python']} |
| torch | {v['torch']} |
| transformers | {v['transformers']} |
| adapters | {v['adapters']} |
| numpy | {v['numpy']} |
| CPU | {v['cpu']} ({v['logical_cpus']} logical CPUs) |
| OS | {v['platform']} |
| torch threads | {log['threads']} (interop {log['interop']}) |
| Power | {log['plugged']}; scheme: {log['scheme']}; mode overlay: {log['overlay']} |
| RAM free at start | {log['free_gb']:.1f} GB of {log['total_gb']:.1f} GB |

## Measurements

| Measurement | Result |
|---|---|
| First model load (incl. download: {log['downloaded_this_run']}) | {log['first_load_s']:.1f} s |
| Model load from local cache | {log['cached_load_s']:.1f} s |
| Output dimension | {log['output_dim']} ({dim_note}); `config.hidden_size` = {log['hidden_size']} |
| Position 0 token | id {log['first_token_id']} (`{log['first_token']}`), `cls_token_id` = {log['cls_token_id']}: {'match' if log['first_token_id'] == log['cls_token_id'] else 'MISMATCH'} |
| Speed, batch size 1 | {m1:.3f} s/paper mean, sd {s1:.3f}, range {lo1:.3f} to {hi1:.3f} ({REPEATS} passes of {n_papers} papers after warm-up) |
| Speed, batch size 8 | {m8:.3f} s/paper mean, sd {s8:.3f}, range {lo8:.3f} to {hi8:.3f} ({REPEATS} passes of {n_papers} papers after warm-up) |
| Extrapolated 5,000 papers | batch 1: {extrapolate(m1, 5000)}; batch 8: {extrapolate(m8, 5000)} |
| Extrapolated 10,000 papers | batch 1: {extrapolate(m1, 10000)}; batch 8: {extrapolate(m8, 10000)} |
| Peak RAM (process working set) | {log['peak_ram_gb']:.2f} GB |
| Model cache on disk (`data/hf_cache`) | {log['cache_mb']:.0f} MB |
| Input length (tokens) | min {log['token_min']}, mean {log['token_mean']:.0f}, max {log['token_max']} |
| Truncated at 512 tokens | {trunc_text} |
| NaNs in embeddings | {log['has_nan']} |
| Mean embedding L2 norm | {log['norm_mean']:.2f} |
| Batch 1 vs batch 8 embeddings, lowest cosine | {log['batch_cosine_min']:.6f} |

Extrapolation assumes the same abstract-length mix as these {n_papers} papers (mean {log['token_mean']:.0f} tokens) and no other load on the machine.

## Quality sanity check (5 nearest neighbours by cosine, excluding the paper itself)

Topic labels come from search results and are noisy, so this is a sanity check, not an evaluation.
Random baseline for 4 balanced topics is about 0.24 (24/99).

### (a) All {a['n']} papers

Same-topic fraction overall: **{a['same_overall']:.3f}** (random baseline {a['random_baseline']:.3f}).
Mean cosine within a topic: **{a['within']:.3f}**; between topics: **{a['between']:.3f}**.

{topic_table(a)}

### (b) Excluding titles containing survey, review, introduction, overview, progress or tutorial

{b['n']} papers remain ({a['n'] - b['n']} excluded). Same-topic fraction overall: **{b['same_overall']:.3f}** (random baseline {b['random_baseline']:.3f}).
Mean cosine within a topic: **{b['within']:.3f}**; between topics: **{b['between']:.3f}**.
{'**At least one topic has fewer than 10 papers here.**' if min(b['counts'].values()) < 10 else 'Every topic still has 10 or more papers.'}

{topic_table(b)}

## Caveats

- Sample is {n_papers} papers on 4 very different topics, so separation is expected to be easy. It says little about how well SPECTER2 separates close topics inside one field such as NLP.
- The sample leans toward survey and review papers (relevance-ranked search); (b) removes the most obvious ones by title.
- Timings are for this laptop, this power state, and this moment; other processes were running.
- Output dimension and speed say nothing about retrieval quality on the real corpus; that needs a labelled query set.
"""
    (HERE / "results.md").write_text(lines, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
