"""Diagnosis: why does vector search miss some queries on the pilot database? (read-only, a testing aid)

Run from db/ with the embeddings environment (needs numpy and the cached model files):
  embeddings/.venv/Scripts/python.exe -m retrieval.diagnose_uniformity --dbname pc_pilot

The database connection is opened read-only. Queries are encoded with the default query adapter (adhoc_query).
All ranks come from an exact cosine ranking over the stored vectors (brute force, all papers), not from the HNSW
index; one table checks that search() agrees with it on the top 5. Nothing here changes search() or any module.

It runs five checks and writes the data sections of db/retrieval-diagnosis.md. The interpretation sections that
follow ("What this shows", "Recommendation") are written by hand after reading the numbers; they are kept when
this script is run again (everything before the line "## What this shows" is regenerated).
"""
import argparse
import os
import re
import sys
from pathlib import Path

import numpy as np
import psycopg

from .cli import connection_params
from .search import keyword_search, search

REPORT = Path(__file__).resolve().parents[1] / "retrieval-diagnosis.md"
TAIL_MARKER = "## What this shows"

TOPICS = {
    "back-translation": re.compile(r"back[- ]?translation", re.I),
    "quality estimation": re.compile(r"quality[- ]estimation", re.I),
}

# Check 2 and 5 queries: (topic, label, text). The text is exactly what is encoded and sent to keyword search.
VARIANTS = [
    ("back-translation", "bare phrase", "back-translation"),
    ("back-translation", "phrase + \"for low-resource languages\" (the original wording)", "back-translation for low-resource languages"),
    ("back-translation", "phrase + \"neural machine translation\"", "back-translation neural machine translation"),
    ("quality estimation", "bare phrase", "quality estimation"),
    ("quality estimation", "phrase + \"for machine translation\" (the original wording)", "quality estimation for machine translation"),
    ("quality estimation", "phrase + \"low-resource\"", "quality estimation low-resource"),
]

# Check 3: (query, group, title rule used to count on-topic papers in the top 5)
SPREAD = [
    ("back-translation", "failing or weak", TOPICS["back-translation"]),
    ("back-translation for low-resource languages", "failing", TOPICS["back-translation"]),
    ("quality estimation for machine translation", "failing", TOPICS["quality estimation"]),
    ("adam optimizer", "working", re.compile(r"\badam\b|optimi[sz]", re.I)),
    ("zero-shot translation", "working", re.compile(r"zero[- ]shot", re.I)),
    ("unsupervised machine translation", "working", re.compile(r"unsupervised", re.I)),
]

RRF_K = 60


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" if i == 0 else "---:" for i in range(len(header))) + " |"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def normalized(matrix):
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def ranking(unit_matrix, vector):
    """Exact cosine ranking of every stored vector. Returns (order, similarities in that order, all similarities)."""
    v = np.asarray(vector, dtype=np.float64)
    v /= np.linalg.norm(v)
    sims = unit_matrix @ v
    order = np.argsort(-sims, kind="stable")
    return order, sims[order], sims


def relevance_counts(order, relevant_idx):
    position = {int(idx): rank + 1 for rank, idx in enumerate(order)}
    ranks = sorted(position[i] for i in relevant_idx)
    return ranks, [sum(1 for r in ranks if r <= n) for n in (5, 20, 100)], (ranks[0] if ranks else None)


