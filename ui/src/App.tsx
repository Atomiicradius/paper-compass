import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Compass, Moon, PanelLeft, Sun, TriangleAlert } from "lucide-react";
import { api } from "@/api/client";
import type { Opportunity } from "@/api/types";
import { buildSearchRequest, type BuiltSearch } from "@/lib/search";
import { formatRoute, parseRoute, type Route, type View } from "@/lib/route";
import { useAsync, useTheme } from "@/lib/hooks";
import { normalizePaperId } from "@/lib/ids";
import { EMPTY_FILTERS, isMockData, type CandidateFilters } from "@/lib/opportunities";
import { cn } from "@/lib/utils";
import { Button, Mono, Skeleton, Tip, TooltipProvider } from "@/components/ui/primitives";
import { SmoothScrollProvider, useRegisterScroller, useScroller } from "@/components/SmoothScroll";
import { Reveal } from "@/components/Reveal";
import { Ambient } from "@/components/Ambient";
import { useSpotlight } from "@/lib/spotlight";
import { Sidebar, type FilterOptions, type SearchForm } from "@/components/Sidebar";
import { CandidatesView } from "@/components/CandidatesView";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { PaperDrawer, PapersView } from "@/components/PapersView";
import { LandscapeView } from "@/components/LandscapeView";

// the graph library is large and only needed on the Graph tab
const GraphView = lazy(() => import("@/components/GraphView").then((m) => ({ default: m.GraphView })));
// the story page (and its canvas) is loaded when the story is opened, so it adds nothing to the first bundle
const StoryView = lazy(() => import("@/components/story/StoryView"));

const VIEWS: { id: View; label: string }[] = [
  { id: "story", label: "Story" },
  { id: "candidates", label: "Candidates" },
  { id: "papers", label: "Papers" },
  { id: "graph", label: "Graph" },
  { id: "landscape", label: "Landscape" },
];

const DEFAULT_YEARS: [number, number] = [1951, 2026];

/** Corpus size, publication years, cutoff and extraction method: always on screen (project plan section 14.1). */
function CorpusStats({ papers, years, cutoff, className }: { papers: number; years: [number, number]; cutoff: number; className?: string }) {
  return (
    <p className={cn("mono-label items-center gap-x-4 gap-y-0.5", className)} aria-label="Corpus">
      <span><Mono className="text-foreground">{papers.toLocaleString()}</Mono> papers</span>
      <span><Mono className="text-foreground">{years[0]}–{years[1]}</Mono></span>
      <span>cutoff <Mono className="text-foreground">{cutoff}</Mono></span>
      <span>rules-v1 extraction</span>
    </p>
  );
}

