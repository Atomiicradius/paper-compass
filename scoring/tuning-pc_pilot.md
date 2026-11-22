# Scoring on real data: Method × Task on `pc_pilot` (O6)

Person 3, 2026-11-22. Database `pc_pilot`, restored from `pc_pilot_2026-11-21.dump` (1,999 papers, 1,055 experiments, 1,999 SPECTER2 embeddings). All numbers below come from runs on that date with the commands shown. Nothing is estimated.

A candidate opportunity is a **potentially underexplored** research-element combination: a signal for human review, never a proven gap. The holdout below measures whether a flagged pair was taken up later *in this corpus*. That is predictive signal, not proof that the pair was a gap.

## 1. What the real counts look like

Method × Task same-universe N = **399 papers** (papers with both a method and a task extracted). The universe is dominated by one task:

| Task | papers (n_B) | | Method | papers (n_A) |
|---|---:|---|---|---:|
| Machine Translation | 338 | | Transformer | 107 |
| Language Modeling | 26 | | Fine-tuning | 93 |
| Question Answering | 10 | | Back-translation | 66 |
| Cross-Lingual Transfer | 6 | | Transfer Learning | 65 |
| 10 more tasks | ≤ 5 each | | Data Augmentation | 62 |
| | | | Statistical MT | 59 |
| | | | 31 more methods | ≤ 19 each |

88 distinct pairs are observed. Method × Dataset (N = 32) and Dataset × Task (N = 27) are too small to score meaningfully and were not run.

Consequence: any method with n_A papers has expected ≈ 0.85 · n_A with Machine Translation, so near-misses like Fine-tuning × MT (78 observed vs 78.8 expected) pass `observed < expected`. Section 3 adds a sparsity floor for this reason.

## 2. Temporal holdout

`python -m scoring.tune --dsn $PG --cutoffs 2020 2021 2022 2023 --min-supports 3 5 8 10 [--min-sparsity S] [--new-only]`

For each cutoff Y, candidates and signals are built from papers ≤ Y only (same code path as `scoring.pipeline`). A **hit** is a candidate pair used together in ≥ 1 paper after Y. The scores are mean average precision (AP) and P@10 over the four cutoffs. Random is averaged over 100 shuffles.

Two hit definitions were run, because they disagree:

- **any later use**: every candidate counts. Pairs that already co-occur a little tend to keep co-occurring, so this label rewards low sparsity.
- **first use after Y** (`--new-only`): only candidates with observed = 0 at Y. A hit means the pair was used together for the first time later. This is closer to what the score is meant to flag.

**Mean AP, `min_support = 5`, `k = 5`:**

| ranking | any later use, no sparsity floor | any later use, min_sparsity 0.3 | any later use, min_sparsity 0.4 | first use after Y |
|---|---:|---:|---:|---:|
| **v1-three-signal (0.40 / 0.35 / 0.25)** | 0.835 | 0.829 | **0.860** | **0.975** |
| semantic only | 0.961 | 0.882 | 0.854 | 0.954 |
| sparsity only | 0.592 | 0.631 | 0.670 | 0.728 |
| random | 0.617 | 0.550 | 0.510 | 0.488 |
| candidates / hits per cutoff (2020..2023) | 12/9, 15/10, 21/10, 20/7 | 8/5, 11/6, 15/6, 15/4 | 7/4, 10/5, 14/5, 14/3 | 7/4, 9/4, 12/3, 10/1 |

Best weights on a 0.05 grid (171 vectors, each signal ≥ 0.05):
- any later use, no floor: 0.10 / 0.85 / 0.05, AP 0.963. This is in effect "semantic only".
- first use after Y: 0.55 / 0.05 / 0.40, AP 0.988. In effect sparsity + temporal.
- first use, every weight ≥ 0.2: 0.45 / 0.20 / 0.35, AP 0.988, vs v1 at 0.975.

Full results: `scoring/out/tuning-pc_pilot*.json` (not committed; re-run the command).

## 3. Decision (O6, for pc_pilot)

