# scoring/ (Person 3)

Candidate generation and scoring for potentially underexplored research-element pairs. Each candidate is a signal for human review, not proof of a research gap.

| File | What it does |
|---|---|
| `signals.py` | expected count, smoothed sparsity, confidence, percentile rank, cosine, recent share, trend slope |
| `counts.py` | Distinct-paper pair counts under the same-universe rule: from the materialized views, from an on-the-fly query for a cutoff year, or from Python rows |
| `candidates.py` | Support threshold, observed < expected, `min_expected` filter, optional query-neighborhood restriction |
| `ranking.py` | Normalizes signals by percentile rank across candidates and scores them; unimplemented signals stay `None` |
| `score.py` | `Score = 100 * Σ w_i s_i`; weight sets `v1-three-signal` (default) and `v2-five-signal` |
| `sensitivity.py` | Shifts each weight by ±delta and reports top-k overlap |
| `holdout.py` | Temporal holdout metrics (P@k, AP) against random, sparsity-only and semantic-only baselines |
| `pipeline.py` | End to end against PostgreSQL; writes `opportunity` and `opportunity_evidence` in one transaction |

```bash
python -m scoring.pipeline --dsn $PG --pair-type method_task --min-support 10
```

Fixed choices (recorded in `context/decisions-and-progress.md`):
- Sparsity = `1 - (observed + 1) / (expected + 1)`, clipped to [0, 1].
- Confidence = `min(1, expected / k)`, k = 5 by default. Pairs with expected < 1 are dropped.

Still open (O6): weights, `min_support`, `k`, and the semantic filter threshold. All of them are parameters, so nothing is hard-coded.

Tests: `python -m pytest`. The integration tests need `PC_TEST_PG_DSN` (and `PC_TEST_NEO4J_URI` / `PC_TEST_NEO4J_PASSWORD` for the sync tests). They build the schema from the SQL in `context/data-and-contracts.md` and check the materialized views against raw counts.
