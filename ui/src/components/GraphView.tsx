import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { AnimatePresence, motion } from "motion/react";
import { Crosshair, Maximize, X } from "lucide-react";
import { api } from "@/api/client";
import type { GraphLabel } from "@/api/types";
import { GRAPH_COLORS } from "@/lib/colors";
import { buildViewGraph, graphNote, type ViewNode } from "@/lib/graph";
import { capDevicePixelRatio, drawLink, drawNode, nodeRadius, type PaintLink, type PaintNode } from "@/lib/graph-paint";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";
import { useAsync, useElementSize, type Theme } from "@/lib/hooks";
import { nodePaperId, normalizePaperId } from "@/lib/ids";
import { cn } from "@/lib/utils";
import { Badge, Button, ErrorNote, IdBadge, Mono, Skeleton, TagBadge, Tip } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { useGraphMotion } from "@/components/useGraphMotion";

type Kind = GraphLabel | "Bridge";
const LEGEND_ORDER: Kind[] = ["Paper", "Bridge", "Method", "Task", "Dataset", "Setting", "Author", "Venue", "Topic", "Institution"];
const EXAMPLE_ID = "W3028876793";

// the graph is drawn on a dark glass surface in both themes (the glowing orbs need a dark ground)
const GLASS_BACKGROUND = {
  backgroundColor: "rgba(5, 8, 16, 0.8)",
  backgroundImage:
    "radial-gradient(ellipse 62% 52% at 50% 47%, rgba(56, 189, 248, 0.14), transparent 70%), radial-gradient(ellipse 38% 38% at 88% 92%, rgba(139, 92, 246, 0.08), transparent 70%)",
} as const;
const LINK_ARROW_COLOR = "rgba(148, 163, 184, 0.55)";
// links drawn with a gradient each (one gradient object per link per frame) only while there are not too many
const GRADIENT_LINKS_MAX = 450;
// above this many nodes the particles along citation links are left out (the links still draw)
const LARGE_GRAPH = 400;

/**
 * The canvas is never sharper than 2 device pixels per css pixel. force-graph reads window.devicePixelRatio itself and has
 * no option for it, so the property is capped while the graph is mounted. This runs before the canvas is created
 * (children are created after the parent's render), and is undone when the graph unmounts.
 */
function useCappedPixelRatio() {
  const restore = useRef<(() => void) | null>(null);
  if (restore.current === null) restore.current = capDevicePixelRatio();
  useEffect(() => {
    if (restore.current === null) restore.current = capDevicePixelRatio(); // React re-runs effects after a simulated unmount in development
    return () => {
      restore.current?.();
      restore.current = null;
    };
  }, []);
}