function AppShell() {
  const registerScroller = useRegisterScroller();
  const scroller = useScroller();
  useSpotlight(); // the pointer-following highlight of the glass cards: one listener for all of them
  const [theme, toggleTheme] = useTheme();
  // the address bar remembers the view, the open drawer and the graph paper (see lib/route.ts)
  const [initialRoute] = useState(() => parseRoute(window.location.hash));
  const [view, setView] = useState<View>(initialRoute.view);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [form, setForm] = useState<SearchForm>({ query: "", mode: "auto", collapse: true, years: DEFAULT_YEARS });
  const [filters, setFilters] = useState<CandidateFilters>(EMPTY_FILTERS);
  const [submitted, setSubmitted] = useState<BuiltSearch | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(initialRoute.opp);
  const [paperId, setPaperId] = useState<string | null>(initialRoute.paper);
  const [graphId, setGraphId] = useState(initialRoute.graph);

  // ---- data
  const opps = useAsync((s) => api.opportunities(s), []);
  const landscape = useAsync((s) => api.landscape(s), []);
  const elementNames = useAsync(async (s) => {
    const [m, t, d] = await Promise.all([api.trends("method", s), api.trends("task", s), api.trends("dataset", s)]);
    const names = (xs: { name: string }[]) => [...new Set(xs.map((x) => x.name))].sort((a, b) => a.localeCompare(b));
    return { methods: names(m), tasks: names(t), datasets: names(d) };
  }, []);

  const selected: Opportunity | null = useMemo(
    () => (selectedId === null ? null : (opps.data?.items.find((o) => o.opportunity_id === selectedId) ?? null)),
    [selectedId, opps.data],
  );

  // keep the hash in step with the state (a new history entry per change, so Back closes a drawer) and the state in
  // step with the hash (Back / Forward / an edited link)
  const route: Route = useMemo(() => ({ view, opp: selectedId, paper: paperId, graph: graphId }), [view, selectedId, paperId, graphId]);
  useEffect(() => {
    const hash = formatRoute(route);
    if (hash !== window.location.hash && !(hash === "" && window.location.hash === "")) {
      window.history.pushState(null, "", hash || window.location.pathname + window.location.search);
    }
  }, [route]);
  useEffect(() => {
    const onPop = () => {
      const r = parseRoute(window.location.hash);
      setView(r.view);
      setSelectedId(r.opp);
      setPaperId(r.paper);
      setGraphId(r.graph);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // a new screen starts at the top (the story is a long scroll; the explorer should not open half way down it)
  useEffect(() => {
    if (scroller) scroller.scrollTop = 0;
  }, [view, scroller]);

  const yearBounds = useMemo<[number, number]>(() => {
    const ys = Object.keys(landscape.data?.papers_per_year ?? {}).map(Number);
    return ys.length ? [Math.min(...ys), Math.max(...ys)] : DEFAULT_YEARS;
  }, [landscape.data]);
  // when the real bounds arrive, widen an untouched slider to them (once, by adjusting state during render)
  const [boundsApplied, setBoundsApplied] = useState(false);
  if (!boundsApplied && landscape.data) {
    setBoundsApplied(true);
    setForm((f) => (f.years[0] === DEFAULT_YEARS[0] && f.years[1] === DEFAULT_YEARS[1] ? { ...f, years: yearBounds } : f));
  }

  const options: FilterOptions = useMemo(
    () => ({
      methods: elementNames.data?.methods ?? [],
      tasks: elementNames.data?.tasks ?? [],
      datasets: elementNames.data?.datasets ?? [],
      settings: [...new Set((opps.data?.items ?? []).map((o) => o.elements.setting).filter((s): s is string => !!s))].sort(),
    }),
    [elementNames.data, opps.data],
  );

  const bridgeIds = useMemo(() => {
    const ids = new Set<string>();
    landscape.data?.bridge_papers.forEach((b) => ids.add(b.paper_id));
    opps.data?.items.forEach((o) => o.evidence.bridge.forEach((id) => ids.add(id)));
    return ids;
  }, [landscape.data, opps.data]);

  const search = useAsync((s) => api.search((submitted as BuiltSearch).request, s), [submitted], submitted != null);

  const runSearch = useCallback(() => {
    if (!form.query.trim()) return;
    const built = buildSearchRequest(form, filters, yearBounds);
    setSubmitted(built);
    setView("papers");
    setSidebarOpen(false);
  }, [form, filters, yearBounds]);

  const openGraph = useCallback((id: string) => {
    setGraphId(normalizePaperId(id));
    setSelectedId(null);
    setPaperId(null);
    setView("graph");
  }, []);

  const stats = landscape.data;
  const mock = isMockData(opps.data?.disclaimer) || isMockData(landscape.data?.disclaimer);

  return (
    <TooltipProvider delayDuration={150} skipDelayDuration={300}>
      <Ambient />
      <div className="relative z-10 flex h-full flex-col">
        <Reveal as="header" self trigger="mount" y={-10} className="glass relative z-20 flex h-14 shrink-0 items-center gap-3 rounded-none border-0 border-b px-4">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Toggle search and filters" onClick={() => setSidebarOpen((o) => !o)}>
            <PanelLeft className="size-5" />
          </Button>
          <h1 className="flex shrink-0 items-center gap-2 font-display text-2xl leading-none tracking-tight whitespace-nowrap">
            <Compass className="size-5 text-primary" aria-hidden />
            <span className="sr-only sm:not-sr-only">Paper Compass</span>
          </h1>
          <nav aria-label="Views" data-lenis-prevent className="ml-2 flex gap-1 overflow-x-auto">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                aria-current={view === v.id ? "page" : undefined}
                onClick={() => setView(v.id)}
                className={cn(
                  "cursor-pointer rounded-lg border border-transparent px-3 py-1.5 font-mono text-[11px] font-medium tracking-[0.14em] whitespace-nowrap uppercase transition-colors",
                  view === v.id ? "border-[var(--glass-border)] bg-hover text-foreground" : "text-muted hover:text-foreground",
                )}
              >
                {v.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {stats ? <CorpusStats papers={stats.corpus.papers} years={yearBounds} cutoff={stats.corpus.cutoff_year} className="hidden xl:flex" /> : null}
            <Tip content={theme === "dark" ? "Switch to Archival Daylight" : "Switch to Obsidian Observatory"} side="bottom">
              <Button variant="outline" size="icon" aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggleTheme}>
                {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
              </Button>
            </Tip>
          </div>
        </Reveal>

        {stats ? <CorpusStats papers={stats.corpus.papers} years={yearBounds} cutoff={stats.corpus.cutoff_year} className="glass flex shrink-0 flex-wrap justify-center rounded-none border-0 border-b px-4 py-1.5 xl:hidden" /> : null}

        {mock ? (
          <div role="status" data-testid="mock-banner" className="flex shrink-0 items-center justify-center gap-2 border-b border-warning/60 bg-warning-soft px-4 py-1.5 text-sm font-semibold text-warning">
            <TriangleAlert className="size-4" /> MOCK DATA: this API is serving made-up records for UI development. These are not real results.
          </div>
        ) : null}

        <div className="relative flex min-h-0 flex-1">
          {/* left pane: search and discovery. On small screens it overlays the content. */}
          <div className={cn("absolute inset-y-0 left-0 z-30 w-80 max-w-[85vw] lg:static lg:z-auto lg:w-80 lg:shrink-0", view === "story" ? "hidden" : sidebarOpen ? "flex" : "hidden lg:flex")}>
            <Sidebar
              className="w-full"
              form={form} onForm={setForm} onSearch={runSearch} searching={search.loading && submitted != null}
              filters={filters} onFilters={setFilters} options={options} yearBounds={yearBounds}
            />
          </div>
          {sidebarOpen ? <button aria-label="Close filters" className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={() => setSidebarOpen(false)} /> : null}

          {/* center pane */}
          <main ref={registerScroller} className={cn("scroll-thin min-w-0 flex-1 overflow-y-auto", view === "story" ? "p-0" : "p-4 sm:p-6", view === "graph" && "flex flex-col")}>
            <div className={cn("mx-auto w-full", view === "graph" ? "flex min-h-0 max-w-none flex-1 flex-col" : view === "story" ? "max-w-none" : "max-w-4xl")}>
              {view === "story" ? (
                <Suspense fallback={<Skeleton className="m-6 min-h-[420px]" />}>
                  <StoryView onOpenExplorer={() => setView("candidates")} />
                </Suspense>
              ) : view === "candidates" ? (
                <CandidatesView
                  state={opps} filters={filters} selectedId={selectedId}
                  onOpen={(o) => setSelectedId(o.opportunity_id)} onClearFilters={() => setFilters(EMPTY_FILTERS)}
                />
              ) : view === "papers" ? (
                <PapersView state={search} submitted={submitted != null} notes={submitted?.notes ?? []} onOpenPaper={setPaperId} />
              ) : view === "graph" ? (
                <Suspense fallback={<Skeleton className="min-h-[420px] flex-1" />}>
                  <GraphView paperId={graphId} onPaperId={setGraphId} bridgeIds={bridgeIds} theme={theme} onOpenPaper={setPaperId} />
                </Suspense>
              ) : (
                <LandscapeView state={landscape} onOpenGraph={openGraph} />
              )}
            </div>
          </main>
        </div>

        <footer className="glass shrink-0 rounded-none border-0 border-t px-4 py-2 text-center text-[11px] leading-snug text-muted">
          Evidence-grounded analysis of a curated corpus. Candidate opportunities are potentially underexplored combinations: signals for human review, not proof of a research gap.
        </footer>
      </div>

      {/* right pane: slide-over details */}
      <EvidenceDrawer opportunity={selected} onClose={() => setSelectedId(null)} onOpenGraph={openGraph} />
      <PaperDrawer paperId={paperId} onClose={() => setPaperId(null)} onOpenPaper={setPaperId} onOpenGraph={openGraph} />
    </TooltipProvider>
  );
}

/** The app. The provider gives the centre pane smooth scrolling (Lenis driven by the GSAP ticker; off with reduced motion). */
export default function App() {
  return (
    <SmoothScrollProvider>
      <AppShell />
    </SmoothScrollProvider>
  );
}
