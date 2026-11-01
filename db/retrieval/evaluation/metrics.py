"""Ranking metrics: precision@K, recall@K, reciprocal rank (and its mean) and nDCG@K.

Inputs
  ranked     list of paper ids, best first.
  relevance  dict paper_id -> grade, where grade is 0 (not relevant), 1 (relevant) or 2 (highly relevant).
             A paper that is not in the dict is unjudged and counts as 0.

Conventions (the same everywhere):
  * "Relevant" for precision, recall and reciprocal rank means grade >= 1. Grades 1 and 2 count the same
    there; only nDCG uses the difference.
  * Duplicate ids in `ranked`: only the first occurrence counts; later copies are dropped before positions
    are assigned (a repeated paper neither helps nor takes a rank).
  * Fewer than K results: the missing positions count as not relevant. Precision@K still divides by K.
  * No relevant paper in `relevance`: precision@K is 0.0 (nothing relevant was found). Recall, reciprocal
    rank and nDCG have a zero denominator and return None ("undefined"). Callers leave such queries out of
    means (see `mean`).

nDCG@K
  gain(grade)  = 2**grade - 1                 -> 0, 1, 3 for grades 0, 1, 2
  discount(i)  = 1 / log2(i + 1)              -> i is the 1-based rank: 1, 0.631, 0.5, 0.431, ...
  DCG@K        = sum over ranks i = 1..K of gain(grade of the paper at rank i) * discount(i)
  IDCG@K       = DCG@K of the ideal ranking (all judged grades sorted high to low, cut at K)
  nDCG@K       = DCG@K / IDCG@K, in [0, 1]; None when IDCG@K is 0 (no relevant paper).
The exponential gain rewards putting a grade-2 paper first more strongly than a linear gain would.
"""
import math

GRADES = (0, 1, 2)


def _check(ranked, relevance, k):
    """Validate the inputs and return (ranking without duplicates, relevance). Raises ValueError."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer of at least 1, got {k!r}")
    if not isinstance(ranked, (list, tuple)) or not all(isinstance(i, str) for i in ranked):
        raise ValueError("ranked must be a list of paper id strings")
    if not isinstance(relevance, dict):
        raise ValueError("relevance must be a dict of paper_id -> grade")
    for paper_id, grade in relevance.items():
        if isinstance(grade, bool) or not isinstance(grade, int) or grade not in GRADES:
            raise ValueError(f"relevance grade for {paper_id!r} must be 0, 1 or 2, got {grade!r}")
    seen, unique = set(), []
    for paper_id in ranked:
        if paper_id not in seen:
            seen.add(paper_id)
            unique.append(paper_id)
    return unique, relevance


def _relevant_total(relevance):
    return sum(1 for grade in relevance.values() if grade >= 1)


def precision_at_k(ranked, relevance, k):
    """Relevant papers among the first k results, divided by k."""
    ranked, relevance = _check(ranked, relevance, k)
    return sum(1 for paper_id in ranked[:k] if relevance.get(paper_id, 0) >= 1) / k


def recall_at_k(ranked, relevance, k):
    """Relevant papers among the first k results, divided by all relevant papers. None if there are none."""
    ranked, relevance = _check(ranked, relevance, k)
    total = _relevant_total(relevance)
    if total == 0:
        return None
    return sum(1 for paper_id in ranked[:k] if relevance.get(paper_id, 0) >= 1) / total


def reciprocal_rank(ranked, relevance, k=None):
    """1 / rank of the first relevant paper; 0.0 if there is none within the first k (all, if k is None).
    None if the query has no relevant paper at all."""
    ranked, relevance = _check(ranked, relevance, 1 if k is None else k)
    if _relevant_total(relevance) == 0:
        return None
    for rank, paper_id in enumerate(ranked[:k], start=1):
        if relevance.get(paper_id, 0) >= 1:
            return 1.0 / rank
    return 0.0


def _dcg(grades):
    return sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def ndcg_at_k(ranked, relevance, k):
    """Normalised discounted cumulative gain at k (formula in the module docstring). None if no relevant paper."""
    ranked, relevance = _check(ranked, relevance, k)
    if _relevant_total(relevance) == 0:
        return None
    dcg = _dcg([relevance.get(paper_id, 0) for paper_id in ranked[:k]])
    ideal = _dcg(sorted(relevance.values(), reverse=True)[:k])
    return dcg / ideal


def mean(values):
    """Mean of the values that are not None; None if there are none."""
    kept = [v for v in values if v is not None]
    return sum(kept) / len(kept) if kept else None


def mean_reciprocal_rank(runs, k=None):
    """MRR over (ranked, relevance) pairs. Queries without a relevant paper are left out."""
    return mean([reciprocal_rank(ranked, relevance, k) for ranked, relevance in runs])


def evaluate_query(ranked, relevance, k):
    """All metrics for one query at cutoff k."""
    return {
        "precision": precision_at_k(ranked, relevance, k),
        "recall": recall_at_k(ranked, relevance, k),
        "reciprocal_rank": reciprocal_rank(ranked, relevance, k),
        "ndcg": ndcg_at_k(ranked, relevance, k),
        "relevant_count": _relevant_total(relevance),
    }