| Parameter | Value | Why |
|---|---|---|
| weights | **keep `v1-three-signal` (0.40 / 0.35 / 0.25)** | Beats random and sparsity-only under both hit definitions. Within 0.013 AP of the best grid vector on "first use". The two definitions pull towards opposite corners of the simplex, so neither "best" vector can be trusted. With 1–10 hits per cutoff, one rank swap moves AP by more than the gaps between the top vectors, so a 0.05-step tune would be fitting noise. |
| `min_support` | **5** (was 10) | At 10, only 3 tasks qualify. At 5 there are 23 candidates and the holdout results are the same or better. |
| `min_sparsity` | **0.3** (new, default 0.0 keeps old behaviour) | Drops pairs used together almost as often as expected (Fine-tuning × MT 78 vs 78.8, LoRA × MT 10 vs 10.2, LSTM × MT 11 vs 13.6). At 0.3 v1 stays well above random (0.829 vs 0.550); at 0.4 v1 beats semantic-only. |
| `k` (confidence) | **5** (unchanged) | The confidence is shown, not scored. 5 papers expected is the point where an observed count of 0 starts to mean something. |
| `min_expected` | **1.0** (unchanged) | |
| semantic filter `min_semantic` | **none** | Every remaining candidate is kept and the reader sees the value. |

Revisit when the corpus grows: re-run `scoring.tune` with the same commands.

## 4. Sensitivity (full corpus, min_support 5, before the sparsity floor)

Each weight shifted by ±0.1, others rescaled: top-10 overlap 0.8–1.0. Shifted by ±0.2: top-5 overlap 0.4–1.0. Lowering sparsity by 0.2 changes the top 5 most (overlap 0.4). The ranking is moderately sensitive, so the UI shows every signal value and offers what-if weight sliders.

## 5. Stored result

`python -m scoring.pipeline --dsn $PG --pair-type method_task --min-support 5 --min-sparsity 0.3 --k 5 --replace` stored **13 opportunities** with 252 evidence rows. Re-running with `--replace` leaves exactly 13; it does not duplicate them.

| # | Method × Task | obs | exp | sparsity | semantic | temporal | conf | score |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Masked Language Modeling × Machine Translation | 1 | 11.86 | 0.84 | 0.75 | 0.55 | 1.00 | 73.7 |
| 2 | Transformer × Cross-Lingual Transfer | 0 | 1.61 | 0.62 | 0.92 | 0.57 | 0.32 | 70.9 |
| 3 | Fine-tuning × Language Modeling | 1 | 6.06 | 0.72 | 0.83 | 0.51 | 1.00 | 70.6 |
| 4 | Cross-Lingual LM Pretraining × Machine Translation | 4 | 6.78 | 0.36 | 1.00 | 0.69 | 1.00 | 66.6 |
| 5 | Back-translation × Language Modeling | 1 | 4.30 | 0.62 | 0.67 | 0.43 | 0.86 | 59.1 |
| 6 | Data Augmentation × Language Modeling | 0 | 4.04 | 0.80 | 0.42 | 0.47 | 0.81 | 58.4 |
| 7 | Statistical MT × Language Modeling | 0 | 3.84 | 0.79 | 0.33 | 0.15 | 0.77 | 47.3 |
| 8 | Byte-Pair Encoding × Language Modeling | 0 | 1.24 | 0.55 | 0.50 | 0.26 | 0.25 | 46.1 |
| 9 | Transfer Learning × Language Modeling | 2 | 4.24 | 0.43 | 0.58 | 0.33 | 0.85 | 45.7 |
| 10 | Back-translation × Question Answering | 0 | 1.65 | 0.62 | 0.17 | 0.49 | 0.33 | 43.0 |
| 11 | Transformer × Natural Language Inference | 0 | 1.34 | 0.57 | 0.25 | 0.25 | 0.27 | 37.9 |
| 12 | Data Augmentation × Question Answering | 0 | 1.55 | 0.61 | 0.00 | 0.53 | 0.31 | 37.6 |
| 13 | Statistical MT × Question Answering | 0 | 1.48 | 0.60 | 0.08 | 0.21 | 0.30 | 32.1 |

Evidence rows: supports_A 64, supports_B 65, bridge 58, nearest_existing 65.

