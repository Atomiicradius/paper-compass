"""Cypher queries for the graph screens and the DBMS benchmark, plus the SQL
recursive-CTE equivalent for the multi-hop citation comparison.

Each function takes a neo4j session (or a psycopg connection for SQL) and
returns plain Python data.
"""

from __future__ import annotations

PAPERS_USING_METHOD = """
MATCH (p:Paper)-[:USES_METHOD]->(m:Method {canonical_name: $method})
RETURN p.paper_id AS paper_id, p.title AS title, p.year AS year
ORDER BY p.year DESC, p.paper_id
"""

# Experiment-level, so "evaluated together" is correct.
DATASETS_FOR_TASK = """
MATCH (e:Experiment)-[:SOLVES]->(:Task {canonical_name: $task})
MATCH (e)-[:EVALUATED_ON]->(d:Dataset)
MATCH (p:Paper)-[:HAS_EXPERIMENT]->(e)
RETURN d.canonical_name AS dataset, count(DISTINCT p) AS n_papers
ORDER BY n_papers DESC, dataset
"""

# Tasks that connect two methods: both methods were used on the task, in different experiments.
METHOD_BRIDGE_TASKS = """
MATCH (m1:Method {canonical_name: $a})<-[:USES_METHOD]-(e1:Experiment)-[:SOLVES]->(t:Task)
      <-[:SOLVES]-(e2:Experiment)-[:USES_METHOD]->(m2:Method {canonical_name: $b})
RETURN t.canonical_name AS task, count(DISTINCT e1) AS a_experiments, count(DISTINCT e2) AS b_experiments
ORDER BY a_experiments + b_experiments DESC, task
"""

# Shortest hop count for each paper reachable over 1..max_hops CITES edges.
MULTI_HOP_CITATIONS = """
MATCH path = (p:Paper {paper_id: $paper_id})-[:CITES*1..%d]->(q:Paper)
WHERE q <> p
RETURN q.paper_id AS paper_id, min(length(path)) AS hops
ORDER BY hops, paper_id
"""

MULTI_HOP_CITATIONS_SQL = """
WITH RECURSIVE reach(paper_id, hops) AS (
    SELECT cited_paper_id, 1 FROM citation WHERE citing_paper_id = %(paper_id)s
    UNION
    SELECT c.cited_paper_id, r.hops + 1
    FROM reach r JOIN citation c ON c.citing_paper_id = r.paper_id
    WHERE r.hops < %(max_hops)s
)
SELECT paper_id, MIN(hops) AS hops FROM reach
WHERE paper_id <> %(paper_id)s
GROUP BY paper_id ORDER BY hops, paper_id
"""

# Neighborhood for the Research Graph screen: the paper, its authors, venue, topics,
# methods / datasets / tasks (via shortcut edges) and direct citations both ways.
PAPER_NEIGHBORHOOD = """
MATCH (p:Paper {paper_id: $paper_id})
OPTIONAL MATCH (p)-[r]-(n)
WHERE type(r) IN ['WROTE', 'PUBLISHED_IN', 'ABOUT', 'USES_METHOD', 'EVALUATED_ON', 'SOLVES', 'CITES']
WITH p, collect(DISTINCT {rel: type(r), out: startNode(r) = p, node: n}) AS links
RETURN p, links[0..$limit] AS links
"""

_ID_KEYS = {
    "Paper": "paper_id", "Author": "author_id", "Venue": "venue_id", "Topic": "topic_id",
    "Method": "method_id", "Dataset": "dataset_id", "Task": "task_id",
}
_NAME_KEYS = ("title", "canonical_name", "name")


def _node_json(node) -> dict:
    label = next(iter(node.labels))
    props = dict(node)
    return {
        "id": f"{label}:{props.get(_ID_KEYS.get(label, ''), '')}",
        "label": label,
        "name": next((props[k] for k in _NAME_KEYS if props.get(k) is not None), None),
        "year": props.get("year"),
    }


def papers_using_method(session, method: str) -> list[dict]:
    return [r.data() for r in session.run(PAPERS_USING_METHOD, method=method)]


def datasets_for_task(session, task: str) -> list[dict]:
    return [r.data() for r in session.run(DATASETS_FOR_TASK, task=task)]


def method_bridge_tasks(session, a: str, b: str) -> list[dict]:
    return [r.data() for r in session.run(METHOD_BRIDGE_TASKS, a=a, b=b)]


def multi_hop_citations(session, paper_id: str, max_hops: int = 3) -> list[dict]:
    if not 1 <= max_hops <= 6:
        raise ValueError("max_hops must be between 1 and 6")
    # Variable-length bounds cannot be parameters in Cypher, so the validated int is inlined.
    return [r.data() for r in session.run(MULTI_HOP_CITATIONS % max_hops, paper_id=paper_id)]


def multi_hop_citations_sql(pg_conn, paper_id: str, max_hops: int = 3) -> list[dict]:
    with pg_conn.cursor() as cur:
        cur.execute(MULTI_HOP_CITATIONS_SQL, {"paper_id": paper_id, "max_hops": max_hops})
        return [{"paper_id": pid, "hops": h} for pid, h in cur.fetchall()]


def paper_neighborhood(session, paper_id: str, limit: int = 200) -> dict | None:
    """Nodes and edges around one paper, in a UI-agnostic {nodes, edges} shape."""
    rec = session.run(PAPER_NEIGHBORHOOD, paper_id=paper_id, limit=limit).single()
    if rec is None:
        return None
    center = _node_json(rec["p"])
    nodes = {center["id"]: center}
    edges = []
    for link in rec["links"]:
        if link["node"] is None:
            continue
        other = _node_json(link["node"])
        nodes[other["id"]] = other
        src, dst = (center["id"], other["id"]) if link["out"] else (other["id"], center["id"])
        edges.append({"source": src, "target": dst, "type": link["rel"]})
    return {"center": center["id"], "nodes": list(nodes.values()), "edges": edges}
