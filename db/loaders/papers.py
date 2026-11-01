"""load-papers: paper metadata with venues, institutions, authors and citations."""
from .common import REJECT_DIR, Summary, clean, normalize, read_jsonl, reject

VENUE_TYPES = ("conference", "journal", "workshop", "preprint", "other")


def check_paper(row):
    """Return a reason string if the paper line is invalid, else None."""
    for field in ("paper_id", "title"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            return f"{field} must be a non-empty string"
    year = row.get("year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1950 <= year <= 2100):
        return f"year must be an integer from 1950 to 2100, got {year!r}"
    for field in ("abstract", "doi", "venue"):
        if row.get(field) is not None and not isinstance(row[field], str):
            return f"{field} must be a string or null"
    if row.get("venue_type") is not None and row["venue_type"] not in VENUE_TYPES:
        return f"venue_type must be one of {', '.join(VENUE_TYPES)}, got {row['venue_type']!r}"
    authors = row.get("authors", [])
    if not isinstance(authors, list):
        return "authors must be a list"
    for a in authors:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str) or not a["name"].strip():
            return "every author needs a non-empty name"
        if isinstance(a.get("order"), bool) or not isinstance(a.get("order"), int):
            return f"author {a['name']!r} needs an integer order"
        for field in ("external_id", "institution"):
            if a.get(field) is not None and not isinstance(a[field], str):
                return f"author {a['name']!r}: {field} must be a string or null"
    refs = row.get("references", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) and r.strip() for r in refs):
        return "references must be a list of paper_id strings"
    return None


class AuthorBook:
    """Looks authors up before inserting so the same person is never inserted twice.
    Authors with an external_id are matched by it; authors without one by normalized name."""

    def __init__(self, conn, summary):
        self.conn, self.summary = conn, summary
        self.institutions = {n: i for i, n in conn.execute("SELECT institution_id, name FROM institution")}
        self.institution_names = {i: n for n, i in self.institutions.items()}
        self.by_external, self.by_name = {}, {}
        for author_id, name, external_id, inst_id in conn.execute(
                "SELECT author_id, name, external_id, institution_id FROM author"):
            if external_id:
                self.by_external[external_id] = (author_id, inst_id)
            else:
                self.by_name[normalize(name)] = (author_id, inst_id)

    def institution_id(self, name):
        if name not in self.institutions:
            inst_id = self.conn.execute(
                "INSERT INTO institution (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                "RETURNING institution_id", (name,)).fetchone()[0]
            self.institutions[name] = inst_id
            self.institution_names[inst_id] = name
            self.summary.add("institutions_inserted")
        return self.institutions[name]

    def resolve(self, author, paper_id):
        name = clean(author["name"])
        external_id = clean(author["external_id"]) if author.get("external_id") else None
        institution = clean(author["institution"]) if author.get("institution") else None

        found = self.by_external.get(external_id) if external_id else self.by_name.get(normalize(name))
        if found:
            author_id, stored_inst = found
            stored = self.institution_names.get(stored_inst)
            if institution and (stored is None or normalize(stored) != normalize(institution)):
                who = external_id or name
                self.summary.warn(
                    f"author {name!r} ({who}) in {paper_id}: institution {institution!r} differs from the stored "
                    f"{stored!r}; keeping the first value")
            return author_id

        inst_id = self.institution_id(institution) if institution else None
        author_id = self.conn.execute(
            "INSERT INTO author (name, external_id, institution_id) VALUES (%s, %s, %s) RETURNING author_id",
            (name, external_id, inst_id)).fetchone()[0]
        (self.by_external if external_id else self.by_name)[external_id or normalize(name)] = (author_id, inst_id)
        self.summary.add("authors_inserted")
        return author_id


def venue_id(conn, name, venue_type, cache, summary):
    key = (name, venue_type)
    if key not in cache:
        row = conn.execute("INSERT INTO venue (name, type) VALUES (%s, %s) ON CONFLICT (name, type) DO NOTHING "
                           "RETURNING venue_id", key).fetchone()
        if row:
            summary.add("venues_inserted")
        else:
            row = conn.execute("SELECT venue_id FROM venue WHERE name = %s AND type = %s", key).fetchone()
        cache[key] = row[0]
    return cache[key]


def insert_citations(conn, pairs, summary):
    """Insert (citing, cited) pairs whose papers both exist. Others are skipped, never stubbed."""
    cited_ids = sorted({cited for _, cited in pairs})
    present = {r[0] for r in conn.execute("SELECT paper_id FROM paper WHERE paper_id = ANY(%s)", (cited_ids,))}
    missing = set()
    summary.details.setdefault("citations_inserted", 0)
    summary.details.setdefault("citations_already_present", 0)
    summary.details.setdefault("citations_skipped_not_in_corpus", 0)
    for citing, cited in sorted(pairs):
        if citing == cited:
            summary.warn(f"{citing} cites itself; skipped")
        elif cited not in present:
            summary.add("citations_skipped_not_in_corpus")
            missing.add(cited)
        else:
            cur = conn.execute("INSERT INTO citation (citing_paper_id, cited_paper_id) VALUES (%s, %s) "
                               "ON CONFLICT DO NOTHING", (citing, cited))
            summary.add("citations_inserted" if cur.rowcount else "citations_already_present")
    summary.details["cited_ids_not_in_corpus"] = sorted(missing)


def load_papers(conn, path, reject_dir=REJECT_DIR):
    summary = Summary("load-papers", str(path))
    rows, rejects = read_jsonl(path)
    summary.read = len(rows) + len(rejects)
    for key in ("venues_inserted", "institutions_inserted", "authors_inserted", "author_links_inserted"):
        summary.details[key] = 0

    with conn.transaction():
        book = AuthorBook(conn, summary)
        venues, citation_pairs = {}, set()
        for number, row in rows:
            reason = check_paper(row)
            if reason:
                rejects.append(reject(number, reason, row))
                continue
            paper_id = row["paper_id"].strip()
            doi = row["doi"].strip() if row.get("doi") else None

            if doi:
                owner = conn.execute("SELECT paper_id FROM paper WHERE doi = %s", (doi,)).fetchone()
                if owner and owner[0] != paper_id:
                    rejects.append(reject(number, f"doi {doi!r} already belongs to paper {owner[0]}", row))
                    continue

            venue = clean(row["venue"]) if row.get("venue") else None
            v_id = venue_id(conn, venue, row.get("venue_type") or "other", venues, summary) if venue else None
            cur = conn.execute(
                "INSERT INTO paper (paper_id, title, abstract, year, doi, venue_id) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (paper_id) DO NOTHING",
                (paper_id, row["title"].strip(), row.get("abstract"), row.get("year"), doi, v_id))
            if cur.rowcount:
                summary.inserted += 1
            else:
                summary.skipped += 1

            seen_authors = set()
            for author in sorted(row.get("authors", []), key=lambda a: a["order"]):
                author_id = book.resolve(author, paper_id)
                if author_id in seen_authors:
                    summary.warn(f"{paper_id}: author {clean(author['name'])!r} appears twice (possible merged "
                                 "homonyms); second entry ignored")
                    continue
                seen_authors.add(author_id)
                cur = conn.execute(
                    "INSERT INTO paper_author (paper_id, author_id, author_order) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING", (paper_id, author_id, author["order"]))
                summary.add("author_links_inserted", cur.rowcount)

            citation_pairs.update((paper_id, r.strip()) for r in row.get("references", []))

        # Citations go last so a paper can cite one that appears later in the same file.
        insert_citations(conn, citation_pairs, summary)

    return summary.finish(rejects, "papers", reject_dir)