export function GraphView({
  paperId, onPaperId, bridgeIds, theme, onOpenPaper, filterButton, filterChips,
}: {
  paperId: string; onPaperId: (id: string) => void; bridgeIds: ReadonlySet<string>; theme: Theme; onOpenPaper: (id: string) => void;
  /** the Filters button (in the header's actions) and the active filter chips (under the title) */
  filterButton?: ReactNode;
  filterChips?: ReactNode;
}) {
  const [draft, setDraft] = useState(paperId);
  const [limit, setLimit] = useState(200);
  const [hidden, setHidden] = useState<Set<Kind>>(new Set());
  const [selected, setSelected] = useState<ViewNode | null>(null);

  // a different paper: show its id in the field and drop the selected node (state adjusted during render, no effect)
  const [shownPaperId, setShownPaperId] = useState(paperId);
  if (paperId !== shownPaperId) {
    setShownPaperId(paperId);
    setDraft(paperId);
    setSelected(null);
  }

  const id = normalizePaperId(paperId);
  const graph = useAsync((s) => api.paperGraph(id, limit, s), [id, limit], id !== "");
  const view = useMemo(() => (graph.data ? buildViewGraph(graph.data, hidden, bridgeIds) : null), [graph.data, hidden, bridgeIds]);

  const [sizeRef, size] = useElementSize<HTMLDivElement>();
  const boxRef = useRef<HTMLDivElement | null>(null); // the same element, for the pointer cursor
  const setBox = useCallback((el: HTMLDivElement | null) => {
    boxRef.current = el;
    sizeRef(el);
  }, [sizeRef]);
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const fit = useCallback(() => fgRef.current?.zoomToFit(400, 40), []);

  useCappedPixelRatio();
  const reduced = usePrefersReducedMotion();
  const centerId = useMemo(() => view?.nodes.find((n) => n.isCenter)?.id ?? null, [view]);
  // the entrance, the idle motion, hover highlighting, label fades and the camera glide (see useGraphMotion)
  const { paint, onRenderFramePre, onNodeHover, glideTo } = useGraphMotion({
    view, dataKey: graph.data, centerId, selectedId: selected?.id ?? null, fgRef, boxRef, reduced, large: (view?.nodes.length ?? 0) > LARGE_GRAPH,
  });

  // spread the layout out so labels and nodes do not pile up
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !view) return;
    fg.d3Force("charge")?.strength(-180);
    fg.d3Force("link")?.distance(70);
    fg.d3ReheatSimulation();
  }, [view?.nodes.length, view?.links.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const note = graphNote(graph.data ?? undefined, limit);
  const nodeCount = view?.nodes.length ?? 0;
  const big = nodeCount > 400;
  const legend = LEGEND_ORDER.filter((k) => (view?.counts[k] ?? 0) > 0);

  const paintNode = useCallback((node: object, ctx: CanvasRenderingContext2D, scale: number) => drawNode(ctx, node as PaintNode, scale, paint.current), [paint]);
  const paintLink = useCallback(
    (link: object, ctx: CanvasRenderingContext2D, scale: number) => drawLink(ctx, link as PaintLink, scale, paint.current, nodeCount <= GRADIENT_LINKS_MAX),
    [nodeCount, paint],
  );

  const paintPointer = useCallback((node: object, color: string, ctx: CanvasRenderingContext2D) => {
    const n = node as ViewNode & { x: number; y: number };
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(n.x, n.y, nodeRadius(n) * 1.6 + 2, 0, 2 * Math.PI);
    ctx.fill();
  }, []);

  return (
    <section aria-label="Research graph" className="flex min-h-0 flex-1 flex-col gap-3">
      <PageHeader
        title={<>Research <span className="accent-word">graph</span></>}
        description="The neighbourhood of one paper in the Neo4j projection: authors, venue, extracted elements and citations."
        actions={
          <>
            {filterButton}
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => { e.preventDefault(); onPaperId(normalizePaperId(draft)); }}
            >
              <label htmlFor="graph-id" className="sr-only">Center paper id</label>
              <input
                id="graph-id" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Paper id, e.g. W3028876793"
                className="h-9 w-64 rounded-lg border border-border bg-background px-3 font-mono text-sm outline-none focus-visible:border-primary"
              />
              <Button type="submit" disabled={!normalizePaperId(draft)}>Show</Button>
            </form>
          </>
        }
      >
        {filterChips}
      </PageHeader>

      {id === "" ? (
        <div className="grid min-h-64 flex-1 place-items-center rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted">
          <div className="space-y-3">
            <p className="text-base font-medium text-foreground">Pick a paper to explore its neighbourhood</p>
            <p>Open a paper from Search or from an evidence card, or enter an OpenAlex id. Pasting a graph id such as <Mono>Paper:W123</Mono> works too.</p>
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="outline" size="sm" onClick={() => onPaperId(EXAMPLE_ID)}>Try {EXAMPLE_ID}</Button>
              {[...bridgeIds].slice(0, 3).map((b) => <Button key={b} variant="outline" size="sm" onClick={() => onPaperId(b)}><TagBadge kind="bridge" className="px-1" /> {b}</Button>)}
            </div>
          </div>
        </div>
      ) : graph.error ? (
        <ErrorNote title="Could not load the graph" message={graph.error.message.replace(/^\d+: /, "")} action={<Button variant="outline" size="sm" onClick={graph.reload}>Try again</Button>} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ul className="flex flex-wrap gap-1.5 p-0" aria-label="Node types">
              {legend.map((k) => {
                const off = hidden.has(k);
                return (
                  <li key={k} className="list-none">
                    <button
                      type="button" aria-pressed={!off} title={off ? "Show " + k : "Hide " + k}
                      onClick={() => setHidden((h) => { const next = new Set(h); if (next.has(k)) next.delete(k); else next.add(k); return next; })}
                      className={cn("inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-2 py-0.5 text-xs transition-opacity", off && "opacity-40")}
                    >
                      <span className="size-2.5 rounded-full" style={{ background: GRAPH_COLORS[k] }} aria-hidden />
                      {k} <Mono className="text-muted">{view?.counts[k] ?? 0}</Mono>
                    </button>
                  </li>
                );
              })}
            </ul>
            <label className="ml-auto flex items-center gap-2 text-xs text-muted">
              Max nodes <Mono className="w-9 text-right text-foreground">{limit}</Mono>
              <input type="range" min={20} max={1000} step={20} value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="Maximum nodes" className="w-32 cursor-pointer accent-[var(--primary)]" />
            </label>
            <Tip content="Fit the graph to the view"><Button variant="outline" size="icon" aria-label="Fit graph" onClick={fit}><Maximize className="size-4" /></Button></Tip>
            <span className="text-xs text-muted" aria-live="polite">{view ? <><Mono className="text-foreground">{nodeCount}</Mono> nodes · <Mono className="text-foreground">{view.links.length}</Mono> edges</> : ""}</span>
          </div>

          {note ? <p role="note" className="rounded-lg border border-border bg-hover px-3 py-1.5 text-xs text-muted">{note}</p> : null}

          <div ref={setBox} data-lenis-prevent data-theme={theme} style={GLASS_BACKGROUND} className="glass relative min-h-[420px] flex-1 overflow-hidden rounded-2xl" data-testid="graph-canvas">
            {graph.loading && !view ? <Skeleton className="absolute inset-0 rounded-none" /> : null}
            {view && size.width > 0 ? (
              <ForceGraph2D
                ref={fgRef}
                width={size.width}
                height={size.height}
                graphData={{ nodes: view.nodes, links: view.links }}
                backgroundColor="rgba(0,0,0,0)"
                nodeId="id"
                nodeLabel={(n) => { const x = n as ViewNode; return `${x.kind}: ${x.name}${x.year ? " (" + x.year + ")" : ""}`; }}
                nodeCanvasObject={paintNode}
                linkCanvasObject={paintLink}
                linkCanvasObjectMode={() => "replace"}
                nodePointerAreaPaint={paintPointer}
                linkColor={() => LINK_ARROW_COLOR}
                linkDirectionalArrowLength={big || !reduced ? 0 : 3}
                linkDirectionalArrowRelPos={1}
                cooldownTicks={big ? 60 : 120}
                d3AlphaDecay={big ? 0.06 : 0.03}
                onEngineStop={() => { if (nodeCount > 0 && !selected) fit(); }}
                onNodeClick={(n) => {
                  setSelected(n as ViewNode);
                  glideTo(n);
                }}
                onNodeHover={onNodeHover}
                onRenderFramePre={onRenderFramePre}
                autoPauseRedraw={reduced}
                onBackgroundClick={() => setSelected(null)}
              />
            ) : null}
            {view && view.nodes.length === 0 ? <p className="absolute inset-0 grid place-items-center text-sm text-muted">No nodes to show.</p> : null}

            <AnimatePresence>
              {selected ? <NodeOverlay key={selected.id} node={selected} onClose={() => setSelected(null)} onCenter={(pid) => onPaperId(pid)} onOpenPaper={onOpenPaper} /> : null}
            </AnimatePresence>
          </div>
        </>
      )}
    </section>
  );
}

