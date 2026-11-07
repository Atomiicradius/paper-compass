"""extract.py must give the same output every time.

Python randomizes string hashing per process, so the order of a set of strings differs from run to run. If
the extractor picks from a set (or sorts a set with ties), its output changes between runs. A test inside one
process cannot see that, so these tests run extract.py in separate processes with different PYTHONHASHSEED
values and compare the output files byte for byte.

The fixture is tiny and written to a temp folder; extraction/data is never read or written. It is built so
that every kind of tie occurs: two methods, datasets, tasks and settings whose names have the same length,
in one sentence and in a title (the title-only fallback and the title-context paths).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

EXTRACT = Path(__file__).resolve().parents[1] / "extract.py"
SEEDS = range(12)

VOCABULARY = [
    {"type": "method", "canonical_name": "Alpha Method", "aliases": []},
    {"type": "method", "canonical_name": "Gamma Method", "aliases": []},
    {"type": "dataset", "canonical_name": "Data One", "aliases": []},
    {"type": "dataset", "canonical_name": "Data Two", "aliases": []},
    {"type": "task", "canonical_name": "Task One", "aliases": []},
    {"type": "task", "canonical_name": "Task Two", "aliases": []},
    {"type": "setting", "canonical_name": "Low-resource", "aliases": []},
    {"type": "setting", "canonical_name": "Multilingual", "aliases": []},
]

PAPERS = [
    # everything in ONE sentence: ties between two methods, two datasets, two tasks and two settings
    {"paper_id": "P1", "title": "A study",
     "abstract": "We study Alpha Method and Gamma Method on Data One and Data Two for Task One and Task Two "
                 "in a Low-resource and Multilingual setting."},
    # no method in any sentence: the fallback takes the methods, dataset, task and setting from the title
    {"paper_id": "P2",
     "title": "Alpha Method versus Gamma Method for Task One and Task Two with Data One and Data Two "
              "in Low-resource and Multilingual settings",
     "abstract": "We describe a pipeline."},
    # task and setting are inherited from the title, which names two of each
    {"paper_id": "P3", "title": "A Low-resource and Multilingual study of Task One and Task Two",
     "abstract": "We apply Alpha Method to a new corpus."},
    # no abstract: skipped
    {"paper_id": "P4", "title": "Alpha Method", "abstract": None},
]


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("extract_fixture")
    write_jsonl(folder / "papers.jsonl", PAPERS)
    write_jsonl(folder / "vocabulary.jsonl", VOCABULARY)
    return folder


def run_extract(folder, seed, name):
    """Run extract.py in its own process with the given hash seed; return the output file's bytes."""
    out = folder / f"out_{name}.jsonl"
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    subprocess.run([sys.executable, str(EXTRACT), "--papers", str(folder / "papers.jsonl"),
                    "--vocab", str(folder / "vocabulary.jsonl"), "--out", str(out)],
                   env=env, check=True, capture_output=True)
    return out.read_bytes()


def test_the_output_is_byte_identical_for_every_hash_seed(inputs):
    outputs = {seed: run_extract(inputs, seed, f"seed{seed}") for seed in SEEDS}
    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        f"{len(distinct)} different outputs from {len(outputs)} hash seeds; seeds per output: "
        + str({hash(o) % 10_000: [s for s, v in outputs.items() if v == o] for o in distinct}))


def test_two_runs_with_the_same_seed_and_a_different_seed_agree(inputs):
    assert run_extract(inputs, 0, "a") == run_extract(inputs, 0, "b") == run_extract(inputs, 12345, "c")


def test_ties_are_broken_longest_first_then_alphabetically(inputs):
    rows = [json.loads(line) for line in run_extract(inputs, 7, "ties").decode("utf-8").splitlines()]
    got = [(r["paper_id"], r["method"], r["dataset"], r["task"], r["setting"], r["confidence"]) for r in rows]
    assert got == [
        # P1: methods in name order; the first dataset, task and setting by name win the ties
        ("P1", "Alpha Method", "Data One", "Task One", "Low-resource", 0.95),
        ("P1", "Gamma Method", "Data One", "Task One", "Low-resource", 0.95),
        # P2: title fallback, methods in name order, ties again by name
        ("P2", "Alpha Method", "Data One", "Task One", "Low-resource", 0.65),
        ("P2", "Gamma Method", "Data One", "Task One", "Low-resource", 0.65),
        # P3: task and setting inherited from the title, ties by name; no dataset
        ("P3", "Alpha Method", None, "Task One", "Low-resource", 0.75),
    ]
    assert all(r["extractor"] == "rules-v1" for r in rows)


def test_the_output_has_one_json_object_per_line_and_ends_with_a_newline(inputs):
    data = run_extract(inputs, 3, "format")
    assert data.endswith(b"\n") and b"\r" not in data
    assert len(data.decode("utf-8").splitlines()) == 5
