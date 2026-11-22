# Paper Compass: demo runbook

Written from a real run of the app on **2026-11-23**: every screen below was opened in Chrome 158 against the demo
database `pc_demo_opps`, every query was run, and every number marked "(live)" was read from that run. Numbers marked with a
file name come from that file. Anything I could not check is marked **unverified**. The three presenters are assigned by
area following the order of the team list in `context/docs/reference/project-plan-v2.md` and the ownership table in
`context/build-plan.md` (Person 1 data and extraction, Person 2 database and retrieval, Person 3 scoring, graph and API);
`context/build-plan.md` leaves the names as TBD, so **confirm the assignment** before the demo.

| Area | Presenter | Screens |
|---|---|---|
| Data and extraction | Samarth Kulkarni | Story steps 0 to 2, the paper drawer |
| Database and retrieval (PostgreSQL, pgvector, Neo4j) | Samarth P Rao | Papers (vector, keyword, hybrid), Graph |
| Scoring plus UI | Samarth Sainath Naik | Candidates, evidence drawer, Landscape, limits |

---

## 1. Setup checklist (do this 15 minutes before)

### 1.1 Start everything

Run each block in its own PowerShell window. The repository root below is the checkout you demo from (`pc-work` here).

**a) The databases** (two containers: `pc-postgres`, `pc-neo4j`). Check, then start only if needed:

```powershell
docker ps --format "{{.Names}}  {{.Status}}"          # expect: pc-postgres (healthy) and pc-neo4j
docker start pc-postgres pc-neo4j                      # only if one is missing; never "down -v", never recreate
```

If the containers do not exist at all: `cd db; docker compose up -d` (needs `db\.env`, see `db/README.md`).

**b) The API on port 8000, against the demo database `pc_demo_opps`.** The passwords are read from `db\.env` into
environment variables and are never printed:

