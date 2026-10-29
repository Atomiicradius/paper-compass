# paper-compass

Research Paper Discovery and Exploration System (DBMS course CD252IA, RV College of Engineering).

Pipeline: Discover -> Connect -> Map -> Detect -> Score -> Explain. It retrieves papers for a research idea, maps how the surrounding work is connected, and flags potentially underexplored combinations of research elements (methods, tasks, datasets, settings), ranked and backed by evidence. A candidate opportunity is a signal for human review, not proof of a research gap.

## Start here

All project context lives in [`context/`](context/). Read [`context/AGENTS.md`](context/AGENTS.md) first; it says which file to read for which task.

| File | Purpose |
|---|---|
| `context/AGENTS.md` | Index, hard rules, wording rules |
| `context/project-context.md` | Problem, positioning, scope |
| `context/data-and-contracts.md` | Schema, Neo4j model, extraction format, opportunity object, API |
| `context/build-plan.md` | Ownership, phases, evaluation, risks |
| `context/decisions-and-progress.md` | Open decisions, decision log, per-person progress |
| `context/docs/reference/project-plan-v2.md` | Detailed reasoning behind the design |

Schema and contract changes need a team decision (see the hard rules in `context/AGENTS.md`).
