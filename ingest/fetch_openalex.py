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


def fetch_openalex_papers(query="machine translation", target_count=500, output_file="data/papers.jsonl", email=None):
    """Fetch works from OpenAlex with cursor/page pagination until target_count is reached."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": f"PaperCompass/1.0 (mailto:{email})" if email else USER_AGENT
    }

    per_page = 100
    page = 1
    collected = 0
    seen_ids = set()

    logger.info(f"Starting fetch from OpenAlex: query={query!r}, target={target_count}")

    with open(output_path, "w", encoding="utf-8") as f:
        while collected < target_count:
            params = {
                "filter": "has_abstract:true",
                "search": query,
                "per-page": min(per_page, target_count - collected),
                "page": page,
                "select": "id,title,abstract_inverted_index,publication_year,doi,primary_location,authorships,referenced_works"
            }
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
                    logger.error("Stopping due to client/auth error.")
                    break
                logger.info("Retrying in 3 seconds...")
                time.sleep(3)
                continue
            except URLError as e:
                logger.error(f"OpenAlex connection error: {e}. Retrying in 3 seconds...")
                time.sleep(3)
                continue

            results = data.get("results") or []
            if not results:
                logger.info("No more results returned from OpenAlex.")
                break

            for work in results:
                transformed = transform_work(work)
                if not transformed:
                    continue
                if transformed["paper_id"] in seen_ids:
                    continue
                seen_ids.add(transformed["paper_id"])

                f.write(json.dumps(transformed, ensure_ascii=False) + "\n")
                collected += 1
                if collected >= target_count:
                    break

            logger.info(f"Fetched {collected}/{target_count} papers so far (page {page})...")
            page += 1
            time.sleep(0.2)  # Polite pool delay

    logger.info(f"Finished! Successfully wrote {collected} papers to {output_path}")
    return collected


def main():
    parser = argparse.ArgumentParser(description="Fetch papers from OpenAlex for Paper Compass.")
    parser.add_argument("--query", default="machine translation low-resource", help="Search query (default: 'machine translation low-resource')")
    parser.add_argument("--count", type=int, default=500, help="Target number of papers (default: 500)")
    parser.add_argument("--out", default="data/papers_pilot.jsonl", help="Output JSONL path")
    parser.add_argument("--email", default="student@rvce.edu.in", help="Contact email for OpenAlex polite pool")
    args = parser.parse_args()

    fetch_openalex_papers(query=args.query, target_count=args.count, output_file=args.out, email=args.email)


if __name__ == "__main__":
    main()
