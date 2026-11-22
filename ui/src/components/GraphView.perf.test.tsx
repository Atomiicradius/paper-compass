import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { PaperGraph } from "@/api/types";
import { gsap } from "@/lib/gsap";
import { setReducedMotion } from "@/test/motion";

// the force-graph library needs a canvas: a stub that records its props, the pixel ratio it saw, and exposes its methods
const fg = vi.hoisted(() => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: null as null | Record<string, any>,
  dprAtRender: null as number | null,
  methods: {} as Record<string, unknown>,
}));
vi.mock("react-force-graph-2d", async () => {
  const React = await import("react");
  const Stub = forwardRef<unknown, Record<string, unknown>>((props, ref) => {
    fg.props = props as never;
    fg.dprAtRender = window.devicePixelRatio; // what the canvas library sees when it is created
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

function graphOf(n: number): PaperGraph {
  return {
    center: "Paper:W0",
    nodes: Array.from({ length: n }, (_, i) => ({ id: `Paper:W${i}`, label: "Paper" as const, name: `Paper ${i}`, year: 2020 })),
    edges: Array.from({ length: n - 1 }, (_, i) => ({ source: "Paper:W0", target: `Paper:W${i + 1}`, type: "CITES" })),
  };
}

/** a recording canvas context */
function fakeCtx() {
  const calls: string[] = [];
  const t: Record<string, unknown> = {};
  const ctx = new Proxy(t, {
    get: (o, p: string) => (p in o ? o[p] : p === "createLinearGradient" ? () => (calls.push(p), { addColorStop() {} }) : () => void calls.push(p)),
    set: (o, p: string, v) => ((o[p] = v), true),
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, count: (fn: string) => calls.filter((c) => c === fn).length };
}

const props = () => fg.props!;
const mount = () =>
  render(
    <TooltipProvider>
      <GraphView paperId="W0" onPaperId={() => {}} bridgeIds={new Set()} theme="dark" onOpenPaper={() => {}} />
    </TooltipProvider>,
  );

/** every non-test source file under src/ */
function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) sources(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) out.push(p);
  }
  return out;
}

describe("GraphView: performance and cleanup", () => {
  let restoreMotion = () => {};
  const defs: Array<() => void> = [];
  const define = (obj: object, key: string, value: unknown) => {
    const had = Object.getOwnPropertyDescriptor(obj, key);
    Object.defineProperty(obj, key, { configurable: true, get: () => value });
    defs.push(() => (had ? Object.defineProperty(obj, key, had) : delete (obj as Record<string, unknown>)[key]));
  };
  beforeEach(() => {
    fg.props = null;
    fg.dprAtRender = null;
    fg.methods = {
      d3Force: () => ({ strength: () => {}, distance: () => {} }),
      d3ReheatSimulation: () => {},
      zoomToFit: () => {},
      refresh: vi.fn(),
      pauseAnimation: vi.fn(),
      resumeAnimation: vi.fn(),
      centerAt: vi.fn(),
      zoom: vi.fn(() => 1),
    };
    define(HTMLElement.prototype, "clientWidth", 900);
    define(HTMLElement.prototype, "clientHeight", 600);
    vi.mocked(api.paperGraph).mockResolvedValue(graphOf(13));
  });
  afterEach(() => {
    restoreMotion();
    defs.splice(0).forEach((f) => f());
  });

  it("caps the device pixel ratio at 2 while the graph is mounted and gives the real value back on unmount", async () => {
    define(window, "devicePixelRatio", 3);
    restoreMotion = setReducedMotion(false);
    const r = mount();
    await waitFor(() => expect(fg.props).not.toBeNull());
    expect(fg.dprAtRender).toBe(2); // the canvas library was created under the cap
    expect(window.devicePixelRatio).toBe(2);
    r.unmount();
    expect(window.devicePixelRatio).toBe(3);
  });

  it("pauses the layout, the loops and the entrance while the tab is hidden, and resumes them when it is shown again", async () => {
    restoreMotion = setReducedMotion(false);
    mount();
    await waitFor(() => expect(fg.props).not.toBeNull());
    type Handle = { pause: ReturnType<typeof vi.fn>; resume: ReturnType<typeof vi.fn> };
    // the graph's own tweens: the entrance timeline, and the two endless loops (the clock and the rings; other components also tween)
    const loops = vi.mocked(gsap.to).mock.calls.map((c, i) => ({ vars: c[1] as Record<string, unknown>, h: vi.mocked(gsap.to).mock.results[i]!.value as Handle })).filter((x) => "time" in x.vars || "ring" in x.vars);
    const handles = [...vi.mocked(gsap.timeline).mock.results.map((x) => x.value as Handle), ...loops.map((x) => x.h)];
    expect(handles).toHaveLength(3); // the entrance, the clock, the rings
    define(document, "hidden", true);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(fg.methods.pauseAnimation).toHaveBeenCalledTimes(1);
    for (const h of handles) expect(h.pause).toHaveBeenCalledTimes(1);
    define(document, "hidden", false);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(fg.methods.resumeAnimation).toHaveBeenCalledTimes(1);
    for (const h of handles) expect(h.resume).toHaveBeenCalledTimes(1);
  });

  it("removes its listener, reverts its tweens and restores the pixel ratio on unmount", async () => {
    define(window, "devicePixelRatio", 3);
    restoreMotion = setReducedMotion(false);
    const remove = vi.spyOn(document, "removeEventListener");
    const r = mount();
    await waitFor(() => expect(fg.props).not.toBeNull());
    const ctxs = vi.mocked(gsap.context).mock.results.map((x) => x.value as { revert: ReturnType<typeof vi.fn> });
    expect(ctxs.length).toBeGreaterThan(0);
    r.unmount();
    expect(remove).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
    for (const c of ctxs) expect(c.revert).toHaveBeenCalled();
    expect(window.devicePixelRatio).toBe(3);
    // nothing is listening any more
    define(document, "hidden", true);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(fg.methods.pauseAnimation).not.toHaveBeenCalled();
  });

  it("still asks the API for as many nodes as the slider says", async () => {
    restoreMotion = setReducedMotion(true);
    mount();
    await waitFor(() => expect(fg.props).not.toBeNull());
    fireEvent.change(screen.getByLabelText("Maximum nodes"), { target: { value: "400" } });
    await waitFor(() => expect(vi.mocked(api.paperGraph).mock.calls.at(-1)![1]).toBe(400));
    expect(vi.mocked(api.paperGraph).mock.calls.at(-1)![0]).toBe("W0");
  });

  it("leaves out the particles and the per-link gradients on a large graph", async () => {
    restoreMotion = setReducedMotion(false);
    vi.mocked(api.paperGraph).mockResolvedValue(graphOf(460));
    mount();
    await waitFor(() => expect((props().graphData as { nodes: unknown[] } | undefined)?.nodes.length).toBe(460));
    const drawFirstLink = () => {
      const nodes: Array<Record<string, unknown>> = (props().graphData as { nodes: Array<Record<string, unknown>> }).nodes.map((n, i) => ({ ...n, x: 10 * i, y: 5 * i }));
      const byId = new Map(nodes.map((n) => [n.id as string, n]));
      const link = (props().graphData as { links: Array<Record<string, unknown>> }).links[0]!;
      const f = fakeCtx();
      (props().onRenderFramePre as () => void)();
      // the entrance is a GSAP tween (stubbed here), so ask for the finished state
      (props().linkCanvasObject as (l: unknown, c: unknown, s: number) => void)({ ...link, source: byId.get(link.source as string), target: byId.get(link.target as string) }, f.ctx, 1);
      return f;
    };
    const large = drawFirstLink();
    expect(large.count("createLinearGradient")).toBe(0); // one flat colour per link
    expect(large.count("arc")).toBe(0); // no particles
  });

  it("keeps the graph code in its own chunk: App loads it lazily and only GraphView and its motion hook import the painters", () => {
    const root = join(process.cwd(), "src");
    const app = readFileSync(join(root, "App.tsx"), "utf-8");
    expect(app).toMatch(/lazy\(\(\) => import\("@\/components\/GraphView"\)/);
    expect(app).not.toMatch(/from "@\/components\/GraphView"/);
    const importers = (needle: string) =>
      sources(root)
        .filter((f) => readFileSync(f, "utf-8").includes(needle))
        .map((f) => f.replace(root, "").replace(/\\/g, "/"))
        .sort();
    expect(importers('from "@/lib/graph-paint"')).toEqual(["/components/GraphView.tsx", "/components/useGraphMotion.ts"]);
    expect(importers('from "@/components/useGraphMotion"')).toEqual(["/components/GraphView.tsx"]);
    expect(importers('from "react-force-graph-2d"')).toEqual(["/components/GraphView.tsx", "/components/useGraphMotion.ts"]); // the latter only for a type
  });
});
