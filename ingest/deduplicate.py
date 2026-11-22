"""Deduplication module for OpenAlex papers corpus (Items 1 & 2).

Merges duplicate records sharing the same DOI or matching title/author/abstract:
1. Shared DOI merge: keep the record with more references and fuller authorship metadata.
2. Repeated title merge: check title match, author overlap, abstract similarity, and year proximity (|y1 - y2| <= 2).
3. Citation remapping: remap all references pointing to dropped IDs to the kept ID.
4. Extractions remapping: remap paper_id in extractions from dropped ID to kept ID.
"""

import json
import re
from collections import defaultdict
from pathlib import Path


def normalize_title(title):
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    return re.sub(r"\s+", " ", t)


def get_author_tokens(authors):
    tokens = set()
    for a in authors:
        name = a.get("name", "").lower()
        words = re.findall(r"[a-z]{3,}", name)
        # ignore generic words like association, computational, linguistics, proceedings
        words = [w for w in words if w not in {"association", "computational", "linguistics", "proceedings", "conference", "meeting"}]
        tokens.update(words)
    return tokens


def get_abstract_tokens(abstract):
    if not abstract:
        return set()
    return set(re.findall(r"[a-z]{4,}", abstract.lower()))


def record_quality(p):
    """Compute score to decide which duplicate record to keep."""
    n_refs = len(p.get("references", []))
    n_inst = sum(1 for a in p.get("authors", []) if a.get("institution"))
    n_auth = len(p.get("authors", []))
    abst_len = len(p.get("abstract") or "")
    
    venue = (p.get("venue") or "").lower()
    venue_type = (p.get("venue_type") or "").lower()
    
    # Prioritize formal peer-reviewed venues over arXiv/Zenodo
    venue_score = 100
    if any(k in venue for k in ["arxiv", "zenodo", "underline", "biorxiv", "medrxiv"]):
        venue_score = 10
    elif venue_type in ["conference", "journal"]:
        venue_score = 150
        
    return (venue_score, n_refs, n_inst, abst_len, n_auth)


