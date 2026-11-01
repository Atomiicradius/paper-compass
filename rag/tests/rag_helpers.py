"""Test helpers: a small builder for synthetic corpora, and brute-force Python versions of the rag
computations, used to check the SQL independently. Everything here is synthetic test data."""
import math
import random

DIM = 768
COL = {"method": 0, "dataset": 1, "task": 2}      # position inside an experiment tuple (method, dataset, task)
TABLE = {"method": "method", "dataset": "dataset", "task": "task"}


def make_vector(seed):
    rng = random.Random(seed)
    return [round(rng.gauss(0, 1), 6) for _ in range(DIM)]


def literal(vector):
    return "[" + ",".join(repr(x) for x in vector) + "]"


class World:
    """Inserts synthetic papers, experiments and citations, and remembers them for brute-force checks."""

    def __init__(self, conn):
        self.conn = conn
        self.ids = {}           # (kind, name) -> id
        self.papers = {}        # paper_id -> dict(year, experiments=[(m_id, d_id, t_id)], vec, title, venue)
        self.citations = []     # (citing, cited)
        self._venues = {}

    def element(self, kind, name):
        if (kind, name) not in self.ids:
            self.ids[(kind, name)] = self.conn.execute(
                f"INSERT INTO {TABLE[kind]} (canonical_name) VALUES (%s) RETURNING {kind}_id", (name,)).fetchone()[0]
        return self.ids[(kind, name)]

    def eid(self, kind, name):
        return self.ids[(kind, name)]

    def _venue_id(self, name):
        if name is None:
            return None
        if name not in self._venues:
            self._venues[name] = self.conn.execute(
                "INSERT INTO venue (name, type) VALUES (%s, 'other') RETURNING venue_id", (name,)).fetchone()[0]
        return self._venues[name]

    def paper(self, paper_id, year, experiments, embedded=True, venue=None):
        """experiments: list of (method, dataset, task) names, or (method, dataset, task, source_sentence,
        extractor). dataset and task may be None."""
        vec = make_vector(paper_id) if embedded else None
        title = f"Title {paper_id}"
        self.conn.execute(
            "INSERT INTO paper (paper_id, title, year, venue_id, embedding) VALUES (%s, %s, %s, %s, %s)",
            (paper_id, title, year, self._venue_id(venue), literal(vec) if vec else None))
        stored = []
        for exp in experiments:
            m, d, t = exp[:3]
            sentence, extractor = (exp[3], exp[4]) if len(exp) > 3 else (None, None)
            ids = (self.element("method", m), self.element("dataset", d) if d else None,
                   self.element("task", t) if t else None)
            self.conn.execute(
                "INSERT INTO experiment (paper_id, method_id, dataset_id, task_id, source_sentence, extractor) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (paper_id, *ids, sentence, extractor))
            stored.append(ids)
        self.papers[paper_id] = {"year": year, "experiments": stored, "vec": vec, "title": title, "venue": venue}

    def cites(self, citing, cited):
        self.conn.execute("INSERT INTO citation (citing_paper_id, cited_paper_id) VALUES (%s, %s)", (citing, cited))
        self.citations.append((citing, cited))


M1, M2 = "Method One", "Method Two"
D1, D2 = "Dataset One", "Dataset Two"
T1, T2 = "Task One", "Task Two"


def standard_world(conn, include_null_year=True):
    """13 papers. The pair used in most tests is A = (method, Method One), B = (task, Task One).
    P01, P02, P09, P12 use A without B; P03, P04, P11 use B without A; P05, P06 use both in one experiment;
    P07 uses A and B in different experiments; P08 has no task (outside the universe); P10 has no year;
    P12 has no embedding; P13 uses neither."""
    w = World(conn)
    for kind, names in (("method", (M1, M2)), ("dataset", (D1, D2)), ("task", (T1, T2))):
        for name in names:
            w.element(kind, name)
    w.paper("P01", 2015, [(M1, D1, T2, "S P01", "ex-1")], venue="Venue A")
    w.paper("P02", 2016, [(M1, D1, T2, "S P02", "ex-1")], venue="Venue B")
    w.paper("P03", 2017, [(M2, D1, T1, "S P03", "ex-1")], venue="Venue A")
    w.paper("P04", 2018, [(M2, D2, T1, "S P04", "ex-1")])
    w.paper("P05", 2019, [(M1, D1, T1, "S P05", "ex-1")], venue="Venue B")
    w.paper("P06", 2020, [(M1, D1, T1, "S P06 together", "ex-2")], venue="Venue A")
    w.paper("P07", 2021, [(M1, D1, T2, "S P07 a-row", "ex-1"), (M2, D1, T1, "S P07 b-row", "ex-1")])
    w.paper("P08", 2022, [(M1, D2, None, "S P08", "ex-1")])
    w.paper("P09", 2023, [(M1, D1, T2, None, None)], venue="Venue B")
    if include_null_year:
        w.paper("P10", None, [(M1, D1, T1, "S P10", "ex-1")])
    w.paper("P11", 2024, [(M2, D1, T1, "S P11", "ex-1")], venue="Venue A")
    w.paper("P12", 2018, [(M1, D2, T2, "S P12", "ex-1")], embedded=False)
    w.paper("P13", 2019, [(M2, D1, T2, "S P13", "ex-1")])
    for citing, cited in (("P13", "P02"), ("P13", "P03"), ("P06", "P01"), ("P06", "P04"), ("P09", "P04"),
                          ("P11", "P01"), ("P05", "P01"), ("P07", "P03"), ("P12", "P03")):
        w.cites(citing, cited)
    if include_null_year:
        w.cites("P10", "P02")
        w.cites("P10", "P03")
    return w


# --- brute force (plain Python on the same data) -----------------------------------------------

def universe(world, kind_a, kind_b, cutoff):
    """[(paper_id, experiment_tuple)] for experiments with both columns present, paper year known and <= cutoff."""
    rows = []
    for pid, p in world.papers.items():
        if p["year"] is None or p["year"] > cutoff:
            continue
        for exp in p["experiments"]:
            if exp[COL[kind_a]] is not None and exp[COL[kind_b]] is not None:
                rows.append((pid, exp))
    return rows


def sets(world, a, b, cutoff):
    """Return dict with N, uses_a, uses_b, exact, supports_a, supports_b (sets of paper ids)."""
    rows = universe(world, a[0], b[0], cutoff)
    uses_a = {pid for pid, e in rows if e[COL[a[0]]] == a[1]}
    uses_b = {pid for pid, e in rows if e[COL[b[0]]] == b[1]}
    exact = {pid for pid, e in rows if e[COL[a[0]]] == a[1] and e[COL[b[0]]] == b[1]}
    return {"universe": {pid for pid, _ in rows}, "uses_a": uses_a, "uses_b": uses_b, "exact": exact,
            "supports_a": uses_a - uses_b, "supports_b": uses_b - uses_a}


def counts(world, a, b, cutoff):
    s = sets(world, a, b, cutoff)
    n, n_a, n_b, obs = len(s["universe"]), len(s["uses_a"]), len(s["uses_b"]), len(s["exact"])
    return {"universe_size": n, "n_a": n_a, "n_b": n_b, "observed": obs, "expected": n_a * n_b / n if n else 0.0}


def cosine(x, y):
    return sum(i * j for i, j in zip(x, y)) / (math.sqrt(sum(i * i for i in x)) * math.sqrt(sum(j * j for j in y)))


def centroid(vectors):
    return [sum(col) / len(vectors) for col in zip(*vectors)]


def nearest(world, a, b, cutoff, limit):
    """[(paper_id, tier, similarity or None)] following the documented semantics."""
    s = sets(world, a, b, cutoff)
    by_year = lambda pid: (-world.papers[pid]["year"], pid)
    result = [(pid, "exact", None) for pid in sorted(s["exact"], key=by_year)][:limit]
    if len(result) < limit:
        def side(candidates, other_users):
            vecs = [world.papers[p]["vec"] for p in other_users if world.papers[p]["vec"] is not None]
            if not vecs:
                return []
            c = centroid(vecs)
            return [(pid, "close", cosine(world.papers[pid]["vec"], c)) for pid in candidates
                    if world.papers[pid]["vec"] is not None]
        close = side(s["supports_a"], s["uses_b"]) + side(s["supports_b"], s["uses_a"])
        close.sort(key=lambda r: (-r[2], r[0]))
        result += close[:limit - len(result)]
    return result


def bridge(world, a, b, cutoff):
    s = sets(world, a, b, cutoff)
    out = set()
    for pid, p in world.papers.items():
        if p["year"] is None or p["year"] > cutoff:
            continue
        cited = {cd for cg, cd in world.citations if cg == pid}
        into_a, into_b = bool(cited & s["supports_a"]), bool(cited & s["supports_b"])
        if (into_a and into_b) or (pid in s["supports_a"] and into_b) or (pid in s["supports_b"] and into_a):
            out.add(pid)
    return out


def yearly(world, a, b, cutoff):
    rows = universe(world, a[0], b[0], cutoff)
    if not rows:
        return []
    per_year = {}
    for pid, e in rows:
        year = world.papers[pid]["year"]
        y = per_year.setdefault(year, {"a": set(), "b": set(), "both": set()})
        if e[COL[a[0]]] == a[1]:
            y["a"].add(pid)
        if e[COL[b[0]]] == b[1]:
            y["b"].add(pid)
        if e[COL[a[0]]] == a[1] and e[COL[b[0]]] == b[1]:
            y["both"].add(pid)
    return [{"year": year, "a": len(per_year.get(year, {"a": ()})["a"]), "b": len(per_year.get(year, {"b": ()})["b"]),
             "both": len(per_year.get(year, {"both": ()})["both"])}
            for year in range(min(per_year), max(per_year) + 1)]


def order_by_year(world, pids):
    return sorted(pids, key=lambda pid: (-world.papers[pid]["year"], pid))