**Raw-SQL check (rule 5)** for #1: N = 399, n_A = 14, n_B = 338, observed = 1, expected = 14 · 338 / 399 = 11.8596, sparsity = 1 − 2 / 12.8596 = 0.8445. These equal the stored values. `/opportunities/14/explain` reports the same counts, and its citation check passes.

Reading the list: #1 does not claim nobody has used masked LM for translation. It says that in this corpus, among 14 MLM papers with a task, only 1 is a translation paper, where about 12 would be expected. The nearest-existing-work papers on the detail screen are the first thing to check. Several low-confidence rows (conf ≈ 0.3) rest on 1–2 expected papers and should be read as weak signals.

## 6. Reproducibility (found 2026-11-22)

The same pipeline on the same data gave two different temporal-activity values on Python 3.11 and 3.12 (opportunity 15:
0.577 vs 0.567; opportunity 22: 0.317 vs 0.327). Python 3.12 sums floats with compensation and 3.11 does not; two
elements whose trend slopes are mathematically equal then differed in the last bit, and percentile ranking turned that
into a one-step rank change. `scoring/signals.py` now computes the trend slope with exact rational arithmetic and uses
`math.fsum`, and tests pin both (`test_signals.py`). Checked afterwards: identical results on 3.11.9 and 3.12.13 for all
13 candidates, a rerun reproduces the stored rows on all 8 fields, a cold restore of the dump plus
`python -m api.prepare_demo` gives the same 13 rows, and every holdout number in section 2 reproduces to three decimals.
The values stored and published here are the exact ones; the 3.11 results before the fix were the inaccurate ones.

## 7. Known limits of the data (measured on pc_pilot, 2026-11-22)

These come from queries on the restored dump. The counts marked *heuristic* use simple text rules and are estimates, not
labels. None of this is extraction accuracy: no human-labelled benchmark exists (the reference set is rule-generated and
circular, see `extraction/accuracy_report.md`).

| Limit | What was measured | Effect on the 13 candidates |
|---|---|---|
| Duplicate records | 51 titles occur more than once (105 papers); 9 extra copies sit in the 399-paper Method x Task data | Removing them leaves the same 13 candidates and the same top 5; expected counts move by less than 0.1 |
| Proceedings / front matter as papers (*heuristic*) | 7 titles look like proceedings volumes, 1 of them in the extraction output, 1 of 399 in the Method x Task data | negligible |
| Abstracts that begin with an author list (*heuristic*) | about 80 papers, 11 in the extraction output, 5 of 399 in the Method x Task data | negligible; these papers' extracted elements are less reliable |
| One task dominates | Machine Translation is 338 of the 399 papers in the Method x Task data | most expected counts are driven by it; only Method x Task is scored (Method x Dataset has N = 32, Dataset x Task N = 27) |
| "Used together" means the same abstract | An experiment stores one source sentence, where the **method** was found. It also mentions the tagged task in only 350 of 719 task-tagged experiments (48.7%); the task is found elsewhere in the title or abstract | a method and a task counted as "used together" were both extracted from one paper, not necessarily from one sentence |
| Task tags that are not in the paper's text | 10 of 719 task tags (1.4%) appear in neither title nor abstract, all "Machine Translation". Some are errors (GraphCodeBERT is code translation; mT5's abstract never mentions translation), some are fine (a seq2seq paper whose title says "translation") | small; it can add a wrong paper to a "Machine Translation" group |
| Keyword search needs every word | PostgreSQL full-text search ANDs the words: "machine translation unicorn" finds nothing | use the vector or hybrid mode; the API says why when keyword search finds nothing |

**Choosing demo pairs.** Confidence is shown on every candidate. The most defensible are those with confidence 1.00 and no
duplicate-title evidence: #14 Masked Language Modeling x Machine Translation, #16 Fine-tuning x Language Modeling and
#17 Cross-Lingual Language Model Pretraining x Machine Translation. Low-confidence candidates (#15, #21, #23, #24, #25,
#26, all below 0.35) rest on one or two expected papers; present them as weak signals. For #14 the "Nearest Existing" list
includes mT5, tagged Machine Translation although its abstract does not mention it: say so if asked.
