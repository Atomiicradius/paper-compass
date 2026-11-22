# ui/ (React + Vite + TypeScript + Tailwind)

Single-page UI for Paper Compass. It talks to the FastAPI backend (`api/`) **over HTTP only**: no SQL, no graph queries, no second server.

| Pane | What it is |
|---|---|
| Left | Search box (vector / keyword / auto), publication-year range, method / task / dataset / setting checklists, minimum confidence, duplicate-title switch |
| Center | **Candidates** (paginated cards: score, observed/expected, confidence, three signal meters, what-if weights), **Papers** (search results), **Graph** (interactive neighbourhood of one paper), **Landscape** (papers per year, clusters, emerging/declining elements, bridge papers) |
| Right | Slide-over **Evidence drawer** (warning banner, grounded explanation with verified citations, Supports A / Supports B / Bridge Work / Nearest Existing tabs, source sentences with highlighted entities) and a paper-details drawer |

Dark mode is "Obsidian Observatory", light mode is "Archival Daylight" (toggle in the header, remembered in `localStorage`). Tag colours are the same in both: Method blue, Task emerald, Dataset orange, Setting purple, Bridge rose.

## Run

Needs Node 22.12 or newer (developed on Node 24) and the API running on port 8000.

```powershell
# terminal 1, from the repository root: the API against the pilot database
powershell -File api\run-api.ps1

# terminal 2: the UI
cd ui
npm ci          # first time (installs the exact versions in package-lock.json)
npm run dev     # http://127.0.0.1:5173
```

In development the browser calls `/api/...` on the Vite server, which forwards it to the API (default `http://127.0.0.1:8000`, override with `PC_API_URL`). The API therefore needs no CORS settings. For a production build, serve `dist/` behind a proxy that maps `/api` to the API, or set `VITE_API_BASE` at build time to the API's address (and enable CORS on the API).

| Command | What it does |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm run typecheck` | `tsc --noEmit` (strict, `noUncheckedIndexedAccess`) |
| `npm test` | Vitest: logic, components, API client |
| `npm run build` | typecheck, then a production build in `dist/` |

There is no committed ESLint configuration: `typescript-eslint` does not support TypeScript 7 yet. The code was linted with
`eslint` 9, `typescript-eslint`, `eslint-plugin-react-hooks` 7 and `eslint-plugin-jsx-a11y` in a separate environment
with TypeScript 5.9: 0 findings, with one documented exception (the dependency list of `useAsync`).

## Mock data

Start the API with `PC_API_MOCK=1` and the UI works unchanged. When the API serves mock data it prefixes its disclaimer with "MOCK DATA", and the UI then shows an orange **MOCK DATA** banner on every screen (project rule 4).

## Which API endpoints

`GET /opportunities`, `POST /opportunities/{id}/explain`, `POST /search`, `GET /papers/{id}`, `GET /papers/{id}/graph`, `GET /papers/{id}/related`, `GET /landscape`, `GET /clusters`, `GET /trends`, `POST /rag/query` (501 until O5; the drawer says so). The explanation comes from `POST /opportunities/{id}/explain`; there is no `/rag/explain`. Types are in `src/api/types.ts` (opportunity = `context/data-and-contracts.md` section 4; the rest follow `api/api-shapes-o10.md`).

## Address bar

The hash remembers the view, the open opportunity, the open paper and the graph paper: `#/candidates?opp=14` opens that
opportunity's evidence, `#/graph?graph=W3028876793` centres the graph, a reload restores the screen, and Back closes a
drawer. Anything unrecognised in the hash is ignored. The search text and filters are not stored.

## Accessibility

Checked with axe-core in a real browser on every view (candidates, both drawers, papers, graph, landscape) in both themes:
no violations, including colour contrast (WCAG AA, 4.5:1). The semantic palette keeps its exact hex for dots, borders,
chart lines and graph nodes; **text** in those colours uses a darker shade (light theme) or lighter shade (dark theme) of
the same hue, because the exact hex fails contrast as text (Method blue on white is 3.7:1). The tokens are in
`src/index.css` (`--tag-text-*`, `--score-*`). The structural axe rules also run in the test suite
(`src/components/a11y.test.tsx`); contrast cannot run in jsdom, so it is only checked in a browser.

Keyboard: a card is one tab stop (its title button); opening a drawer moves focus into it, Tab stays inside, Escape or Back
closes it and focus returns to where it came from; the page behind is hidden from screen readers while it is open.

## Behaviour worth knowing

- **Citations are verified, not trusted.** A `[paper:W…]` marker in the explanation is shown as verified (violet) only if the API's citation check lists it as cited **and** the paper is one of the evidence papers in the drawer. Anything else is shown as unverified (orange) and cannot be followed. Clicking a verified one opens its tab and scrolls to it.
- **Filters.** Method / task / dataset / setting and minimum confidence filter the candidates in the browser (OR inside a group, AND across groups). Years and the element lists also go to `POST /search`. The year range does not apply to candidates, which are scored over a single cutoff year.
- **Settings.** The API has no endpoint that lists settings, and no stored candidate uses one yet, so the Settings list fills from stored candidates and is empty today. It is not invented.
- **What-if weights** re-rank the candidates in the browser with the same formula as `scoring/score.py` (`100 · Σ wᵢ sᵢ`); the stored score and weights version never change.
- **Truncated graphs.** The API's limit counts nodes. When a paper has more neighbours than that, the paper's own
  authors, venue and extracted elements are kept first, then its most recent citations, and the page says "Showing 199 of
  342 neighbours".
- **Graph.** Drawn on a canvas (`react-force-graph-2d`), loaded only when the Graph tab opens. Up to 1,000 nodes (the API's limit). Node types can be hidden; papers that bridge clusters or appear as bridge evidence are rose. Selecting a node opens a details overlay; "Re-center" reloads the graph around a paper. Pasting `Paper:W…`, a plain `W…` or an `https://openalex.org/W…` link all work.
- **Performance.** Candidate and result lists are paginated (6 per page). For 1,500 nodes the layout engine costs about 8 ms per tick and painting about 1 ms per frame on the development machine; above 400 nodes the simulation stops after 60 ticks.

## Layout

```
src/api/         types.ts (API shapes), client.ts (fetch wrapper, error mapping)
src/lib/         pure, tested logic: filtering, re-ranking, highlighting, citations, graph building, ids
src/components/  CandidateCard, CandidatesView, EvidenceDrawer, GraphView, LandscapeView, PapersView, Sidebar, motion.tsx
src/components/ui/primitives.tsx   themed Radix wrappers (tabs, tooltip, slider, checkbox, switch) and badges
```