```powershell
cd <repo root>
Get-Content db\.env | Where-Object { $_ -match '^\s*([A-Z0-9_]+)=(.*)$' } | ForEach-Object { Set-Item "env:$($Matches[1])" $Matches[2] }
$env:PC_PG_DSN = "postgresql://$($env:POSTGRES_USER):$($env:POSTGRES_PASSWORD)@127.0.0.1:5432/pc_demo_opps"
$env:PC_NEO4J_URI = "bolt://127.0.0.1:7687"; $env:PC_NEO4J_USER = $env:NEO4J_USER; $env:PC_NEO4J_PASSWORD = $env:NEO4J_PASSWORD
# the embeddings packages (torch, transformers, adapters) must come first, or vector and hybrid search are unavailable:
$env:PYTHONPATH = "<path to>\db\embeddings\.venv\Lib\site-packages"
<path to the API venv>\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

(In this checkout the API venv is `..\pc-envs\api-venv` and the embeddings packages are in the other checkout,
`..\paper-compass-main\db\embeddings\.venv`. Using `PYTHONPATH` this way was run and works: `/health` says `ok` and the
encoder is available. Without it the API starts but is `degraded`, see Known issues.) The API loads the search model in the
background; it was ready **30 to 63 seconds** after start on this machine (live). Do not demo a search before
`query_encoder.loaded` is `true`.

**c) The UI on port 5173:**

```powershell
cd <repo root>\ui
npm ci            # first time only
npm run dev       # http://localhost:5173  (it forwards /api to http://127.0.0.1:8000)
```

### 1.2 Demo database

| | |
|---|---|
| Demo database | **`pc_demo_opps`** (PostgreSQL 16.15 + pgvector 0.8.7, container `pc-postgres`) |
| What is in it (live) | 1,999 papers (all with an embedding), 1,055 experiments, 11,542 citations, 13 opportunities with 252 evidence rows, 20 tables, 12 materialized views |
| Neo4j (live) | one graph, 1,999 `Paper` nodes, 12,864 nodes and 34,796 relationships in total; the 11,542 `CITES` edges are the same set as the Postgres `citation` rows |
| Other databases on the server | `pc_pilot` (the original pilot database, the source of the dump), `paper_compass`, `pc_demo`, `pc_demo_synth`, `postgres`: do not write to them |

### 1.3 Sixty-second smoke test

Run this in PowerShell with the API up (it took **0.6 seconds** in total here, live). Expected output on the right.

```powershell
$B = "http://127.0.0.1:8000"
$h = Invoke-RestMethod "$B/health"; "health: status=$($h.status) papers=$($h.postgres.papers) opps=$($h.postgres.opportunities) neo4j_ok=$($h.neo4j.ok) neo4j_papers=$($h.neo4j.papers) encoder_loaded=$($h.query_encoder.loaded)"
$o = Invoke-RestMethod "$B/opportunities"; "opportunities: total=$($o.total) first=$($o.items[0].elements.method) x $($o.items[0].elements.task)"
$s = Invoke-RestMethod "$B/search" -Method Post -ContentType "application/json" -Body '{"query":"adam optimizer","top_k":3,"mode":"hybrid"}'; "hybrid search top: $($s.results[0].title)"
$g = Invoke-RestMethod "$B/papers/W4388691873/graph"; "graph: nodes=$($g.nodes.Count) edges=$($g.edges.Count)"
$e = Invoke-RestMethod "$B/opportunities/1/explain" -Method Post; "explain: source=$($e.summary_source) citations_ok=$($e.citation_check.ok)"
```

```
health: status=ok papers=1999 opps=13 neo4j_ok=True neo4j_papers=1999 encoder_loaded=True
opportunities: total=13 first=Masked Language Modeling x Machine Translation
hybrid search top: Adam: A Method for Stochastic Optimization
graph: nodes=28 edges=27
explain: source=template citations_ok=True
```

Then open http://localhost:5173 and check, in 5 to 10 seconds each: **Story** (a rotating dot sphere and "Paper Compass");
**Candidates** (13 rows, "Showing 13 of 13"); **Papers** (type `adam optimizer`, Hybrid, Search: the Adam paper first);
**Graph** (type `W4388691873`, Show: "28 nodes · 27 edges"); **Landscape** (a papers-per-year chart and 7 cluster rows).
Stop and fix anything that does not match before presenting.

### 1.4 Fallbacks

| If | What happens (tested) | What to do |
|---|---|---|
| **Neo4j is down or unreachable** | I ran an API whose Neo4j address pointed at a dead port. `/health` says `degraded` with `neo4j.ok: false`. The **Graph screen shows "Could not load the graph" with the raw driver error and a "Try again" button**. Candidates (13 rows), Landscape and Papers search all kept working. | Skip the live Graph step. Show `docs/screenshots/05-graph.png`. Do not open the Graph tab. Say Neo4j is a derived copy of PostgreSQL, so nothing is lost. |
| **The LLM** | It is **off by default** and no key is needed. `POST /opportunities/{id}/explain` returned `summary_source: "template"` and `summary_fallback_reason: null`, and the drawer shows the fixed-template explanation with "5 citations verified" (live). | Nothing to do. Do not claim an LLM wrote the explanation (see section 3). |
| **The search model is unavailable** (`/health` says `degraded`, "No query encoder") | Auto search falls back to keyword; Vector and Hybrid cannot work (`api/README.md`; I saw the degraded health, I did not click Vector in that state: **unverified**). | Restart the API with the `PYTHONPATH` line above. If there is no time, demo Keyword only and show `03-papers-hybrid-search.png`. |
| **The API is down** | Every screen shows its own error with a retry (unverified for each screen). | Switch to the screenshots (section 6). |

---

## 2. Timed script (about 9 minutes 30 seconds)

Clock times are cumulative. Each row: **Screen and click**, **Say**, **See**, **Likely question**. Keep the mouse still while
talking; the Story and Graph screens animate.

### Part A: data and extraction (Samarth Kulkarni), 0:00 to 1:50

**A1. 0:00 to 0:50. Story (home).** Open http://localhost:5173 (no `#`). Scroll slowly with the mouse wheel from "Paper Compass" to step 01.
- **Say:** "Paper Compass finds combinations of methods and tasks that are weakly represented in a corpus of low-resource machine translation papers. The corpus is 1,999 papers from OpenAlex, from 1951 to 2026. Everything you will see is a signal for human review, not a verdict."
- **See:** a rotating sphere of dots with the tag "ILLUSTRATION · NOT TO SCALE"; "Finding what the literature has not connected yet."; "An evidence-grounded exploration of a curated corpus of 1,999 papers."; counter 00 / 07; then step "01 · DISCOVER · The corpus" with 1,999 PAPERS and a year axis. The header corpus chip reads "1,999 papers 1951–2026 cutoff 2026 rules-v1 extraction".
- **Q: "Why 1,999 and not 2,000?"** A: One record was rejected as a duplicate DOI of the Adam paper (W1522301498 into W2964121744); 1,999 of 2,000 loaded (`db/pilot-report.md`, section 4). The deduplication report counts 1,975 after merging 25 duplicates (`extraction/accuracy_report.md`), but that merged corpus is not what this database holds.

