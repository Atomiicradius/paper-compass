import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import type { PaperGraph } from "@/api/types";
import { gsap } from "@/lib/gsap";
import { setReducedMotion } from "@/test/motion";

// ---- the force-graph library needs a canvas: replace it with a stub that records its props and exposes the methods
const fg = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: null as null | Record<string, any>,
  methods: {
    d3Force: () => ({ strength: () => {}, distance: () => {} }),
    d3ReheatSimulation: () => {},
    zoomToFit: () => {},
    refresh: () => {},
    pauseAnimation: () => {},
    resumeAnimation: () => {},
    centerAt: () => {},
    zoom: () => 1,
  } as Record<string, unknown>,
}));
vi.mock("react-force-graph-2d", async () => {
  const React = await import("react");
  const Stub = forwardRef<unknown, Record<string, unknown>>((props, ref) => {
    fg.props = props as never;
    useImperativeHandle(ref, () => fg.methods as never, []);
    return React.createElement("div", { "data-testid": "force-graph-stub" });
  });
  return { default: Stub };
});
vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, paperGraph: vi.fn(), paper: vi.fn() } };
});
import { api } from "@/api/client";
import { GraphView } from "@/components/GraphView";
import { TooltipProvider } from "@/components/ui/primitives";

/** a centre paper with 8 cited papers; W1 is cited by many of the others, so it is the best-connected */
function makeGraph(): PaperGraph {
  const paper = (n: number) => ({ id: `Paper:W${n}`, label: "Paper" as const, name: `Paper number ${n}`, year: 2020 + (n % 5) });
  const nodes = [paper(0), ...Array.from({ length: 12 }, (_, i) => paper(i + 1))];
  const edges = Array.from({ length: 12 }, (_, i) => ({ source: "Paper:W0", target: `Paper:W${i + 1}`, type: "CITES" }));
  for (const k of [2, 3, 4, 5, 6]) edges.push({ source: `Paper:W${k}`, target: "Paper:W1", type: "CITES" });
  for (const k of [3, 4, 5]) edges.push({ source: `Paper:W${k}`, target: "Paper:W2", type: "CITES" });
  for (const k of [4, 5]) edges.push({ source: `Paper:W${k}`, target: "Paper:W3", type: "CITES" });
  edges.push({ source: "Paper:W5", target: "Paper:W4", type: "CITES" });
  return { center: "Paper:W0", nodes, edges, truncated: false, neighbors_total: 12 };
}

