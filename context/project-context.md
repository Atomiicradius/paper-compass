# project-context.md

Short, stable background. Details and reasoning: `docs/reference/project-plan-v2.md`.

## Problem
Researchers can find papers easily but still have to connect methods, tasks, datasets, and topics by hand to see what is well covered and what is weakly covered. Existing tools return paper lists and citation views; they do not rank weakly represented combinations or show traceable evidence for them.

## Pipeline
```text
DISCOVER → CONNECT → MAP → DETECT → SCORE → EXPLAIN
```

| Stage | What happens | Technology |
|---|---|---|
| Discover | Embed the query, retrieve similar papers, apply metadata filters | pgvector + PostgreSQL |
| Connect | Exact metadata, citations, entity relationships | PostgreSQL + Neo4j |
| Map | Clusters, temporal trends, bridges, weak links | SQL + Neo4j + embeddings |
| Detect | Find weakly represented combinations | PostgreSQL materialized views |
| Score | Rank candidates with normalized signals | Python scoring engine |
| Explain | Structured evidence chain, then RAG phrasing | PostgreSQL + Neo4j + LLM |

## Positioning
A DBMS / system-engineering project with intelligent retrieval and analysis components. We are not proposing a new embedding model, LLM, or graph algorithm. The contribution is the integrated, evidence-grounded workflow.

**Defensible novelty:** detecting and explaining potentially underexplored combinations of research elements (methods, tasks, datasets, topics, settings), ranked by semantic, graph, temporal, and sparsity signals, with the evidence behind each result.

**Do not claim novelty for:** semantic search, citation graphs, knowledge graphs, paper recommendation, clustering, temporal mapping, RAG, generic research-gap detection, graph + embeddings, method-aware recommendation.

**Do not claim "research-gap accuracy."** Evaluation shows plausibility and predictive signal, not ground truth.

## Architecture in one view
- **PostgreSQL** (authoritative): structured metadata, constraints, aggregation, combination counts.
- **pgvector** (inside PostgreSQL): semantic similarity over paper embeddings.
- **Neo4j** (derived graph): citations, entity relationships, multi-hop traversal, bridges.
- A shared `paper_id` links all three. Neo4j is rebuilt from PostgreSQL by an idempotent batch sync.
- RAG receives structured evidence from all three and phrases it. It is never the source of findings.

## Key modeling decision
`EXPERIMENT` rows (paper, method, dataset, task, setting) mean "used together." Co-occurrence in a paper is not enough to claim a method was evaluated on a dataset. All combination counts come from experiments. Results attach to experiments. Details in `data-and-contracts.md`.

## Scope

**Core (must build):** PostgreSQL schema, pgvector search, Neo4j graph, controlled vocabulary with aliases and extraction provenance, weak-combination detection (pairs first), normalized scoring with confidence, structured evidence chain, RAG with citation verification, evaluation, DBMS benchmarks, demo UI.

**Stretch:** triple combinations, graph bridge strength and method compatibility as extra signals, weight sliders, feedback buttons, richer clustering.

**Deferred / cut:** temporal forecasting, contradiction analysis, intra-paper knowledge graph, collaboration analysis, research path finder, method transfer detector.

**Feature test before adding anything:** (1) improves research discovery? (2) uses the database/graph architecture meaningfully? (3) provides evidence, not just an LLM answer? (4) can we build and demo it? (5) can we explain why it differs from existing tools? If most answers are no, it is not core.

## Glossary
| Term | Meaning |
|---|---|
| Research element | A method, task, dataset, topic, or setting |
| Experiment | A row linking a paper to a method, dataset, task, and setting used together |
| Observed count | Distinct papers containing a combination |
| Expected count | Papers expected if elements were independent: `n_A * n_B / N`, with every count taken over papers where all elements of the pair were extracted |
| Bridge | A paper, author, method, dataset, or topic connecting two clusters |
| Candidate opportunity | A weakly represented combination ranked by score; a signal for human review |
| Evidence chain | Structured trail from a candidate to supporting papers and counts |
| Nearest existing work | Closest paper already combining some of the candidate's elements |
| Temporal holdout | Build the corpus up to year Y, then check which flagged combinations appear later |