**A2. 0:50 to 1:50. Story, step 02 "Methods and tasks".** Keep scrolling one step.
- **Say:** "Methods, tasks and datasets are pulled out of titles and abstracts by a rule-based extractor, version rules-v1, using a controlled vocabulary with aliases. It only finds a paper's elements when the abstract states them, so 634 of the 1,999 papers, about 32 percent, have at least one extracted experiment. That is the biggest limit of the whole system, and every count after this one inherits it."
- **See:** METHODS Transformer 185 papers, Fine-tuning 163, Transfer Learning 82, Data Augmentation 71; TASKS Machine Translation 338, Language Modeling 26, Question Answering 10, Cross-Lingual Transfer 6 (all live).
- **Q: "How accurate is the extraction?"** A: Not measured against people. The only check set is 50 abstracts labelled by two regular-expression passes, which is not independent of the extractor; the two passes agree on 44 of 50 papers (88.0%). Against that set the method precision is 63.6% and task recall 43.5%, and the report itself says these are not accuracy figures (`extraction/accuracy_report.md`, sections 1 and 3).

### Part B: database and retrieval (Samarth P Rao), 1:50 to 5:00

**B1. 1:50 to 2:50. Papers, vector search.** Click the **Papers** tab. Click **Vector**. Type `low-resource neural machine translation`. Press Search.
- **Say:** "Each paper's title and abstract was turned into a 768-number SPECTER2 embedding and stored in PostgreSQL with pgvector. The query is embedded the same way and an HNSW index finds the nearest papers by cosine similarity. On this data the index query takes about 2.5 milliseconds from Python."
- **See:** "20 results for 'low-resource neural machine translation' · mode vector · score cosine_similarity" (about 270 ms end to end, live). Top three: "Low-resource Neural Machine Translation: Methods and Trends" (2022, score 0.828), "Neural machine translation for low-resource languages" (2017), "Low-Resource Neural Machine Translation: A Systematic Literature Review" (2023). Each card has a rank number, a score meter, element tags and a paper id.
- **Q: "Why HNSW? How good is it?"** A: Measured on 200 queries: recall@10 against an exact scan is 0.9995 (one query found 9 of 10), and the median query is 2.48 ms against 7.04 ms for an exact scan. At 1,999 rows an exact scan is already fast, so the index matters for growth, not today (`docs/measurements.md`).

**B2. 2:50 to 3:35. Papers, keyword and hybrid.** Click **Keyword**, type `adam optimizer`, Search. Then click **Hybrid**, type `zero-shot translation`, Search.
- **Say:** "Keyword search is PostgreSQL full text and every word has to match, so 'adam optimizer' finds only four papers. Hybrid mode runs both searches and merges the two ranked lists with reciprocal rank fusion, and each card shows its rank in the vector list and in the keyword list."
- **See:** Keyword: "4 results for 'adam optimizer' · mode keyword · score ts_rank", Adam first. Hybrid for `zero-shot translation`: top is "Improving Zero-shot Multilingual Neural Machine Translation for Low-Resource Languages" with pills "vector #2 keyword #1", then "Google's Multilingual Neural Machine Translation System: Enabling Zero-Shot Translation" "vector #1 keyword #3" (live).
- **Q: "Is hybrid better?"** A: We do not know. It was only checked by counting lexical matches on 3 queries, which favours keyword search, and there are no human relevance labels (`db/pilot-report.md`, section 8). Hybrid ignores method, task and dataset filters and says so with a visible note (live).

