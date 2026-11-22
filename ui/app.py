"""paper-compass UI (Streamlit). Six screens from project-plan-v2 section 14.1, all served by the FastAPI backend.

    streamlit run ui/app.py            # API at PC_API_URL (default http://127.0.0.1:8000)

Every screen shows the corpus size, date range, extraction method and the statement that
results are candidates for human review (plan section 14.1).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run with `streamlit run ui/app.py` from the repo root

import pandas as pd
import streamlit as st

from ui.client import ApiError, Client
from ui.ids import normalize_paper_id, paper_id_from_node
from ui.rerank import rerank

SIGNALS = ("sparsity", "semantic_compatibility", "temporal_activity")
SIGNAL_LABELS = {"sparsity": "Sparsity", "semantic_compatibility": "Semantic compatibility",
                 "temporal_activity": "Temporal activity"}
V1 = {"sparsity": 0.40, "semantic_compatibility": 0.35, "temporal_activity": 0.25}
EXTRACTION_NOTE = "Elements extracted from abstracts by rules-v1 (confidence cutoff 0.70)"
LABEL_COLORS = {"Paper": "#4C78A8", "Author": "#F58518", "Method": "#54A24B", "Task": "#B279A2",
                "Dataset": "#E45756", "Venue": "#9D755D", "Setting": "#72B7B2", "Topic": "#EECA3B",
                "Institution": "#BAB0AC", "Experiment": "#D3D3D3"}

st.set_page_config(page_title="paper-compass", layout="wide")


@st.cache_resource
def client() -> Client:
    return Client()


@st.cache_data(ttl=300, show_spinner=False)
def cached(method: str, *args, **kw):
    return getattr(client(), method)(*args, **kw)


def call(method: str, *args, **kw):
    """API call with a visible error instead of a stack trace. Returns None on error."""
    try:
        return cached(method, *args, **kw)
    except ApiError as e:
        if e.status == 0:
            st.error(f"{e.detail}. Start it with `uvicorn api.main:app` (see ui/README.md).")
        elif e.status == -1:
            st.warning(e.detail)
        else:
            st.error(f"API error {e.status}: {e.detail}")
        return None


def title_of(paper_id: str) -> str:
    try:
        p = cached("paper", paper_id)
        return f"{p['title']} ({p.get('year') or 'n.d.'})"
    except ApiError:
        return paper_id


def banner() -> None:
    land = call("landscape")
    if land is None:
        return
    years = sorted(int(y) for y in land["papers_per_year"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Papers in the analyzed corpus", f"{land['corpus']['papers']:,}")
    c2.metric("Publication years", f"{years[0]}–{years[-1]}" if years else "n/a")
    c3.metric("Corpus cutoff year", land["corpus"]["cutoff_year"])
    st.caption(f"{EXTRACTION_NOTE}. {land['disclaimer']}")


def open_paper(paper_id: str) -> None:
    st.session_state["paper_id"] = paper_id
    st.switch_page(PAGES["paper"])


def open_opportunity(opportunity_id: int) -> None:
    st.session_state["opportunity_id"] = int(opportunity_id)
    st.switch_page(PAGES["detail"])


def paper_buttons(ids: list[str], key: str, limit: int = 10) -> None:
    for pid in ids[:limit]:
        if st.button(title_of(pid), key=f"{key}-{pid}", type="tertiary"):
            open_paper(pid)
    if len(ids) > limit:
        st.caption(f"... and {len(ids) - limit} more")


# --- 1. Search ------------------------------------------------------------------

def page_search() -> None:
    st.title("Search")
    banner()
    with st.form("search"):
        query = st.text_input("Research idea", st.session_state.get("query", "back-translation for low-resource languages"))
        c1, c2, c3, c4 = st.columns(4)
        top_k = c1.number_input("Results", 1, 100, 10)
        mode = c2.selectbox("Mode", ["auto", "vector", "keyword"],
                            help="auto: SPECTER2 vector search when the query encoder is available, else keyword search")
        year_min = c3.number_input("From year", 1900, 2100, value=None, placeholder="any")
        year_max = c4.number_input("To year", 1900, 2100, value=None, placeholder="any")
        collapse = st.checkbox("Hide duplicate records of the same title", value=True,
                               help="The pilot corpus has duplicate OpenAlex records for some papers; this shows one per title")
        submitted = st.form_submit_button("Search", type="primary")
    if submitted:
        st.session_state["query"] = query
        st.session_state["collapse"] = collapse
    if not st.session_state.get("query"):
        return
    with st.spinner("Searching (the first vector search loads the SPECTER2 model)..."):
        res = call("search", st.session_state["query"], top_k=int(top_k), mode=mode,
                   collapse_same_title=st.session_state.get("collapse", True),
                   year_min=int(year_min) if year_min else None, year_max=int(year_max) if year_max else None)
    if not res:
        return
    model = res.get("model") or ""
    st.caption(f"Mode used: **{res['mode']}** · score = {res['score_type']}"
               + (f" · model {model.split('@')[0]} + adapter" if model else "")
               + (f" · {res['note']}" if res.get("note") else ""))
    if not res["results"]:
        st.info("No papers matched.")
    for h in res["results"]:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{h['title']}**  \n{h.get('year') or 'n.d.'} · {h.get('venue') or 'venue unknown'}")
            c2.markdown(f"score  \n**{h['score']:.3f}**")
            elems = [f"`{m}`" for m in h["methods"]] + [f"_{t}_" for t in h["tasks"]] + [f"**{d}**" for d in h["datasets"]]
            if elems:
                c1.markdown("Methods / _tasks_ / **datasets**: " + " ".join(elems))
            if c1.button("Open paper", key=f"s-{h['paper_id']}"):
                open_paper(h["paper_id"])


# --- 2. Paper Explorer -------------------------------------------------------------

def page_paper() -> None:
    st.title("Paper Explorer")
    banner()
    pid = normalize_paper_id(st.text_input("Paper ID (OpenAlex)", st.session_state.get("paper_id", "")))
    if not pid:
        st.info("Open a paper from Search, or enter an OpenAlex ID such as W3028876793.")
        return
    st.session_state["paper_id"] = pid
    p = call("paper", pid)
    if not p:
        return
    st.header(p["title"])
    st.write(f"{p.get('year') or 'n.d.'} · {p.get('venue') or 'venue unknown'}"
             + (f" · DOI [{p['doi']}](https://doi.org/{p['doi']})" if p.get("doi") else ""))
    st.write("**Authors:** " + (", ".join(p["authors"]) or "none recorded"))
    c1, c2, c3, c4 = st.columns(4)
    c1.write("**Methods**\n\n" + ("\n".join(f"- {m}" for m in p["methods"]) or "none extracted"))
    c2.write("**Tasks**\n\n" + ("\n".join(f"- {m}" for m in p["tasks"]) or "none extracted"))
    c3.write("**Datasets**\n\n" + ("\n".join(f"- {m}" for m in p["datasets"]) or "none extracted"))
    c4.write("**Topics**\n\n" + ("\n".join(f"- {m}" for m in p["topics"]) or "none recorded"))
    if p.get("abstract"):
        with st.expander("Abstract", expanded=True):
            st.write(p["abstract"])
    if st.button("Show in Research Graph"):
        st.switch_page(PAGES["graph"])
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader(f"Cites ({len(p['cites'])} in corpus)")
        paper_buttons(p["cites"], "cites")
    with c2:
        st.subheader(f"Cited by ({len(p['cited_by'])} in corpus)")
        paper_buttons(p["cited_by"], "citedby")
    with c3:
        st.subheader("Related (embedding)")
        rel = call("related", pid, 8)
        if rel:
            for h in rel["results"]:
                if st.button(f"{h['title']} ({h.get('year') or 'n.d.'}) · {h['score']:.3f}", key=f"rel-{h['paper_id']}",
                             type="tertiary"):
                    open_paper(h["paper_id"])


# --- 3. Research Graph ---------------------------------------------------------------

def _dot_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def graph_dot(g: dict, max_label: int = 40) -> str:
    lines = ["digraph G {", "rankdir=LR; bgcolor=transparent;",
             'node [style=filled, fontname="Helvetica", fontsize=10, shape=box, color="#00000020"];',
             'edge [fontname="Helvetica", fontsize=8, color="#888888"];']
    for n in g["nodes"]:
        name = n.get("name") or n["id"]
        if len(name) > max_label:
            name = name[: max_label - 1] + "…"
        label = f"{n['label']}\\n{_dot_escape(name)}" + (f" ({n['year']})" if n.get("year") else "")
        pen = ', penwidth=3, color="#000000"' if n["id"] == g["center"] else ""
        lines.append(f'"{_dot_escape(n["id"])}" [label="{label}", fillcolor="{LABEL_COLORS.get(n["label"], "#DDDDDD")}"{pen}];')
    for e in g["edges"]:
        lines.append(f'"{_dot_escape(e["source"])}" -> "{_dot_escape(e["target"])}" [label="{e["type"]}"];')
    lines.append("}")
    return "\n".join(lines)


def page_graph() -> None:
    st.title("Research Graph")
    banner()
    c1, c2 = st.columns([3, 1])
    pid = normalize_paper_id(c1.text_input("Center paper ID", st.session_state.get("paper_id", "")))
    limit = c2.slider("Max nodes", 10, 200, 60)
    if not pid:
        st.info("Open a paper first, or enter an OpenAlex ID.")
        return
    st.session_state["paper_id"] = pid
    g = call("paper_graph", pid, limit)
    if not g:
        return
    labels = sorted({n["label"] for n in g["nodes"]})
    shown = st.multiselect("Node types", labels, default=labels)
    keep = {n["id"] for n in g["nodes"] if n["label"] in shown or n["id"] == g["center"]}
    g = {"center": g["center"], "nodes": [n for n in g["nodes"] if n["id"] in keep],
         "edges": [e for e in g["edges"] if e["source"] in keep and e["target"] in keep]}
    st.caption(f"{len(g['nodes'])} nodes, {len(g['edges'])} edges, from the Neo4j projection of PostgreSQL. "
               + " ".join(f":{l}" for l in shown))
    st.graphviz_chart(graph_dot(g), use_container_width=True)
    papers = [n for n in g["nodes"] if n["label"] == "Paper" and n["id"] != g["center"]]
    if papers:
        by_id = {paper_id_from_node(n): n for n in papers}          # plain OpenAlex ids, not "Paper:W..." node ids
        choice = st.selectbox("Re-center on a neighbouring paper", [""] + list(by_id),
                              format_func=lambda i: "" if not i else f"{by_id[i].get('name') or i} ({by_id[i].get('year')})")
        if choice:
            st.session_state["paper_id"] = choice
            st.rerun()


# --- 4. Landscape --------------------------------------------------------------------

def page_landscape() -> None:
    st.title("Landscape")
    banner()
    land = call("landscape")
    if not land:
        return
    ppy = pd.DataFrame({"year": [str(y) for y in land["papers_per_year"]], "papers": list(land["papers_per_year"].values())})
    st.subheader("Papers per year")
    st.bar_chart(ppy.set_index("year"))

    cl = call("clusters")
    if cl:
        st.subheader(f"Clusters ({len(cl['clusters'])}, {cl['n_noise']} of {cl['n_papers']} papers in no cluster)")
        st.caption(f"HDBSCAN on SPECTER2 embeddings (PCA {cl.get('pca_dims') or 'none'}, min cluster size "
                   f"{cl['min_cluster_size']}, min samples {cl.get('min_samples')}). Clusters are named by their most "
                   "frequent extracted elements, or by sample titles when none were extracted.")
        rows = []
        for c in cl["clusters"]:
            elems = ", ".join(f"{e['name']} ({e['n_papers']})" for e in c["top_elements"][:4])
            rows.append({"cluster": c["cluster_id"], "papers": c["size"], "years": f"{c['year_min']}–{c['year_max']}",
                         "most frequent elements": elems or "none extracted",
                         "sample titles": " | ".join(title_of(p) for p in c["paper_ids"][:2]) if not elems else ""})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.subheader("Temporal evolution")
    etype = st.radio("Element type", ["method", "task", "dataset"], horizontal=True)
    min_total = st.slider("Hide elements with fewer papers than", 1, 30, 5,
                          help="Growth labels from very few papers are noisy")
    tr = call("trends", etype)
    if tr:
        tr = [t for t in tr if t["total"] >= min_total]
        c1, c2 = st.columns(2)
        for col, lab in ((c1, "emerging"), (c2, "declining")):
            items = [t for t in tr if t["label"] == lab]
            col.markdown(f"**{lab.capitalize()}** ({len(items)})")
            col.dataframe(pd.DataFrame([{"name": t["name"], "papers": t["total"], "recent share": round(t["recent_share"], 2),
                                         "growth": round(t["growth"], 2)} for t in items]),
                          hide_index=True, use_container_width=True)
        pick = st.multiselect("Plot yearly papers", [t["name"] for t in tr],
                              default=[t["name"] for t in sorted(tr, key=lambda t: -t["total"])[:4]])
        if pick:
            df = pd.DataFrame({t["name"]: {int(y): n for y, n in t["yearly"].items()} for t in tr if t["name"] in pick})
            df = df.sort_index().fillna(0)
            df = df[df.index >= 2000]
            df.index = df.index.astype(str)          # plain year labels (no thousands separator)
            st.line_chart(df)

    st.subheader("Bridge papers")
    st.caption("Papers whose citation links reach several clusters. Many are foundational papers that HDBSCAN left in no cluster.")
    for b in land["bridge_papers"][:10]:
        c1, c2 = st.columns([5, 2])
        if c1.button(title_of(b["paper_id"]), key=f"bridge-{b['paper_id']}", type="tertiary"):
            open_paper(b["paper_id"])
        own = "no cluster" if b["own_cluster"] == -1 else f"cluster {b['own_cluster']}"
        c2.write(f"{own} → clusters {', '.join(map(str, b['linked_clusters']))}")
    if land["weakly_connected_cluster_pairs"]:
        st.subheader("Weakly connected cluster pairs")
        st.dataframe(pd.DataFrame(land["weakly_connected_cluster_pairs"]), hide_index=True)


# --- 5. Opportunity Dashboard -----------------------------------------------------------

def page_dashboard() -> None:
    st.title("Opportunity Dashboard")
    banner()
    st.info("Each row is a **candidate research opportunity**: a research-element combination that is weakly "
            "represented in the analyzed corpus and potentially underexplored. It is a signal for human review, "
            "not proof of a research gap.")
    min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05,
                         help="confidence = min(1, expected / 5): a low observed count means little when few papers were expected")
    data = call("opportunities", 200, 0, min_conf or None)
    if not data:
        return
    items = data["items"]
    if not items:
        if min_conf:
            st.warning(f"No stored opportunity has confidence of at least {min_conf:.2f}. Lower the minimum confidence.")
        else:
            st.warning("No opportunities stored yet. Run `python -m scoring.pipeline` (see scoring/README.md).")
        return
    with st.expander("What-if weights (view only; the stored score is not changed)"):
        cols = st.columns(3)
        w = {s: cols[i].slider(SIGNAL_LABELS[s], 0.0, 1.0, V1[s], 0.05, key=f"w-{s}") for i, s in enumerate(SIGNALS)}
    try:
        ranked = rerank(items, w)
    except ValueError as e:
        st.warning(f"{e}; showing the stored ranking.")
        ranked = rerank(items, V1)
    rows = []
    for o in ranked:
        e = o["elements"]
        rows.append({"id": o["opportunity_id"], "rank": o["custom_rank"],
                     "combination": " × ".join(v for v in (e.get("method"), e.get("dataset"), e.get("task"), e.get("setting")) if v),
                     "observed": o["observed_count"], "expected": round(o["expected_count"], 2),
                     **{SIGNAL_LABELS[s]: o["signals"][s] for s in SIGNALS},
                     "confidence": o["confidence"], "score": round(o["custom_score"], 1),
                     "stored score": round(o["score"], 1)})
    df = pd.DataFrame(rows)
    pct = {SIGNAL_LABELS[s]: st.column_config.ProgressColumn(SIGNAL_LABELS[s], min_value=0, max_value=1, format="%.2f")
           for s in SIGNALS}
    event = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                         column_config={**pct, "confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=1, format="%.2f"),
                                        "score": st.column_config.NumberColumn("score (what-if)")})
    st.caption(f"{data['total']} stored · weights {items[0]['weights_version']} "
               f"(stored) · corpus cutoff {items[0]['corpus']['cutoff_year']}. Select a row to open its evidence.")
    if event.selection.rows:
        open_opportunity(df.iloc[event.selection.rows[0]]["id"])


# --- 6. Opportunity Detail ---------------------------------------------------------------

def evidence_list(items: list[dict], key: str, show_tier: bool = False) -> None:
    if not items:
        st.caption("none in the analyzed corpus")
    for it in items:
        extra = ""
        if show_tier:
            extra = f" · {it.get('tier')}" + (f", similarity {it['similarity']:.3f}" if it.get("similarity") is not None else "") \
                    + (f", uses {it['uses']}" if it.get("uses") else "")
        if st.button(f"{it['title']} ({it.get('year') or 'n.d.'}){extra}", key=f"{key}-{it['paper_id']}", type="tertiary"):
            open_paper(it["paper_id"])
        if it.get("source_sentence"):
            st.caption(f"“{it['source_sentence'][:300]}”  ({it.get('extractor', '')})")


def page_detail() -> None:
    st.title("Opportunity Detail")
    banner()
    opps = call("opportunities", 200)
    if not opps or not opps["items"]:
        st.warning("No opportunities stored yet.")
        return
    ids = [o["opportunity_id"] for o in opps["items"]]
    label = {o["opportunity_id"]: " × ".join(v for v in o["elements"].values() if v) for o in opps["items"]}
    cur = st.session_state.get("opportunity_id", ids[0])
    oid = st.selectbox("Opportunity", ids, index=ids.index(cur) if cur in ids else 0, format_func=lambda i: f"#{i} {label[i]}")
    st.session_state["opportunity_id"] = oid
    o = call("opportunity", oid)
    ex = call("explain", oid)
    if not o:
        return
    st.header(label[oid])
    st.caption("Potentially underexplored research-element combination: a candidate for human review, not proof of a research gap.")
    c = st.columns(5)
    c[0].metric("Score", f"{o['score']:.1f}", help=f"weights {o['weights_version']}")
    c[1].metric("Observed papers", o["observed_count"])
    c[2].metric("Expected papers", f"{o['expected_count']:.2f}", help="n_A × n_B / N over papers where both kinds of element were extracted")
    c[3].metric("Confidence", f"{o['confidence']:.2f}")
    if ex:
        c[4].metric("Universe (N)", ex["evidence"]["corpus"]["universe_size"],
                    help="papers up to the cutoff in which both kinds of element were extracted")
    st.subheader("Signals")
    sig = pd.DataFrame({"signal": [SIGNAL_LABELS.get(k, k) for k in o["signals"]],
                        "value": [v for v in o["signals"].values()]})
    sig["value"] = sig["value"].apply(lambda v: "not implemented" if v is None else round(v, 3))
    st.dataframe(sig, hide_index=True)
    if not ex:
        return
    tab_why, tab_ev, tab_years, tab_chat = st.tabs(["Why? (explanation)", "Evidence chain", "Papers per year", "Ask (RAG)"])
    with tab_why:
        st.markdown(ex["summary"])
        cc = ex["citation_check"]
        st.caption(f"Summary source: {ex['summary_source']}"
                   + (f" (fallback: {ex['summary_fallback_reason']})" if ex.get("summary_fallback_reason") else "")
                   + f" · citation check: {'passed' if cc['ok'] else 'FAILED'}, {len(cc['cited'])} papers cited, "
                     f"{len(cc['unknown'])} unknown")
        with st.expander("Limitations"):
            for lim in ex["evidence"]["limitations"]:
                st.write(f"- {lim}")
    with tab_ev:
        roles = ex["evidence"]["roles"]
        a, b = ex["evidence"]["pair"]["a"], ex["evidence"]["pair"]["b"]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Supports A: uses {a['name']}** ({a['kind']})")
            evidence_list(roles["supports_A"], "sa")
            st.markdown("**Bridge papers** (citations between the two groups)")
            evidence_list(roles["bridge"], "br")
        with c2:
            st.markdown(f"**Supports B: uses {b['name']}** ({b['kind']})")
            evidence_list(roles["supports_B"], "sb")
            st.markdown("**Nearest existing work** (check these before treating the combination as new)")
            evidence_list(roles["nearest_existing"], "ne", show_tier=True)
    with tab_years:
        a, b = ex["evidence"]["pair"]["a"]["name"], ex["evidence"]["pair"]["b"]["name"]
        df = pd.DataFrame(ex["evidence"]["yearly"]).set_index("year").rename(columns={"a": a, "b": b, "both": "both"})
        df = df[df.index >= 2000]
        df.index = df.index.astype(str)
        st.line_chart(df)
    with tab_chat:
        q = st.text_input("Question about this opportunity")
        if q:
            try:
                st.write(client().rag_query(q))
            except ApiError as e:
                st.info(f"RAG chat is not available yet ({e.status}): {e.detail}. The explanation tab uses the "
                        "evidence-grounded template summary.")


PAGES = {
    "search": st.Page(page_search, title="Search", icon=":material/search:", url_path="search", default=True),
    "paper": st.Page(page_paper, title="Paper Explorer", icon=":material/article:", url_path="paper"),
    "graph": st.Page(page_graph, title="Research Graph", icon=":material/hub:", url_path="graph"),
    "landscape": st.Page(page_landscape, title="Landscape", icon=":material/insights:", url_path="landscape"),
    "dashboard": st.Page(page_dashboard, title="Opportunity Dashboard", icon=":material/leaderboard:", url_path="opportunities"),
    "detail": st.Page(page_detail, title="Opportunity Detail", icon=":material/fact_check:", url_path="opportunity"),
}

st.navigation(list(PAGES.values())).run()