/** a recording canvas context */
function fakeCtx() {
  const calls: string[] = [];
  const alphas: number[] = [];
  const t: Record<string, unknown> = {};
  const ctx = new Proxy(t, {
    get: (o, p: string) => (p in o ? o[p] : (p === "createLinearGradient" ? () => ({ addColorStop() {} }) : () => void calls.push(p))),
    set: (o, p: string, v) => ((p === "globalAlpha" && alphas.push(v as number)), (o[p] = v), true),
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, calls, alphas, count: (fn: string) => calls.filter((c) => c === fn).length };
}

const props = () => fg.props!;
type N = Record<string, unknown> & { id: string; name: string; x: number; y: number };
const graphNodes = () => (props().graphData as { nodes: Array<Record<string, unknown>> }).nodes;
const withXY = (n: Record<string, unknown>, i: number): N => ({ ...n, id: n.id as string, name: n.name as string, x: 10 * i, y: 5 * i });

async function show(opts: { reduced: boolean }) {
  const restore = setReducedMotion(opts.reduced);
  vi.mocked(api.paperGraph).mockResolvedValue(makeGraph());
  const view = render(
    <TooltipProvider>
      <GraphView paperId="W0" onPaperId={() => {}} bridgeIds={new Set()} theme="dark" onOpenPaper={() => {}} />
    </TooltipProvider>,
  );
  await waitFor(() => expect(fg.props).not.toBeNull());
  if (!opts.reduced) await waitFor(() => expect(gsap.timeline).toHaveBeenCalled()); // the entrance is started by an effect, a moment after the first render
  return { restore, ...view };
}

describe("GraphView: motion", () => {
  let restore = () => {};
  const defs: Array<() => void> = [];
  const define = (obj: object, key: string, value: unknown) => {
    const had = Object.getOwnPropertyDescriptor(obj, key);
    Object.defineProperty(obj, key, { configurable: true, get: () => value });
    defs.push(() => (had ? Object.defineProperty(obj, key, had) : delete (obj as Record<string, unknown>)[key]));
  };
  beforeEach(() => {
    fg.props = null;
    for (const k of Object.keys(fg.methods)) if (typeof fg.methods[k] !== "function") continue;
    fg.methods.centerAt = vi.fn();
    fg.methods.zoom = vi.fn(() => 1);
    fg.methods.refresh = vi.fn();
    fg.methods.pauseAnimation = vi.fn();
    fg.methods.resumeAnimation = vi.fn();
    define(HTMLElement.prototype, "clientWidth", 900);
    define(HTMLElement.prototype, "clientHeight", 600);
  });
  afterEach(() => {
    restore();
    defs.splice(0).forEach((f) => f());
  });

  it("plays an entrance timeline and the idle loops, keeps drawing every frame, and lets particles show direction instead of arrows", async () => {
    const r = await show({ reduced: false });
    restore = r.restore;
    expect(gsap.context).toHaveBeenCalled();
    expect(gsap.timeline).toHaveBeenCalledTimes(1); // the entrance
    const tweens = vi.mocked(gsap.to).mock.calls.map((c) => c[1] as Record<string, unknown>);
    expect(tweens.some((v) => v.repeat === -1 && "ring" in v)).toBe(true); // the slow rings
    expect(tweens.some((v) => "time" in v)).toBe(true); // the clock of the drift and the particles
    expect(props().autoPauseRedraw).toBe(false); // the canvas keeps redrawing: things move
    expect(props().linkDirectionalArrowLength).toBe(0); // the particles show the direction
    expect(props().linkCanvasObjectMode && (props().linkCanvasObjectMode as () => string)()).toBe("replace");
    expect(screen.getByTestId("graph-canvas")).toHaveAttribute("data-lenis-prevent");
  });

  it("under reduced motion: no timeline, no tween, a static canvas, arrows instead of particles", async () => {
    const r = await show({ reduced: true });
    restore = r.restore;
    expect(gsap.timeline).not.toHaveBeenCalled();
    expect(gsap.to).not.toHaveBeenCalled();
    expect(gsap.context).not.toHaveBeenCalled();
    expect(props().autoPauseRedraw).toBe(true); // redraw only when something changes
    expect(props().linkDirectionalArrowLength).toBe(3);
    expect(screen.getByTestId("graph-canvas")).toHaveAttribute("data-lenis-prevent"); // still its own scroll/zoom area
    // everything is already fully drawn (no entrance): the first link is complete and nodes are at full size
    const f = fakeCtx();
    const link = (props().graphData as { links: Array<Record<string, unknown>> }).links[0]!;
    const nodes = graphNodes().map(withXY);
    const byId = new Map(nodes.map((n) => [n.id as string, n]));
    (props().linkCanvasObject as (l: unknown, c: unknown, s: number) => void)({ ...link, source: byId.get(link.source as string), target: byId.get(link.target as string) }, f.ctx, 1);
    expect(f.count("stroke")).toBe(1);
    expect(f.count("arc")).toBe(0); // no particles
  });

  it("labels only the selected paper and the best-connected nodes, never the rest", async () => {
    const r = await show({ reduced: true });
    restore = r.restore;
    (props().onRenderFramePre as () => void)(); // reduced motion: labels reach their state in one step
    const nodes = graphNodes().map(withXY);
    const labelled = nodes.filter((n) => {
      const f = fakeCtx();
      (props().nodeCanvasObject as (n: unknown, c: unknown, s: number) => void)(n, f.ctx, 3); // zoomed in: still no extra labels
      return f.count("fillText") > 0;
    });
    const names = labelled.map((n) => n.name);
    expect(names).toContain("Paper number 0"); // the selected paper (the centre)
    expect(names).toContain("Paper number 1"); // the best-connected
    expect(labelled.length).toBeLessThanOrEqual(6); // the centre plus at most five
    expect(labelled.length).toBeLessThan(nodes.length);
  });

  it("on hover keeps the node and its neighbours lit and dims everything else; leaving restores it", async () => {
    const r = await show({ reduced: true });
    restore = r.restore;
    const nodes = graphNodes().map(withXY);
    const peak = (id: string) => {
      const f = fakeCtx();
      (props().nodeCanvasObject as (n: unknown, c: unknown, s: number) => void)(nodes.find((n) => n.id === id), f.ctx, 1);
      return Math.max(...f.alphas);
    };
    const before = peak("Paper:W12");
    act(() => (props().onNodeHover as (n: unknown) => void)(nodes.find((n) => n.id === "Paper:W2")));
    (props().onRenderFramePre as () => void)();
    expect(peak("Paper:W2")).toBeGreaterThan(0.85); // the hovered node
    expect(peak("Paper:W1")).toBeGreaterThan(0.85); // a neighbour (W2 cites W1)
    expect(peak("Paper:W12")).toBeLessThan(0.25); // not connected to W2: dimmed
    expect(screen.getByTestId("graph-canvas").style.cursor).toBe("pointer");
    act(() => (props().onNodeHover as (n: unknown) => void)(null));
    (props().onRenderFramePre as () => void)();
    expect(peak("Paper:W12")).toBeCloseTo(before, 5);
    expect(screen.getByTestId("graph-canvas").style.cursor).toBe("");
  });

  it("on click glides the camera to the node (eased) and opens the node card", async () => {
    const r = await show({ reduced: false });
    restore = r.restore;
    vi.mocked(api.paper).mockRejectedValue(new Error("not needed"));
    const node = withXY(graphNodes().find((n) => n.id === "Paper:W3")!, 4);
    act(() => (props().onNodeClick as (n: unknown) => void)(node));
    expect(fg.methods.centerAt).toHaveBeenCalledWith(node.x, node.y, 800);
    expect(fg.methods.zoom).toHaveBeenCalledWith(2.2, 800); // never zooms out, and eased over the same time
    expect(await screen.findByRole("region", { name: "Node details" })).toBeInTheDocument();
  });

  it("with reduced motion the click moves the camera at once", async () => {
    const r = await show({ reduced: true });
    restore = r.restore;
    vi.mocked(api.paper).mockRejectedValue(new Error("not needed"));
    const node = withXY(graphNodes().find((n) => n.id === "Paper:W3")!, 4);
    act(() => (props().onNodeClick as (n: unknown) => void)(node));
    expect(fg.methods.centerAt).toHaveBeenCalledWith(node.x, node.y, 0);
    expect(await screen.findByRole("region", { name: "Node details" })).toBeInTheDocument();
  });

  it("reverts everything it started when the graph is removed", async () => {
    const r = await show({ reduced: false });
    restore = r.restore;
    const ctxs = vi.mocked(gsap.context).mock.results.map((x) => x.value as { revert: ReturnType<typeof vi.fn> });
    expect(ctxs.length).toBeGreaterThan(0);
    r.unmount();
    for (const c of ctxs) expect(c.revert).toHaveBeenCalled();
  });
});
