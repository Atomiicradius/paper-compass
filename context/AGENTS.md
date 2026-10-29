# AGENTS.md

Read this first, every session. It is the index for the project's context files.

All context lives in the `context/` folder of the repo. File paths below are relative to `context/`.

## What this project is
A research exploration system, not a paper search engine. Pipeline: **Discover → Connect → Map → Detect → Score → Explain.** It retrieves papers for a research idea (pgvector), maps relationships (PostgreSQL + Neo4j), finds research-element combinations that are individually common but rarely used together, ranks them, and explains the evidence with RAG.

A candidate opportunity is a **signal for human review, not proof of a research gap.**

## Which file to read for which task

| If your task involves... | Read |
|---|---|
| Anything (background, scope, wording rules) | `project-context.md` |
| Schema, SQL, Neo4j, extraction output, opportunity object, API | `data-and-contracts.md` |
| Who owns what, phases, evaluation, risks | `build-plan.md` |
| Open questions, past decisions, current status | `decisions-and-progress.md` |
| Deep reasoning behind any design choice | `docs/reference/project-plan-v2.md` |
| Original (older) context and literature review | `docs/reference/original-context.md` (not in the repo yet; ask the team if you need it) |

**Precedence when files disagree:** top-level context files (the five in `context/`) > `docs/reference/project-plan-v2.md` > `docs/reference/original-context.md`. The reference documents explain the reasoning; they are not the working spec. If a reference document conflicts with a root file, follow the root file and tell the team so the reference can be corrected.

## Folder ownership
`ingest/`, `extraction/` · `db/`, `retrieval/` · `graph/`, `scoring/` · `rag/` · `api/` · UI folder is **not created yet** (stack undecided).
Owners per folder are in `build-plan.md`. Do not edit another person's folder without telling them.

## Hard rules
1. **Schema and contract shapes are frozen** except through a team decision. To change `data-and-contracts.md`: tell the team, update that file, add a line to the decision log. Never alter a table, column, edge name, or JSON field silently.
2. **PostgreSQL is the source of truth.** Neo4j is a derived projection loaded by an idempotent batch sync (`MERGE`, never `CREATE`). Both use the same `paper_id`.
3. **Count distinct papers**, not experiment rows, for all frequencies. For pair statistics, compute `n_A`, `n_B`, `N`, and observed over the same set of papers (those where every element of the pair was extracted); see the same-universe rule in `data-and-contracts.md`.
4. **Never invent data.** Seed data, labels, extraction results, and evaluation numbers come from real sources or manual work. Mock data must be clearly marked as mock.
5. **Numeric code gets tests first** (counts, expected values, normalization, scoring). Verify at least one result per function against a raw SQL query.
6. **Evidence before explanation.** RAG phrases structured evidence already retrieved; it never invents gaps. Every paper named in an answer must be in the retrieved evidence set.
7. **Pin versions.** Lockfiles, Docker, and a recorded embedding model name and version.
8. **Small changes.** One module per branch, small pull requests, merge daily.
9. After finishing a task, update your section in `decisions-and-progress.md`.

## Open decisions (do not assume, ask first)
The live list is in `decisions-and-progress.md`. If a task touches an Open item (corpus source, embedding model, UI stack, score weights, thresholds, domain), stop and ask rather than choosing silently.

**UI stack is undecided: do not scaffold a UI.** Work against the mock data format in `data-and-contracts.md` if a prototype is requested.

## Wording rules (code comments, UI text, reports, RAG output)
Use: "potentially underexplored", "candidate research opportunity", "weakly represented in the analyzed corpus", "research-element combination", "evidence-grounded explanation".
Avoid: "definitely unexplored", "guaranteed research gap", "nobody has done this", "AI discovered a new research area".
Say "three complementary representations", not "three databases".

## Adding a context file
Only when a decision has actually been made or a module has stabilized. When you add one, add a line to the table above saying when to read it.
