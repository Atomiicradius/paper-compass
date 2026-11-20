"""Fetch Machine Translation papers from OpenAlex API and format as papers.jsonl.

Conforms to Person 2's loader specifications:
- db/proposals/paper-metadata-format.md
- db/loaders/papers.py
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest-openalex")

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "PaperCompass/1.0 (mailto:student@rvce.edu.in)"

VALID_VENUE_TYPES = {"conference", "journal", "workshop", "preprint", "other"}


def reconstruct_abstract(inverted_index):
    """Reconstruct plain text from OpenAlex's abstract_inverted_index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    words.sort(key=lambda x: x[0])
    text = " ".join(w[1] for w in words).strip()
    return text if text else None


def clean_id(raw_id):
    """Strip OpenAlex URI prefix to keep clean short IDs like 'W12345' or 'A12345'."""
    if not raw_id:
        return None
    return raw_id.split("/")[-1].strip()


def clean_doi(raw_doi):
    """Normalize DOI to standard 10.xxxx format or null."""
    if not raw_doi:
        return None
    raw_doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    return raw_doi if raw_doi else None


def map_venue_type(raw_type):
    """Map OpenAlex source type to valid DB enum."""
    if not raw_type:
        return "other"
    raw_type = raw_type.lower().strip()
    if raw_type in ("conference", "proceedings"):
        return "conference"
    if raw_type in ("journal", "book series"):
        return "journal"
    if raw_type in ("repository", "preprint"):
        return "preprint"
    if raw_type == "workshop":
        return "workshop"
    return "other"


def transform_work(work):
    """Transform an OpenAlex work JSON object into the target papers.jsonl schema."""
    paper_id = clean_id(work.get("id"))
    title = (work.get("title") or "").strip()
    if not paper_id or not title:
        return None

    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    year = work.get("publication_year")
    if year is not None and not (1950 <= year <= 2100):
        year = None

    doi = clean_doi(work.get("doi"))

    # Venue & Venue Type
    primary_loc = work.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    venue = (source.get("display_name") or "").strip() or None
    raw_source_type = source.get("type")
    venue_type = map_venue_type(raw_source_type) if venue else "other"

    # Authors
    authors = []
    for idx, authorship in enumerate(work.get("authorships") or [], start=1):
        author_obj = authorship.get("author") or {}
        author_name = (author_obj.get("display_name") or "").strip()
        if not author_name:
            continue
        external_id = clean_id(author_obj.get("id"))

        # Institution (first affiliation if present)
        institutions = authorship.get("institutions") or []
        inst_name = (institutions[0].get("display_name") or "").strip() if institutions else None

        authors.append({
            "name": author_name,
            "external_id": external_id,
            "institution": inst_name,
            "order": idx
        })

    # References
    raw_refs = work.get("referenced_works") or []
    references = [clean_id(ref) for ref in raw_refs if clean_id(ref)]

    return {
        "paper_id": paper_id,
        "title": title,
        "abstract": abstract,
        "year": year,
        "doi": doi,
        "venue": venue,
        "venue_type": venue_type,
        "authors": authors,
        "references": references
    }


DEFAULT_FETCH_STREAMS = [
    ("MT-TopCited", "concepts.id:C204321447,has_abstract:true", "cited_by_count:desc", 500),
    ("MT-Recent", "concepts.id:C204321447,publication_year:>2019,has_abstract:true", "cited_by_count:desc", 400),
    ("NLP-Representations", "concepts.id:C41008148,has_abstract:true", "cited_by_count:desc", 400),
    ("Speech-Processing", "concepts.id:C28490314,has_abstract:true", "cited_by_count:desc", 350),
    ("Question-Answering", "concepts.id:C199360897,has_abstract:true", "cited_by_count:desc", 350),
]