function NodeOverlay({
  node, onClose, onCenter, onOpenPaper,
}: {
  node: ViewNode; onClose: () => void; onCenter: (id: string) => void; onOpenPaper: (id: string) => void;
}) {
  const isPaper = node.label === "Paper";
  const pid = isPaper ? nodePaperId(node.id) : null;
  const paper = useAsync((s) => api.paper(pid as string, s), [pid], pid != null);
  const kindTag = node.kind === "Method" ? "method" : node.kind === "Task" ? "task" : node.kind === "Dataset" ? "dataset" : node.kind === "Setting" ? "setting" : node.kind === "Bridge" ? "bridge" : null;
  return (
    <motion.div
      role="region"
      data-lenis-prevent
      initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }}
      transition={{ type: "spring", damping: 25, stiffness: 180 }}
      className="absolute top-3 right-3 z-10 max-h-[calc(100%-1.5rem)] w-80 max-w-[calc(100%-1.5rem)] glass overflow-y-auto rounded-xl bg-card/90 p-4 scroll-thin"
      aria-label="Node details"
    >
      <button type="button" aria-label="Close details" onClick={onClose} className="absolute top-2 right-2 cursor-pointer rounded p-1 text-muted hover:bg-hover hover:text-foreground"><X className="size-4" /></button>
      <div className="mb-2 flex items-center gap-2">
        {kindTag ? <TagBadge kind={kindTag} /> : <Badge className="border-border bg-hover">{node.kind}</Badge>}
        {node.year ? <Mono className="text-xs text-muted">{node.year}</Mono> : null}
      </div>
      <h3 className="pr-6 text-sm leading-snug font-semibold">{node.name}</h3>
      <div className="mt-1"><IdBadge id={node.id} /></div>
      <p className="mt-2 text-xs text-muted"><Mono className="text-foreground">{node.degree}</Mono> connections in this view</p>

      {isPaper ? (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          {paper.loading ? <Skeleton className="h-16" /> : paper.error ? (
            <p className="text-xs text-muted">{paper.error.message.replace(/^\d+: /, "")}</p>
          ) : paper.data ? (
            <>
              <p className="text-xs text-muted">{paper.data.venue ?? "venue unknown"}{paper.data.authors.length ? " · " + paper.data.authors.slice(0, 3).join(", ") + (paper.data.authors.length > 3 ? " et al." : "") : ""}</p>
              <div className="flex flex-wrap gap-1">
                {paper.data.methods.map((m) => <TagBadge key={"m" + m} kind="method">{m}</TagBadge>)}
                {paper.data.tasks.map((m) => <TagBadge key={"t" + m} kind="task">{m}</TagBadge>)}
                {paper.data.datasets.map((m) => <TagBadge key={"d" + m} kind="dataset">{m}</TagBadge>)}
              </div>
            </>
          ) : null}
          <div className="flex gap-2 pt-1">
            <Button size="sm" variant="outline" onClick={() => pid && onCenter(pid)}><Crosshair className="size-3.5" /> Re-center</Button>
            <Button size="sm" onClick={() => pid && onOpenPaper(pid)}>Details</Button>
          </div>
        </div>
      ) : null}
    </motion.div>
  );
}
