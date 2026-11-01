"""Fetch about 100 real abstracts from the OpenAlex API for the embedding experiment.

About 25 each from 4 clearly different topics. Keeps English papers published 2015 or later with
an abstract of at least 50 words. No email or API key is used. If OpenAlex rejects a request or
rate-limits us, this script prints the exact response and stops.

Usage (from db/experiments/embeddings/):  .venv\\Scripts\\python.exe fetch_abstracts.py
"""
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "abstracts.jsonl"
API = "https://api.openalex.org/works"
PER_TOPIC = 25
MIN_WORDS = 50
TOPICS = {
    "machine translation": "machine translation",
    "image segmentation": "image segmentation",
    "protein structure prediction": "protein structure prediction",
    "reinforcement learning": "reinforcement learning",
}
HEADERS = {"User-Agent": "paper-compass-embedding-experiment"}  # no email on purpose
PAUSE_SECONDS = 1.5


def rebuild_abstract(inverted_index):
    """OpenAlex stores abstracts as {word: [positions]}. Put the words back in order."""
    words = {}
    for word, positions in inverted_index.items():
        for position in positions:
            words[position] = word
    return " ".join(words[i] for i in sorted(words))


def fetch_page(search_phrase, page):
    params = {
        "filter": f"title_and_abstract.search:{search_phrase},language:en,"
                  "from_publication_date:2015-01-01,has_abstract:true,type:article",
        "per-page": 100,
        "page": page,
        "select": "id,title,abstract_inverted_index,publication_year,language",
    }
    response = requests.get(API, params=params, headers=HEADERS, timeout=60)
    if response.status_code != 200:
        print(f"OpenAlex returned HTTP {response.status_code} for {response.url}")
        for header in ("Retry-After", "X-RateLimit-Remaining", "X-RateLimit-Limit"):
            if header in response.headers:
                print(f"{header}: {response.headers[header]}")
        print("Body:", response.text[:1000])
        sys.exit(1)
    return response.json()


def collect(label, search_phrase, taken_ids):
    papers = []
    page = 1
    while len(papers) < PER_TOPIC and page <= 3:
        data = fetch_page(search_phrase, page)
        time.sleep(PAUSE_SECONDS)
        for work in data.get("results", []):
            index = work.get("abstract_inverted_index")
            if not index or not work.get("title") or work.get("language") != "en":
                continue
            abstract = rebuild_abstract(index)
            if len(abstract.split()) < MIN_WORDS or (work.get("publication_year") or 0) < 2015:
                continue
            openalex_id = work["id"].rsplit("/", 1)[-1]
            if openalex_id in taken_ids:
                continue  # a paper that matched two topics would blur the sanity check
            taken_ids.add(openalex_id)
            papers.append({
                "openalex_id": openalex_id,
                "title": " ".join(work["title"].split()),
                "abstract": abstract,
                "year": work["publication_year"],
                "topic_label": label,
            })
            if len(papers) == PER_TOPIC:
                break
        page += 1
    return papers


def show_check(rows):
    print("\n=== DATA CHECK ===")
    print(f"total papers: {len(rows)}")
    years = [r["year"] for r in rows]
    lengths = [len(r["abstract"].split()) for r in rows]
    print(f"year range: {min(years)} to {max(years)}")
    print(f"abstract length (words): min {min(lengths)}, max {max(lengths)}, "
          f"mean {sum(lengths) / len(lengths):.0f}")
    for label in TOPICS:
        topic_rows = [r for r in rows if r["topic_label"] == label]
        flag = "   <-- FEWER THAN 15 USABLE PAPERS" if len(topic_rows) < 15 else ""
        print(f"\n{label}: {len(topic_rows)} papers{flag}")
        if topic_rows:
            t_years = [r["year"] for r in topic_rows]
            t_len = [len(r["abstract"].split()) for r in topic_rows]
            print(f"  years {min(t_years)}-{max(t_years)}, abstract words {min(t_len)}-{max(t_len)}")
        for r in topic_rows[:3]:
            print(f"  - ({r['year']}) {r['title'][:110]}")


def main():
    taken_ids, rows = set(), []
    for label, phrase in TOPICS.items():
        found = collect(label, phrase, taken_ids)
        print(f"{label}: kept {len(found)} papers")
        rows.extend(found)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"saved {len(rows)} papers to {OUT}")
    show_check(rows)


if __name__ == "__main__":
    main()