def run_deduplication(papers_path, extractions_path, out_papers_path, out_extractions_path, log_path=None):
    papers = [json.loads(line) for line in open(papers_path, encoding="utf-8") if line.strip()]
    print(f"Initial paper count: {len(papers)}")
    
    id_remap = {}
    merge_reasons = {}
    
    # Pass 1: Shared DOI
    by_doi = defaultdict(list)
    for p in papers:
        doi = (p.get("doi") or "").strip().lower()
        if doi:
            by_doi[doi].append(p)
            
    for doi, group in by_doi.items():
        if len(group) <= 1:
            continue
        # Sort by record quality descending
        sorted_group = sorted(group, key=record_quality, reverse=True)
        kept = sorted_group[0]
        for dropped in sorted_group[1:]:
            id_remap[dropped["paper_id"]] = kept["paper_id"]
            merge_reasons[dropped["paper_id"]] = (
                f"Shared DOI {doi}: merged into {kept['paper_id']} "
                f"({kept['title'][:40]}...) [refs: {len(kept.get('references', []))} vs {len(dropped.get('references', []))}]"
            )

    print(f"Pass 1 (Shared DOI): Identified {len(id_remap)} duplicate records to merge.")
    
    # Pass 2: Repeated titles with different DOIs
    # Group remaining papers by normalized title
    by_title = defaultdict(list)
    for p in papers:
        pid = p["paper_id"]
        # If already remapped in pass 1, resolve to kept id
        canon_id = id_remap.get(pid, pid)
        # We only consider papers that haven't been dropped
        if pid != canon_id:
            continue
        norm_t = normalize_title(p.get("title"))
        if norm_t:
            by_title[norm_t].append(p)
            
    title_merges = 0
    for norm_t, group in by_title.items():
        if len(group) <= 1:
            continue
            
        # Cluster into duplicate sub-groups based on author overlap and year proximity
        clusters = [] # list of lists of papers
        for p in group:
            matched_cluster = None
            p_auth = get_author_tokens(p.get("authors", []))
            p_abst = get_abstract_tokens(p.get("abstract"))
            p_year = p.get("year")
            
            for cluster in clusters:
                c0 = cluster[0]
                c0_auth = get_author_tokens(c0.get("authors", []))
                c0_abst = get_abstract_tokens(c0.get("abstract"))
                c0_year = c0.get("year")
                
                # Check author overlap
                auth_overlap = len(p_auth & c0_auth)
                year_diff = abs(p_year - c0_year) if (p_year and c0_year) else 0
                
                # Abstract Jaccard similarity if both have abstracts
                abst_jaccard = 1.0
                if p_abst and c0_abst:
                    abst_jaccard = len(p_abst & c0_abst) / len(p_abst | c0_abst)
                elif not p_abst and not c0_abst:
                    abst_jaccard = 1.0
                else:
                    # One has abstract, one doesn't (common for preprint vs conference metadata)
                    abst_jaccard = 0.5
                    
                # Decision rule for same paper:
                # 1. Author overlap exists (at least 1 meaningful author token in common)
                # 2. Years are close (|y1 - y2| <= 2, or up to 3 for preprint-to-journal publication lag)
                # 3. If both have abstracts, abstract Jaccard >= 0.25 (same topic/abstract)
                if auth_overlap >= 1 and year_diff <= 3 and abst_jaccard >= 0.25:
                    matched_cluster = cluster
                    break
                    
            if matched_cluster is not None:
                matched_cluster.append(p)
            else:
                clusters.append([p])
                
        # For each cluster with >1 paper, merge them
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            sorted_cluster = sorted(cluster, key=record_quality, reverse=True)
            kept = sorted_cluster[0]
            for dropped in sorted_cluster[1:]:
                id_remap[dropped["paper_id"]] = kept["paper_id"]
                title_merges += 1
                merge_reasons[dropped["paper_id"]] = (
                    f"Duplicate title ({kept['title'][:40]}...): merged {dropped['paper_id']} "
                    f"(Year: {dropped.get('year')}, Refs: {len(dropped.get('references', []))}) into {kept['paper_id']} "
                    f"(Year: {kept.get('year')}, Refs: {len(kept.get('references', []))})"
                )
                
    print(f"Pass 2 (Repeated Titles): Identified {title_merges} duplicate records to merge.")
    print(f"Total dropped duplicate IDs: {len(id_remap)}")
    
    # Transitive closure on id_remap (if A -> B and B -> C, then A -> C)
    for src in list(id_remap.keys()):
        curr = src
        while curr in id_remap:
            curr = id_remap[curr]
        id_remap[src] = curr

    # Build the de-duplicated paper collection and merge references/metadata
    papers_by_id = {p["paper_id"]: p for p in papers}
    
    # Merge dropped record attributes into kept record
    for dropped_id, kept_id in id_remap.items():
        dropped_p = papers_by_id[dropped_id]
        kept_p = papers_by_id[kept_id]
        
        # Combine references
        existing_refs = set(kept_p.get("references", []))
        for ref in dropped_p.get("references", []):
            if ref != kept_id: # avoid self-reference
                existing_refs.add(ref)
        kept_p["references"] = sorted(list(existing_refs))
        
        # If kept record has no abstract but dropped record does, borrow it
        if not kept_p.get("abstract") and dropped_p.get("abstract"):
            kept_p["abstract"] = dropped_p["abstract"]
            
        # If kept record has no DOI but dropped record does, borrow it
        if not kept_p.get("doi") and dropped_p.get("doi"):
            kept_p["doi"] = dropped_p["doi"]
            
    # Filter out dropped papers
    deduped_papers = [p for p in papers if p["paper_id"] not in id_remap]
    print(f"Final de-duplicated paper count: {len(deduped_papers)} (removed {len(id_remap)} duplicates)")
    
    # Remap citations across all papers
    remapped_ref_count = 0
    internal_edges = 0
    all_paper_ids = set(p["paper_id"] for p in deduped_papers)
    
    for p in deduped_papers:
        new_refs = []
        for ref in p.get("references", []):
            target = id_remap.get(ref, ref)
            if target == p["paper_id"]:
                continue # no self-loops
            if target != ref:
                remapped_ref_count += 1
            new_refs.append(target)
            if target in all_paper_ids:
                internal_edges += 1
        # Deduplicate references for this paper
        p["references"] = sorted(list(set(new_refs)))
        
    print(f"Total citation references remapped: {remapped_ref_count}")
    print(f"Internal citation edges in deduplicated corpus: {internal_edges}")
    
    # Save deduplicated papers
    with open(out_papers_path, "w", encoding="utf-8") as f:
        for p in deduped_papers:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Saved deduplicated papers to {out_papers_path}")
    
    # Remap extractions
    extractions = [json.loads(line) for line in open(extractions_path, encoding="utf-8") if line.strip()]
    remapped_extractions = []
    seen_extractions = set()
    remapped_ext_count = 0
    
    for e in extractions:
        old_pid = e.get("paper_id")
        new_pid = id_remap.get(old_pid, old_pid)
        if new_pid != old_pid:
            remapped_ext_count += 1
        e["paper_id"] = new_pid
        
        # Deduplicate experiment tuples
        key = (new_pid, e.get("method"), e.get("dataset"), e.get("task"), e.get("setting"))
        if key not in seen_extractions:
            seen_extractions.add(key)
            remapped_extractions.append(e)
            
    print(f"Extractions: remapped {remapped_ext_count} rows, kept {len(remapped_extractions)} unique experiment tuples.")
    with open(out_extractions_path, "w", encoding="utf-8") as f:
        for e in remapped_extractions:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Saved remapped extractions to {out_extractions_path}")
    
    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_initial_papers": len(papers),
                "total_deduped_papers": len(deduped_papers),
                "total_duplicates_merged": len(id_remap),
                "remapped_citations": remapped_ref_count,
                "merges": merge_reasons
            }, f, indent=2, ensure_ascii=False)
        print(f"Saved deduplication audit log to {log_path}")

    return len(deduped_papers), len(id_remap)


if __name__ == "__main__":
    run_deduplication(
        papers_path="ingest/data/papers_pilot.jsonl",
        extractions_path="extraction/data/extractions_pilot.jsonl",
        out_papers_path="ingest/data/papers_pilot.jsonl",
        out_extractions_path="extraction/data/extractions_pilot.jsonl",
        log_path="ingest/data/deduplication_log.json"
    )