**B3. 3:35 to 4:10. Papers drawer (with Kulkarni).** Search `low-resource neural machine translation` in **Hybrid**; click the first card.
- **Say (Rao):** "Clicking a result opens the paper's record from PostgreSQL: authors, venue, DOI, abstract, citations inside the corpus and related papers by embedding." **Say (Kulkarni):** "This one is a survey, and the extractor found no methods or tasks in it: it shows 'no elements extracted'. That is what the 32 percent coverage looks like in practice."
- **See:** "Low-Resource Neural Machine Translation: A Systematic Literature Review", 2023, IEEE Access, id W4388953014, "no elements extracted", "Cites (37 in corpus)", "Cited by (4 in corpus)", "Related by embedding", a "Show in graph" button (live).
- **Q: "Only 37 citations?"** A: Only citations to papers inside the corpus are stored: 11,542 of 78,513 listed references; the rest point outside the 1,999 papers, so citation counts here are lower bounds (`db/pilot-report.md`, section 4).

**B4. 4:10 to 5:00. Graph.** Press Esc. Click the **Graph** tab. In "Center paper id" type `W4388691873`, press Show.
- **Say:** "The graph is Neo4j. PostgreSQL stays the source of truth, and the graph is a copy rebuilt by an idempotent sync, with the same paper ids. It holds 12,864 nodes and 34,796 relationships and the counts match the SQL tables. Here is one paper with its authors, venue, extracted methods, task and the papers it cites or is cited by."
- **See:** legend Paper 13, Bridge 2, Method 4, Task 1, Author 7, Venue 1; "28 nodes · 27 edges"; a glowing star-shaped graph (live).
- **Q: "Why Neo4j if PostgreSQL can do it?"** A: Honest answer: for 1 and 2 hop citation lookups here, a recursive CTE in PostgreSQL was faster than Cypher (1 hop 0.63 ms against 2.40 ms, 2 hops 0.71 against 2.52 ms) and returned identical results in 60 of 60 cases. Neo4j gives the graph screen and a natural model for longer traversals, which we did not measure (`docs/measurements.md`).

### Part C: scoring plus UI (Samarth Sainath Naik), 5:00 to 9:30

**C1. 5:00 to 6:15. Candidates, candidate #1.** Click the **Candidates** tab. Row 01 is selected.
- **Say:** "A candidate is a method and task pair that is used together less often than chance suggests. For Masked Language Modeling and Machine Translation, 14 papers use the method and 338 use the task among 399 papers that have both a method and a task, so about 11.9 papers should combine them by chance, and only 1 does. The score, 74, combines three signals: how sparse the pair is, how close the two are in embedding space, and recent activity."
- **See:** "Showing 13 of 13", 13 ranked rows with score rings (74, 71, 71, 67, 59 ...). Detail: Method "Masked Language Modeling", Task "Machine Translation", Score 74, "Observed Count: 1", "Expected: 11.9", "Confidence: 1.00", Sparsity 0.84, Semantic 0.75, Temporal 0.55, and "Closest existing work": Rethinking the Exploitation of Monolingual Data for Low-Resource Neural Machine Translation (W4388691873), mT5 (W3093517588), Masked Language Model Scoring (W3024308166) (live).
- **Q: "How is the score computed?"** A: Score = 100 × (0.40 × sparsity + 0.35 × semantic + 0.25 × temporal), each signal turned into a 0 to 1 rank among the candidates; sparsity is 1 − (observed + 1) / (expected + 1); the expected count is n_A × n_B / N = 14 × 338 / 399 = 11.86 (`scoring/README.md`, `scoring/tuning-pc_pilot.md`, section 5). The "What-if weights" button re-ranks with your own weights without changing the stored score.

**C2. 6:15 to 7:15. Evidence drawer.** Click **Evidence & explanation**.
- **Say:** "This is the explanation, and it is not written by a language model: it is a fixed template filled from the retrieved evidence, and every paper it names must be in the evidence set, which the badge 'five citations verified' confirms. Read the closest existing work: the first paper already uses both Masked Language Modeling and Machine Translation in one experiment. So this candidate is not an empty space; the counts say the pair is rare in our corpus."
- **See:** the banner "A candidate opportunity is a signal for human review, not proof of a research gap."; "5 citations verified"; "WHAT THE CORPUS SHOWS" (14 papers, 338 papers, 1 together, about 11.9 expected); "WHAT THE SYSTEM INFERS" ("potentially underexplored ... not a proven research gap"); "CLOSEST EXISTING WORK" with W4388691873 "uses both 'Masked Language Modeling' and 'Machine Translation' in one experiment"; tabs Supports A, Supports B, Bridge Work, Nearest Existing (5 each); a Limitations section (live).
- **Q: "Did an LLM write this? Can I trust it?"** A: No. The LLM option exists, is off by default, and was never shown working: 7 real calls to the model all failed with timeouts or 503/504 errors and returned no text (`rag/llm-summary.md`). The template summary is deterministic and its citations are checked against the evidence.