def rrf(rank_lists, k=RRF_K):
    """Reciprocal rank fusion of lists of ids (best first). Returns ids best first. Ties go to the smaller id."""
    scores = {}
    for ids in rank_lists:
        for rank, pid in enumerate(ids, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return [pid for pid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dbname", required=True)
    parser.add_argument("--out", default=str(REPORT))
    args = parser.parse_args(argv)

    from embeddings.encoder import make_query_encoder
    encoder = make_query_encoder()  # the default: adhoc_query (PC_QUERY_ADAPTER may select proximity)
    params = connection_params(args.dbname)
    conn = psycopg.connect(**params, autocommit=True, options="-c default_transaction_read_only=on")

    before = conn.execute("SELECT (SELECT count(*) FROM paper), (SELECT count(embedding) FROM paper), "
                          "(SELECT count(*) FROM author), (SELECT count(*) FROM experiment)").fetchone()
    rows = conn.execute("SELECT paper_id, title, coalesce(abstract, ''), embedding::text FROM paper "
                        "WHERE embedding IS NOT NULL ORDER BY paper_id").fetchall()
    ids = [r[0] for r in rows]
    titles = [r[1] for r in rows]
    abstracts = [r[2] for r in rows]
    unit = normalized(np.array([[float(x) for x in r[3].strip("[]").split(",")] for r in rows]))
    n = len(ids)
    index_of = {pid: i for i, pid in enumerate(ids)}
    md = []
    w = md.append

    w("# Retrieval diagnosis on pc_pilot (generated by `db/retrieval/diagnose_uniformity.py`)")
    w("")
    w(f"Database `{args.dbname}`, opened read-only. Query encoder: `{encoder.model_string}`. {n} papers with a stored embedding "
      f"(rows before: papers {before[0]}, embeddings {before[1]}, authors {before[2]}, experiments {before[3]}). "
      "Ranks and similarities come from an exact cosine ranking over all stored vectors, not from the HNSW index. "
      "Every number below is printed by the script run that wrote this file.")
    w("")

    # ---- check 1
    relevant_strict, relevant_broad = {}, {}
    for topic, pattern in TOPICS.items():
        relevant_strict[topic] = [i for i in range(n) if pattern.search(titles[i])]
        relevant_broad[topic] = [i for i in range(n) if pattern.search(titles[i]) or pattern.search(abstracts[i])]
    w("## Check 1: how many relevant papers exist?")
    w("")
    w("Strict = the phrase is in the title. Broad = the phrase is in the title or the abstract. Patterns (case-insensitive): "
      "`back[- ]?translation` (back-translation, backtranslation, back translation) and `quality[- ]estimation`.")
    w("")
    w(table(["Topic", "Strict (title)", "Broad (title or abstract)", "Broad only"],
            [(t, len(relevant_strict[t]), len(relevant_broad[t]), len(relevant_broad[t]) - len(relevant_strict[t])) for t in TOPICS]))
    w("")
    for topic in TOPICS:
        broad_only = [i for i in relevant_broad[topic] if i not in set(relevant_strict[topic])]
        w(f"First 10 of the {len(broad_only)} broad-only papers for \"{topic}\" (ordered by paper_id), to judge by eye:")
        w("")
        for i in broad_only[:10]:
            w(f"- {ids[i]} ({titles[i][:110]})")
        w("")

    # ---- encode all query texts once
    texts = {text for _, _, text in VARIANTS} | {q for q, _, _ in SPREAD}
    vectors = {text: np.array(encoder.embed([text])[0]) for text in sorted(texts)}
    ranked = {text: ranking(unit, vectors[text]) for text in vectors}

    # consistency of the exact ranking with search() (HNSW) on the top 5
    agree = []
    for text in sorted(texts):
        top5 = [r["paper_id"] for r in search(conn, vectors[text].tolist(), top_k=5)]
        exact5 = [ids[int(i)] for i in ranked[text][0][:5]]
        agree.append((text, len(set(top5) & set(exact5)), "yes" if top5 == exact5 else "no"))

    # ---- check 2
    w("## Check 2: query variants")
    w("")
    w("For the broad-relevant papers of each topic: how many are in the top 5, 20 and 100 of the exact ranking over all papers, and the best rank.")
    w("")
    check2 = []
    for topic, label, text in VARIANTS:
        ranks, (t5, t20, t100), best = relevance_counts(ranked[text][0], relevant_broad[topic])
        check2.append((topic, label, text, len(relevant_broad[topic]), t5, t20, t100, best))
    w(table(["Topic", "Variant", "Query text", "Relevant (broad)", "In top 5", "In top 20", "In top 100", "Best rank"],
            [(a, b, f"`{c}`", d, e, f, g, h) for a, b, c, d, e, f, g, h in check2]))
    w("")
    w("Same table for the strict (title) relevant papers:")
    w("")
    check2s = []
    for topic, label, text in VARIANTS:
        ranks, (t5, t20, t100), best = relevance_counts(ranked[text][0], relevant_strict[topic])
        check2s.append((topic, label, len(relevant_strict[topic]), t5, t20, t100, best))
    w(table(["Topic", "Variant", "Relevant (strict)", "In top 5", "In top 20", "In top 100", "Best rank"], check2s))
    w("")
    w("Check that the exact ranking agrees with `search()` (HNSW, default settings) on the top 5:")
    w("")
    w(table(["Query text", "Shared ids in top 5 (of 5)", "Same order"], [(f"`{t}`", a, b) for t, a, b in agree]))
    w("")

    # ---- check 3
    w("## Check 3: score spread")
    w("")
    w("Cosine similarity at ranks 1, 5, 20 and 100 of the exact ranking, mean and standard deviation of the similarity over all "
      f"{n} papers, and the gap rank 1 minus rank 20. \"On-topic in top 5\" counts titles matching a simple rule (back-translation / quality estimation: "
      "the phrase; adam optimizer: the word adam or optimi[sz]; zero-shot translation: zero-shot; unsupervised machine translation: unsupervised). "
      "The group label (failing or working) is mine, from the earlier before/after tables in `db/pilot-report.md`.")
    w("")
    check3 = []
    for text, group, rule in SPREAD:
        order, sims_sorted, sims_all = ranked[text]
        on_topic = sum(1 for i in order[:5] if rule.search(titles[int(i)]))
        check3.append((text, group, on_topic, sims_sorted[0], sims_sorted[4], sims_sorted[19], sims_sorted[99], sims_all.mean(), sims_all.std(), sims_sorted[0] - sims_sorted[19]))
    w(table(["Query", "Group", "On-topic in top 5", "Rank 1", "Rank 5", "Rank 20", "Rank 100", "Mean (all)", "Std (all)", "Gap rank1 - rank20"],
            [(f"`{q}`", g, o, f"{a:.4f}", f"{b:.4f}", f"{c:.4f}", f"{d:.4f}", f"{m:.4f}", f"{s:.4f}", f"{gap:.4f}") for q, g, o, a, b, c, d, m, s, gap in check3]))
    w("")
    gaps = {}
    for row in check3:
        gaps.setdefault(row[1], []).append(row[9])
    stds = {}
    for row in check3:
        stds.setdefault(row[1], []).append(row[8])
    w("Mean gap rank1 - rank20 by group: " + "; ".join(f"{g}: {np.mean(v):.4f} ({len(v)} queries)" for g, v in gaps.items()) + ".")
    w("")
    w("Gap in units of the spread of that query's similarities (gap / std over all papers):")
    w("")
    w(table(["Query", "Group", "Gap / std"], [(f"`{r[0]}`", r[1], f"{r[9] / r[8]:.2f}") for r in check3]))
    w("")

    # ---- check 4
    rng = np.random.default_rng(42)
    sample = rng.choice(n, size=min(500, n), replace=False)
    sub = unit[sample]
    sim = sub @ sub.T
    pairs = sim[np.triu_indices(len(sample), k=1)]
    pct = np.percentile(pairs, [5, 50, 95])
    low = np.array([bool(re.search(r"low[- ]resource", a, re.I)) for a in abstracts])
    low_title = np.array([bool(re.search(r"low[- ]resource", t, re.I)) for t in titles])
    full = unit @ unit.T
    np.fill_diagonal(full, -1.0)
    nn = full.max(axis=1)
    w("## Check 4: corpus uniformity (stored embeddings only, no model)")
    w("")
    w(table(["Measure", "Value"], [
        ("Papers sampled (seed 42, numpy default_rng)", len(sample)),
        ("Pairwise cosine, mean", f"{pairs.mean():.4f}"),
        ("Pairwise cosine, standard deviation", f"{pairs.std():.4f}"),
        ("Pairwise cosine, 5th / 50th / 95th percentile", f"{pct[0]:.4f} / {pct[1]:.4f} / {pct[2]:.4f}"),
        ("Share of papers whose abstract contains \"low-resource\" or \"low resource\"", f"{low.mean() * 100:.1f}% ({int(low.sum())} of {n})"),
        ("Share of papers whose title contains it", f"{low_title.mean() * 100:.1f}% ({int(low_title.sum())} of {n})"),
        ("Share of vectors whose nearest neighbour (excluding itself) has cosine above 0.95", f"{(nn > 0.95).mean() * 100:.1f}% ({int((nn > 0.95).sum())} of {n})"),
        ("Nearest-neighbour cosine, 5th / 50th / 95th percentile", " / ".join(f"{v:.4f}" for v in np.percentile(nn, [5, 50, 95]))),
    ]))
    w("")
    in_low, out_low = np.where(low)[0], np.where(~low)[0]
    sample_low = rng.choice(in_low, size=min(300, len(in_low)), replace=False)
    sample_out = rng.choice(out_low, size=min(300, len(out_low)), replace=False)

    def pair_stats(idx):
        s = unit[idx] @ unit[idx].T
        p = s[np.triu_indices(len(idx), k=1)]
        return f"{p.mean():.4f}", f"{p.std():.4f}"

    cross = (unit[sample_low] @ unit[sample_out].T).ravel()
    w("Extra (not asked for): pairwise cosine inside the two groups, 300 random papers each (seed 42).")
    w("")
    w(table(["Group", "Mean", "Std"], [("abstract mentions low-resource", *pair_stats(sample_low)),
                                       ("abstract does not mention it", *pair_stats(sample_out)),
                                       ("between the two groups", f"{cross.mean():.4f}", f"{cross.std():.4f}")]))
    w("")

    # ---- check 5
    w("## Check 5: keyword baseline and a PROTOTYPE hybrid")
    w("")
    w(f"**Prototype, inside this script only; `search()` is not changed.** Keyword = the existing `keyword_search()` (PostgreSQL full text, all query words must match). Fused = reciprocal rank fusion, score = sum over the two lists of 1/({RRF_K} + rank), of the exact vector ranking (all papers) and the keyword ranking (all matching papers). Relevant = broad-relevant papers of the topic.")
    w("")
    check5 = []
    for topic, label, text in VARIANTS:
        kw = [r["paper_id"] for r in keyword_search(conn, text, top_k=n)]
        vec_ids = [ids[int(i)] for i in ranked[text][0]]
        fused = rrf([vec_ids, kw])
        rel = {ids[i] for i in relevant_broad[topic]}
        count = lambda lst, k: sum(1 for pid in lst[:k] if pid in rel)
        check5.append((topic, f"`{text}`", len(kw), count(vec_ids, 5), count(vec_ids, 20), count(kw, 5), count(kw, 20), count(fused, 5), count(fused, 20)))
    w(table(["Topic", "Query text", "Keyword matches", "Vector top 5", "Vector top 20", "Keyword top 5", "Keyword top 20", "Fused top 5", "Fused top 20"], check5))
    w("")
    w("Numbers are counts of relevant papers (broad rule) in the list's first 5 or 20 entries.")
    w("")

    after = conn.execute("SELECT (SELECT count(*) FROM paper), (SELECT count(embedding) FROM paper), "
                         "(SELECT count(*) FROM author), (SELECT count(*) FROM experiment)").fetchone()
    w(f"Rows after the run: papers {after[0]}, embeddings {after[1]}, authors {after[2]}, experiments {after[3]} (before: {before[0]}, {before[1]}, {before[2]}, {before[3]}).")
    w("")

    out = Path(args.out)
    tail = ""
    if out.exists():
        existing = out.read_text(encoding="utf-8")
        if TAIL_MARKER in existing:
            tail = existing[existing.index(TAIL_MARKER):]
    text = "\n".join(md) + "\n" + tail
    out.write_text(text, encoding="utf-8", newline="\n")
    print("\n".join(md))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
