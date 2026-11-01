# SPECTER2 embedding experiment (open decision O3)

Measurement only, not a decision. Real abstracts from OpenAlex (100 papers, 4 topics, English, 2015 or later).
Setup: `allenai/specter2_base` + proximity adapter `allenai/specter2` (full SPECTER2 setup, as on the model card),
input `title + [SEP] + abstract`, `max_length=512`, embedding = `last_hidden_state[:, 0, :]`, `model.eval()`,
`torch.no_grad()`, seed 0, CPU only, torch build without CUDA.

## Environment

| Item | Value |
|---|---|
| Python | 3.12.3 |
| torch | 2.15.0+cpu |
| transformers | 4.57.6 |
| adapters | 1.3.0 |
| numpy | 2.5.4 |
| CPU | 13th Gen Intel(R) Core(TM) i7-13650HX (20 logical CPUs) |
| OS | Windows-11-10.0.26200-SP0 |
| torch threads | 14 (interop 14) |
| Power | plugged in; scheme: Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced); mode overlay: Balanced (00000000-0000-0000-0000-000000000000) |
| RAM free at start | 6.6 GB of 23.7 GB |

## Measurements

| Measurement | Result |
|---|---|
| First model load (incl. download: True) | 44.0 s |
| Model load from local cache | 2.4 s |
| Output dimension | 768 (matches the schema's vector(768)); `config.hidden_size` = 768 |
| Position 0 token | id 102 (`[CLS]`), `cls_token_id` = 102: match |
| Speed, batch size 1 | 0.125 s/paper mean, sd 0.001, range 0.125 to 0.126 (3 passes of 100 papers after warm-up) |
| Speed, batch size 8 | 0.171 s/paper mean, sd 0.010, range 0.159 to 0.177 (3 passes of 100 papers after warm-up) |
| Extrapolated 5,000 papers | batch 1: 10.4 min; batch 8: 14.3 min |
| Extrapolated 10,000 papers | batch 1: 20.8 min; batch 8: 28.5 min |
| Peak RAM (process working set) | 1.02 GB |
| Model cache on disk (`data/hf_cache`) | 884 MB (corrected: the script first reported 1768 MB because it followed cache symlinks and counted every file twice). The cache holds both `pytorch_model.bin` and a `model.safetensors` copy (about 440 MB each) plus the 3.4 MB adapter, so one copy of the model needs about 443 MB. |
| Input length (tokens) | min 85, mean 216, max 662 |
| Truncated at 512 tokens | 1 of 100 inputs; full lengths in tokens: 662 |
| NaNs in embeddings | False |
| Mean embedding L2 norm | 22.00 |
| Batch 1 vs batch 8 embeddings, lowest cosine | 1.000000 |

Extrapolation assumes the same abstract-length mix as these 100 papers (mean 216 tokens) and no other load on the machine.

## Quality sanity check (5 nearest neighbours by cosine, excluding the paper itself)

Topic labels come from search results and are noisy, so this is a sanity check, not an evaluation.
Random baseline for 4 balanced topics is about 0.24 (24/99).

### (a) All 100 papers

Same-topic fraction overall: **1.000** (random baseline 0.242).
Mean cosine within a topic: **0.918**; between topics: **0.806**.

| Topic | Papers | Same-topic fraction in top-5 | Mean cosine to same-topic papers |
|---|---|---|---|
| image segmentation | 25 | 1.00 | 0.915 |
| machine translation | 25 | 1.00 | 0.916 |
| protein structure prediction | 25 | 1.00 | 0.927 |
| reinforcement learning | 25 | 1.00 | 0.916 |

### (b) Excluding titles containing survey, review, introduction, overview, progress or tutorial

75 papers remain (25 excluded). Same-topic fraction overall: **0.995** (random baseline 0.250).
Mean cosine within a topic: **0.915**; between topics: **0.808**.
Every topic still has 10 or more papers.

| Topic | Papers | Same-topic fraction in top-5 | Mean cosine to same-topic papers |
|---|---|---|---|
| image segmentation | 17 | 1.00 | 0.906 |
| machine translation | 20 | 1.00 | 0.908 |
| protein structure prediction | 24 | 1.00 | 0.930 |
| reinforcement learning | 14 | 0.97 | 0.896 |

## Caveats

- Sample is 100 papers on 4 very different topics, so separation is expected to be easy. It says little about how well SPECTER2 separates close topics inside one field such as NLP.
- The sample leans toward survey and review papers (relevance-ranked search); (b) removes the most obvious ones by title.
- Timings are for this laptop, this power state, and this moment; other processes were running.
- Output dimension and speed say nothing about retrieval quality on the real corpus; that needs a labelled query set.