**C3. 7:15 to 8:00. Candidate #2, low confidence.** Press Esc. Click row **02 Transformer × Cross-Lingual Transfer**.
- **Say:** "Here the app flags weak evidence. Zero papers combine Transformer and Cross-Lingual Transfer, but only about 1.6 were expected, so a zero means little. The confidence is 0.32, shown in orange with the words 'Low confidence', and the score of 71 should be read with that."
- **See:** "Observed Count: 0", "Expected: 1.6", an orange "Confidence: 0.32" chip and the text "Low confidence"; the address bar changes to `#/candidates?opp=2`. The explain response for this candidate adds "This is low confidence because the expected count is small (about 1.6 papers)." (live, from the API; I opened the evidence drawer for candidate #1 in the browser, not for #2).
- **Q: "Why is a low-confidence pair ranked second?"** A: The score does not include confidence; confidence is shown beside it, not scored (`scoring/tuning-pc_pilot.md`, section 3). Confidence is min(1, expected / 5) and 6 of the 13 candidates have a value below 0.5 (live: #2, #8, #10, #11, #12, #13).

**C4. 8:00 to 8:40. Landscape.** Click the **Landscape** tab.
- **Say:** "The landscape is the corpus seen from above: papers per year, seven clusters found with HDBSCAN on the embeddings, and methods that are growing or shrinking. 883 of the 1,999 papers belong to no cluster, because the corpus is mostly about one subject."
- **See:** "Papers per year 1,991 with a year" and a gradient bar chart (hover a bar for the year and count; the peak is 2020 with 191 papers); a Clusters table with 7 rows (sizes 38, 420, 19, 69, 135, 398, 37); "883 of 1,999 papers belong to no cluster"; Temporal evolution with Emerging 12 and Declining 10 for methods; Bridge papers (live).
- **Q: "44 percent noise is a lot."** A: Yes (883 of 1,999). Clustering the full 768 dimensions was worse (2 clusters, 55.4% noise); we reduced to 20 dimensions first to get 7 clusters and 44.2% noise, with a low silhouette of 0.24 (`graph/README.md`).

**C5. 8:40 to 9:30. Limits and close (all three).** Click the logo "Paper Compass" (top left) to return to the Story and scroll to the last step, "A signal, not a verdict".
- **Say (Sainath Naik):** "To be clear about what this is not: a candidate is a signal for human review, not proof of a gap, and the counts come from rule-based extraction over a curated corpus, not the whole literature." **Say (Rao):** "Retrieval and hybrid search were checked by eye and by counting, not against human labels." **Say (Kulkarni):** "Extraction covers about 32 percent of papers and has no human-labelled accuracy yet."
- **See:** "07 · LIMITS · WHAT THIS IS NOT", "A candidate opportunity is a signal for human review, not proof of a research gap. Counts come from rule-based extraction over a curated corpus, not the whole literature.", and an "Open the explorer" button.
- **Q: "What would you do next?"** A: Human-labelled extraction check, a labelled query set for retrieval and hybrid, a larger and de-duplicated corpus, and the LLM explanation tested on a real model (all listed as not done in `extraction/accuracy_report.md`, `db/pilot-report.md`, `rag/llm-summary.md`).

---

## 3. What not to claim

| Do not say | Say instead | Source |
|---|---|---|
| "The system extracts methods and tasks accurately" | "Extraction is rule-based (rules-v1) and finds elements for about 31 to 32 percent of papers: 634 of 1,999 (31.7%) in this database, 623 of 1,975 (31.5%) in the deduplication report. No accuracy against human labels exists." | live SQL; `extraction/accuracy_report.md` section 2 |
| "We validated extraction on 50 abstracts" / "F1 is 78%" | "A 50-abstract check set was made by two rule passes, not by people; it is not independent ground truth and the comparison figures are not accuracy." | `extraction/accuracy_report.md` section 1 and 3 |
| "These are research gaps" / "nobody has done this" | "Potentially underexplored combinations in the analyzed corpus, for human review." Candidate #1's closest existing work already uses both Masked Language Modeling and Machine Translation. | `context/AGENTS.md` wording rules; live explain for opportunity 1 |
| "Hybrid search is better" | "Hybrid search exists and is optional; its benefit was not measured on labelled queries." | `db/pilot-report.md` section 8 |
| "The LLM explains the candidates" | "The explanation is a fixed template over verified evidence. The optional LLM is off by default and never produced a real answer." | `rag/llm-summary.md`; live `summary_source: template` |
| "HNSW makes search much faster" | "On 1,999 papers the index is 2.8x faster from Python (2.48 vs 7.04 ms) with recall 0.9995; the planner does not even choose it at the default setting on a table this small." | `docs/measurements.md` |
| "Neo4j is faster than SQL for graph queries" | "For 1 and 2 hop citation lookups here the recursive CTE was faster; results were identical." | `docs/measurements.md` |
| "The holdout proves the ranking works" | "On a temporal holdout the v1 weights beat random, but 'semantic only' scored higher under one hit definition, and there are only 1 to 10 hits per cutoff." | `scoring/tuning-pc_pilot.md` section 2 and 3 |
| "Counts are for the whole literature" | "Counts are over the 399 papers with both a method and a task, inside this corpus." | live explain; `context/data-and-contracts.md` same-universe rule |

---

## 4. Q&A cheat sheet (10 questions)

Numbers below were checked against the named file, or marked (live) for what I read from the running database or app.

1. **What is the schema and is it normalized?** 20 tables (live): papers, authors, venues, institutions, citations, the controlled vocabularies (method, task, dataset, setting) with alias tables, `experiment`, and the `opportunity` tables. All tables are intended to be in 3NF; `opportunity` stores derived scores on purpose (a deliberate denormalization for speed and reproducibility), and an experiment is unique per (paper, method, dataset, task, setting) with `NULLS NOT DISTINCT` (`context/data-and-contracts.md`, "Normal form"; decision 17 in `context/decisions-and-progress.md`). Honestly, the `topic`, `paper_topic` and `result` tables exist but hold 0 rows, and there are 12 materialized views for the counts (live).
2. **Why Neo4j as well as PostgreSQL?** PostgreSQL is the source of truth; Neo4j is a derived projection loaded by an idempotent `MERGE` sync, with the same paper ids (hard rule 2 in `context/AGENTS.md`; `graph/README.md`). It holds 12,864 nodes and 34,796 relationships and every label and relationship count matches SQL (`graph/README.md`; the totals re-checked live). The measured comparison favours the CTE for 1 and 2 hops (0.63 vs 2.40 ms, 0.71 vs 2.52 ms, identical results), so we justify Neo4j by the graph screen and longer traversals, which are unmeasured (`docs/measurements.md`).
3. **Why HNSW, and does it lose results?** An HNSW index on `paper.embedding` (vector(768), cosine) finds nearest papers without scanning every row. On 200 queries recall@10 was 0.9995 with 1 query below 1.0, and the median query was 2.48 ms against 7.04 ms exact from Python (0.50 vs 4.66 ms inside the database); the index uses pgvector's default m = 16 and ef_construction = 64 (no `WITH` clause in `db/init.sql`; the defaults are documented, not read back) (`docs/measurements.md`).
4. **How is the score computed?** Score = 100 × Σ w_i s_i with the default weights 0.40 sparsity, 0.35 semantic compatibility, 0.25 temporal activity (`v1-three-signal`), where each signal is normalized by its percentile rank among the candidates (`scoring/README.md`; weights confirmed live in the What-if panel). Candidate #1 scores 73.7 with signals 0.84, 0.75, 0.55 (`scoring/tuning-pc_pilot.md`, section 5; same values live).
5. **How is the expected count calculated?** expected = n_A × n_B / N over the same set of papers, those where both a method and a task were extracted (the same-universe rule), and sparsity = 1 − (observed + 1) / (expected + 1). For candidate #1: 14 × 338 / 399 = 11.8596 and sparsity 0.8445, matching a raw SQL check (`scoring/tuning-pc_pilot.md`, section 5; `scoring/README.md`).
6. **What does the confidence mean?** Confidence = min(1, expected / 5): a count of zero means little when fewer than about five papers were expected. Candidate #2 has expected 1.6 and confidence 0.32 and is flagged "Low confidence"; confidence is shown beside the score, not part of it (`scoring/README.md`; `scoring/tuning-pc_pilot.md` section 3; live).
7. **What does the holdout show?** For each cutoff year from 2020 to 2023 the candidates are built from papers up to that year and checked against later papers. With `min_sparsity` 0.3, mean AP is 0.829 for v1 against 0.550 random and 0.631 sparsity-only, but 0.882 for semantic-only; for pairs used together for the first time later, v1 gets 0.975 against random 0.488. There are only 1 to 10 hits per cutoff, so one swap moves AP more than the gaps between settings (`scoring/tuning-pc_pilot.md`, sections 2 and 3). It measures whether a pair was taken up later in this corpus, not whether it was a real gap.
8. **How good is the extraction and how much does it cover?** Rule-based (`rules-v1`, threshold 0.70) and covers 634 of 1,999 papers (31.7%, live; the deduplication report says 623 of 1,975, 31.5%); 719 of 1,055 experiments have a task and only 40 name a dataset (3.8%, live; `db/pilot-report.md` section 4 gives the same 40 of 1,055). There is no human-labelled accuracy; the 50-abstract set is made by rules (88.0% agreement between two rule passes) (`extraction/accuracy_report.md`).
9. **How was retrieval evaluated?** It was not, with labels. Eight queries were checked by eye, and for "back-translation for low-resource languages" the top 5 holds 0 papers matching a lexical rule for vector search, 5 for keyword and 4 for hybrid; the rule favours keyword search, so this is not a blind evaluation (`db/pilot-report.md`, sections 3 and 8). Hybrid fuses the top 50 of each list with reciprocal rank fusion, k = 60.
10. **What are the main limitations?** One small, skewed corpus: 1,999 papers, Machine Translation is 338 of the 399 papers in the Method × Task universe and 51 titles repeat (live); only 11,542 of 78,513 listed references point inside the corpus (`db/pilot-report.md` section 4; `scoring/tuning-pc_pilot.md` section 7). Extraction is rule-based with no accuracy figure, "used together" means in the same abstract, the LLM explanation was never shown working, and candidates are signals for review, not proof of gaps.

---

## 5. Likely follow-ups that are not in the cheat sheet

- **"Why does Landscape call Transformer declining?"** The label is a growth rule (slope over the last 5 years divided by the mean, at most −0.1; `graph/trends.py`), applied to counts per year. Transformer is the most-used method (185 papers) and still appears under Declining (live). The cause (for example a partial final year) is **unverified**; say it is a growth label, not a popularity ranking.
- **"Why 185 papers for Transformer on the Story but 107 in the score?"** The Story counts all papers with the method; the candidate arithmetic uses only the 399 papers that also have a task (`scoring/tuning-pc_pilot.md`, section 1). The same-universe rule in `context/data-and-contracts.md`.
- **"Is the ranking stable?"** Moderately. Shifting each weight by ±0.1 keeps the top-10 overlap at 0.8 to 1.0; by ±0.2 the top-5 overlap drops to 0.4 to 1.0, which is why the UI shows every signal and has what-if sliders (`scoring/tuning-pc_pilot.md`, section 4).

---

## 6. Backup plan: screenshots

All files are in `docs/screenshots/` (2880 x 1800, dark theme, taken from this run against `pc_demo_opps`). If the live app fails, say what
you were about to show and put up the matching image.

| Step | If this fails | Show |
|---|---|---|
| A1, A2 (Story) | UI will not load, or the animation stutters | `01-story-home.png` (the opening step); for step 02 describe the numbers from section 2 |
| B1, B2 (Papers search) | API down, or no search model | `03-papers-hybrid-search.png` (hybrid results for "back-translation for low-resource languages" with the vector and keyword pills) |
| B3 (paper drawer) | drawer will not open | `04-papers-paper-drawer.png` |
| B4 (Graph) | Neo4j or the graph is down | `05-graph.png` (W4388691873, 28 nodes and 27 edges); to explain the failure on screen use `08-graph-neo4j-unavailable.png` |
| C1 (Candidates #1) | Candidates will not load | `02-candidates-detail-panel.png` |
| C2 (evidence drawer) | drawer or explain call fails | `04b-candidates-evidence-drawer.png` |
| C3 (low confidence) | row 02 will not select | `07-candidates-low-confidence.png` |
| C4 (Landscape) | Landscape fails | `06-landscape.png` |
| Numbers behind the screens | any question about recall or CTE vs Cypher | `docs/measurements.md` (tables) |

The screenshots differ from the live steps in two ways: `03` and `04` use the query "back-translation for low-resource languages" (the live steps use "low-resource neural machine translation" and "zero-shot translation"), and `04` shows the drawer of a different paper (a Bavarian case study, not the survey of step B3). Say so if you use them.

---

## 7. Known issues (found while preparing this runbook)

1. **The documented start does not give a working search model by itself.** An API started with plain `uvicorn api.main:app` from the API venv answered `/health` with `status: degraded`, `query_encoder.available: false` and the note "No query encoder (torch / transformers / adapters missing ...)": search then falls back to keyword and Hybrid is unavailable. It works when the embeddings packages are first on the path (the `PYTHONPATH` line in 1.1; `status: ok`). `api/README.md` mentions the packages but not this step.
2. **`api/run-api.ps1` cannot run as written in this checkout.** It calls `.venv\Scripts\python.exe` at the repository root, which does not exist here (the API venv is `..\pc-envs\api-venv`), and it defaults to the database `pc_pilot`, not the demo database.
3. **`ui/README.md` is out of date.** It describes a three-pane layout with a left search sidebar and paginated candidate cards. The running UI has header tabs (Candidates, Papers, Graph, Landscape), the Story as the home page (the logo links to it), a Filters slide-over, and a Candidates screen with a ranked list and a detail panel.
4. **Opportunity ids differ from the docs.** `scoring/tuning-pc_pilot.md` quotes `/opportunities/14/explain` for the top candidate; in `pc_demo_opps` the ids are 1 to 13 and the top candidate is id 1.
5. **The demo database is the 1,999-paper pilot corpus, not the deduplicated 1,975-paper corpus** that `extraction/accuracy_report.md` describes. Differences seen live: 51 titles still repeat; 40 of 1,055 experiments name a dataset (3.8%), against 10.1% (104 of 1,033) in the report; 634 papers (31.7%) have experiments, against 623 (31.5%). Quote numbers with their source.
6. **When Neo4j is down the Graph screen shows the raw driver error** ("Neo4j unavailable: ServiceUnavailable: Couldn't connect to 127.0.0.1:7999 ... [WinError 10061] ..."). The "Try again" button works and the other screens are unaffected, but the text is not presentation-friendly (screenshot `08-graph-neo4j-unavailable.png`).
7. **Keyword search needs every word to match.** `adam optimizer` returns 4 papers, and a long natural-language query can return few or none (the response note says so, per `api/README.md`). Use Vector or Hybrid for natural-language queries.
8. **Landscape labels Transformer as "declining"** although it is the most-used method (185 papers). The rule is in `graph/trends.py`; why this method falls under it is **unverified**.
9. **The first search after starting the API waits for the model.** The encoder was ready 30 to 63 seconds after start (live); a search before that is not safe to demo.
10. **Not tested:** the LLM path (no key used, off by default), the light theme and reduced-motion modes in the demo flow, the Landscape "Weakly connected cluster pairs" section (the demo database has none, so the section is hidden), and any screen with the API down. Opening each screen in Chrome gave **0 console errors and 0 failed requests** (live).

---

## 8. What was run for this runbook

- Stack: PostgreSQL 16.15 + pgvector 0.8.7 and Neo4j 5.26.32 in Docker; API (FastAPI) against `pc_demo_opps`; UI dev server; Chrome 158 driven through its DevTools protocol (headless).
- Searches (all three modes each, `top_k` 5 through the API, and through the UI): "low-resource neural machine translation", "zero-shot translation", "adam optimizer". All returned results; timings through the UI were 267 ms (vector), 271 to 540 ms (keyword) and about 530 to 540 ms (hybrid).
- Candidates #1 and #2 (and the whole list of 13), both evidence drawers and the explain responses, the paper drawer, the Graph for W4388691873, Landscape and its API, the command palette (Ctrl+K lists the 13 candidates and the screens), the what-if weights panel (0.40 / 0.35 / 0.25), hybrid with a method filter (shows the note "Hybrid search applies only the year range, so your method, task and dataset filters were not used. Use vector or keyword mode to apply them."), and an API with Neo4j unreachable.
- Database facts read by SQL (read only): 20 tables, 12 materialized views, 1,999 papers (1,991 with a year), 634 papers with experiments, 1,055 experiments, 11,542 citations, 13 opportunities, 252 evidence rows, 51 repeated titles, no replacement characters in titles or abstracts.