def fetch_openalex_papers(target_count=2000, output_file="ingest/data/papers_pilot.jsonl", email=None, preserve_existing=True):
    """Fetch diverse NLP/MT papers from OpenAlex using structured concept filters to avoid rate limits."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": f"PaperCompass/1.0 (mailto:{email})" if email else USER_AGENT
    }

    seen_ids = set()
    papers_list = []

    # Preserve existing papers if present
    if preserve_existing and output_path.exists():
        logger.info(f"Loading existing papers from {output_path} to preserve low-resource MT seed...")
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = json.loads(line)
                    pid = p.get("paper_id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        papers_list.append(p)
        logger.info(f"Loaded {len(papers_list)} existing papers.")

    collected = len(papers_list)
    per_page = 100

    logger.info(f"Starting multi-stream fetch from OpenAlex for target ~{target_count} papers...")

    for stream_name, filter_str, sort_str, s_target in DEFAULT_FETCH_STREAMS:
        if collected >= target_count:
            break
        s_collected = 0
        page = 1
        empty_pages = 0
        logger.info(f"Stream '{stream_name}' (target: {s_target}, sort: {sort_str})...")

        while s_collected < s_target and collected < target_count:
            params = {
                "filter": filter_str,
                "per-page": min(per_page, s_target - s_collected),
                "page": page,
                "select": "id,title,abstract_inverted_index,publication_year,doi,primary_location,authorships,referenced_works"
            }
            if sort_str:
                params["sort"] = sort_str
            if email:
                params["mailto"] = email
            url = f"{OPENALEX_WORKS_URL}?{urlencode(params)}"

            req = Request(url, headers=headers)
            try:
                with urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                logger.error(f"OpenAlex HTTP {e.code} error on page {page}: {err_body}")
                if e.code in (401, 403, 400):
                    logger.error("Stopping this stream due to client/auth error.")
                    break
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
                continue
            except URLError as e:
                logger.error(f"OpenAlex connection error: {e}. Retrying in 5 seconds...")
                time.sleep(5)
                continue

            results = data.get("results") or []
            if not results:
                logger.info(f"No more results for stream {stream_name!r}.")
                break

            page_added = 0
            for work in results:
                transformed = transform_work(work)
                if not transformed:
                    continue
                if transformed["paper_id"] in seen_ids:
                    continue
                seen_ids.add(transformed["paper_id"])
                papers_list.append(transformed)

                collected += 1
                s_collected += 1
                page_added += 1
                if s_collected >= s_target or collected >= target_count:
                    break

            if page_added == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    logger.info(f"Stream '{stream_name}' yielded no new unique papers after {page} pages; moving to next stream.")
                    break
            else:
                empty_pages = 0

            logger.info(f"  [{stream_name}] Added {s_collected}/{s_target} (total unique: {collected})...")
            page += 1
            time.sleep(0.1)

    # Write all papers
    with open(output_path, "w", encoding="utf-8") as f:
        for p in papers_list:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Compute citation metrics
    all_paper_ids = {p["paper_id"] for p in papers_list}
    total_citations = sum(len(p.get("references", [])) for p in papers_list)
    internal_citations = sum(
        sum(1 for ref in p.get("references", []) if ref in all_paper_ids)
        for p in papers_list
    )
    density = (internal_citations / total_citations * 100) if total_citations else 0.0

    logger.info("=" * 60)
    logger.info(f"FETCH COMPLETE: {collected} papers written to {output_path}")
    logger.info(f"Total citations: {total_citations}")
    logger.info(f"Internal corpus citations: {internal_citations} ({density:.2f}% density)")
    logger.info("=" * 60)

    return collected


def main():
    parser = argparse.ArgumentParser(description="Fetch papers from OpenAlex for Paper Compass.")
    parser.add_argument("--query", default=None, help="Search query (if omitted, runs balanced multi-query bundle)")
    parser.add_argument("--count", type=int, default=2000, help="Target number of papers (default: 2000)")
    parser.add_argument("--out", default="ingest/data/papers_pilot.jsonl", help="Output JSONL path")
    parser.add_argument("--email", default="student@rvce.edu.in", help="Contact email for OpenAlex polite pool")
    args = parser.parse_args()

    fetch_openalex_papers(target_count=args.count, output_file=args.out, email=args.email)


if __name__ == "__main__":
    main()
