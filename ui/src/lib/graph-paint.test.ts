import { afterEach, describe, expect, it } from "vitest";
import {
  appearProgress, buildAdjacency, capDevicePixelRatio, distancesFromCenter, drawLink, drawNode, easeToward, hashPhase, hexToRgb, highlightSet,
  labelTargets, linkProgress, linkTouches, MAX_DPR, MAX_LABELLED, newPaintState, nodeRadius, particlePositions, rgba, stepLabelAlpha, topDegreeIds,
  type PaintLink, type PaintNode,
} from "@/lib/graph-paint";

const node = (id: string, over: Partial<PaintNode> = {}): PaintNode => ({
  id, label: "Paper", name: "Name " + id, year: 2020, kind: "Paper", color: "#0EA5E9", val: 1, isCenter: false, degree: 0, x: 0, y: 0, ...over,
});

/** A canvas context that only records what is called on it. */
function fakeCtx() {
  const calls: { fn: string; args: unknown[] }[] = [];
  const gradientStops: Array<[number, string]> = [];
  const target: Record<string, unknown> = {};
  const ctx = new Proxy(target, {
    get: (t, p: string) => {
      if (p === "createLinearGradient") return (...a: unknown[]) => (calls.push({ fn: p, args: a }), { addColorStop: (o: number, c: string) => gradientStops.push([o, c]) });
      if (p in t) return t[p];
      return (...args: unknown[]) => void calls.push({ fn: p, args });
    },
    set: (t, p: string, v) => ((t[p] = v), true),
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, calls, gradientStops, count: (fn: string) => calls.filter((c) => c.fn === fn).length };
}

describe("colours", () => {
  it("parses #rrggbb and #rgb, and falls back to a neutral grey for anything else", () => {
    expect(hexToRgb("#3B82F6")).toEqual([59, 130, 246]);
    expect(hexToRgb("#fff")).toEqual([255, 255, 255]);
    expect(hexToRgb("not a colour")).toEqual([148, 163, 184]);
    expect(rgba("#10B981", 0.5)).toBe("rgba(16, 185, 129, 0.5)");
    expect(rgba("#10B981", 7)).toBe("rgba(16, 185, 129, 1)"); // clamped
  });
});

describe("the label rule: only the selected paper, the clicked node, the hovered node and the best-connected nodes", () => {
  const nodes = [
    { id: "c", name: "centre", degree: 2 },
    { id: "a", name: "A", degree: 9 },
    { id: "b", name: "B", degree: 8 },
    { id: "d", name: "D", degree: 7 },
    { id: "e", name: "E", degree: 6 },
    { id: "f", name: "F", degree: 5 },
    { id: "g", name: "G", degree: 4 },
    { id: "h", name: "H", degree: 3 },
    { id: "z", name: "Z", degree: 0 },
  ];

  it("labels the best-connected nodes, at most five, and never an unconnected one", () => {
    expect(MAX_LABELLED).toBe(5);
    expect(topDegreeIds(nodes)).toEqual(["a", "b", "d", "e", "f"]);
    expect(topDegreeIds(nodes, 50)).not.toContain("z");
    expect(topDegreeIds([{ id: "x", name: "x", degree: 3 }, { id: "y", name: "y", degree: 3 }], 1)).toEqual(["x"]); // ties: by name
  });

  it("adds the selected paper, the clicked node and the hovered node, and nothing else", () => {
    const base = labelTargets({ nodes, centerId: null, selectedId: null, hoverId: null });
    expect([...base].sort()).toEqual(["a", "b", "d", "e", "f"]);
    const all = labelTargets({ nodes, centerId: "c", selectedId: "g", hoverId: "z" });
    expect([...all].sort()).toEqual(["a", "b", "c", "d", "e", "f", "g", "z"]);
    expect(all.has("h")).toBe(false); // a node that is none of these has no label, however much of the graph is shown
  });

  it("ignores ids that are not in the graph", () => {
    expect([...labelTargets({ nodes, centerId: "nope", selectedId: "nope2", hoverId: "nope3" })].sort()).toEqual(["a", "b", "d", "e", "f"]);
  });

  it("fades labels in and out instead of switching them", () => {
    const alpha = new Map<string, number>();
    stepLabelAlpha(alpha, ["a", "b"], new Set(["a"]), 0.05);
    expect(alpha.get("a")!).toBeGreaterThan(0);
    expect(alpha.get("a")!).toBeLessThan(1); // on its way in
    for (let i = 0; i < 60; i += 1) stepLabelAlpha(alpha, ["a", "b"], new Set(["a"]), 0.05);
    expect(alpha.get("a")!).toBeGreaterThan(0.99);
    expect(alpha.has("b")).toBe(false); // never labelled
    stepLabelAlpha(alpha, ["a", "b"], new Set(), 0.05); // now it should leave
    expect(alpha.get("a")!).toBeLessThan(0.99);
    expect(alpha.get("a")!).toBeGreaterThan(0.3); // fading, not gone
    for (let i = 0; i < 80; i += 1) stepLabelAlpha(alpha, ["a", "b"], new Set(), 0.05);
    expect(alpha.has("a")).toBe(false); // gone completely
  });

  it("draws a label only for a node that has label opacity, and not for the others", () => {
    const st = newPaintState(false);
    const withLabel = fakeCtx();
    st.labelAlpha.set("n1", 1);
    drawNode(withLabel.ctx, node("n1", { x: 10, y: 10 }), 1, st);
    expect(withLabel.count("fillText")).toBe(1);
    const without = fakeCtx();
    drawNode(without.ctx, node("n2", { x: 10, y: 10 }), 1, st);
    expect(without.count("fillText")).toBe(0);
    const faint = fakeCtx();
    st.labelAlpha.set("n3", 0.01);
    drawNode(faint.ctx, node("n3"), 1, st);
    expect(faint.count("fillText")).toBe(0); // practically invisible: not drawn
  });
});

describe("hover highlighting", () => {
  const links = [{ source: "a", target: "b" }, { source: "a", target: "c" }, { source: "d", target: "e" }];
  const adj = buildAdjacency(links);

  it("lights the hovered node and its neighbours and nothing else", () => {
    expect([...highlightSet(adj, "a")!].sort()).toEqual(["a", "b", "c"]);
    expect([...highlightSet(adj, "b")!].sort()).toEqual(["a", "b"]); // links work both ways
    expect([...highlightSet(adj, "zzz")!]).toEqual(["zzz"]); // a node without links lights only itself
    expect(highlightSet(adj, null)).toBeNull();
  });

  it("knows which links touch the hovered node, also when the ends are node objects", () => {
    expect(linkTouches("a", links[0]!)).toBe(true);
    expect(linkTouches("a", links[2]!)).toBe(false);
    expect(linkTouches(null, links[0]!)).toBe(false);
    expect(linkTouches("b", { source: { id: "a" }, target: { id: "b" } })).toBe(true);
    expect(buildAdjacency([{ source: { id: "x" }, target: { id: "y" } }]).get("x")).toEqual(new Set(["y"]));
  });

  /** the highest globalAlpha the painter sets while drawing a node */
  const peakAlpha = (n: PaintNode, st: ReturnType<typeof newPaintState>) => {
    const f = fakeCtx();
    const seen: number[] = [];
    const ctx = new Proxy(f.ctx as object, { set: (t, p, v) => ((p === "globalAlpha" && seen.push(v as number)), Reflect.set(t, p, v)), get: (t, p) => Reflect.get(t, p) }) as unknown as CanvasRenderingContext2D;
    drawNode(ctx, n, 1, st);
    return Math.max(...seen);
  };

  it("dims what is not lit: the opacity of a node outside the highlight drops, the lit ones stay", () => {
    const st = newPaintState(false);
    st.highlight = highlightSet(adj, "a");
    st.dim = 1;
    expect(peakAlpha(node("b", { x: 1, y: 1 }), st)).toBeGreaterThan(0.85); // a neighbour of the hovered node
    expect(peakAlpha(node("e", { x: 1, y: 1 }), st)).toBeLessThan(0.25); // not connected to it
  });

  it("no hover, no dimming: every node keeps its full opacity", () => {
    const st = newPaintState(false);
    st.dim = 1; // even with the dim amount at 1, there is no highlight set, so nothing is dimmed
    expect(peakAlpha(node("q", { x: 1, y: 1 }), st)).toBeGreaterThan(0.9);
  });

  it("eases values toward a target without overshooting", () => {
    let v = 0;
    for (let i = 0; i < 5; i += 1) {
      const next = easeToward(v, 1, 0.05, 8);
      expect(next).toBeGreaterThan(v);
      expect(next).toBeLessThan(1);
      v = next;
    }
    expect(easeToward(0.5, 0.5, 0.1)).toBe(0.5);
  });
});

describe("the entrance", () => {
  it("shows the nodes nearest the selected paper first and the farthest last", () => {
    for (const reveal of [0.1, 0.3, 0.6]) expect(appearProgress(0, reveal)).toBeGreaterThanOrEqual(appearProgress(0.5, reveal));
    expect(appearProgress(0, 0)).toBe(0);
    expect(appearProgress(1, 0.3)).toBe(0); // the farthest has not started
    expect(appearProgress(0, 0.6)).toBe(1); // the nearest is complete
    expect(appearProgress(1, 1)).toBe(1); // everything is complete at the end
    expect(appearProgress(0.5, 0.5)).toBeGreaterThan(0);
    expect(appearProgress(0.5, 0.5)).toBeLessThan(1);
  });

  it("draws the links in after the nodes have started", () => {
    expect(linkProgress(0)).toBe(0);
    expect(linkProgress(0.25)).toBe(0);
    expect(linkProgress(0.6)).toBeGreaterThan(0);
    expect(linkProgress(1)).toBe(1);
    expect(linkProgress(0.8)).toBeGreaterThan(linkProgress(0.5));
  });

  it("measures the distance from the selected paper, scaled to 0..1", () => {
    const d = distancesFromCenter([node("c", { x: 0, y: 0 }), node("n", { x: 30, y: 40 }), node("m", { x: 3, y: 4 })], "c");
    expect(d.get("c")).toBe(0);
    expect(d.get("n")).toBe(1);
    expect(d.get("m")).toBeCloseTo(0.1, 5);
    expect(distancesFromCenter([node("c")], "missing").size).toBe(0);
  });

  it("moves particles along a link in its direction, evenly spaced, wrapping around", () => {
    expect(particlePositions(2, 0)).toEqual([0, 0.5]);
    const later = particlePositions(2, 1, 0.25);
    expect(later[0]!).toBeCloseTo(0.25, 5);
    expect(later[1]!).toBeCloseTo(0.75, 5);
    expect(particlePositions(2, 4.1, 0.25).every((p) => p >= 0 && p < 1)).toBe(true);
  });

  it("gives each node its own stable drift phase", () => {
    expect(hashPhase("W1")).toBe(hashPhase("W1"));
    expect(hashPhase("W1")).not.toBe(hashPhase("W2"));
    expect(hashPhase("W1")).toBeGreaterThanOrEqual(0);
    expect(hashPhase("W1")).toBeLessThan(Math.PI * 2);
  });
});

describe("node and link painting", () => {
  it("sizes nodes by degree, and the selected paper is larger still", () => {
    expect(nodeRadius({ val: 4, isCenter: false })).toBeGreaterThan(nodeRadius({ val: 1, isCenter: false }));
    expect(nodeRadius({ val: 1, isCenter: true })).toBeGreaterThan(nodeRadius({ val: 1, isCenter: false }));
  });

  it("draws a node as a glowing orb with additive blending", () => {
    const st = newPaintState(false);
    const f = fakeCtx();
    const modes: unknown[] = [];
    const ctx = new Proxy(f.ctx as object, { set: (t, p, v) => ((p === "globalCompositeOperation" && modes.push(v)), Reflect.set(t, p, v)), get: (t, p) => Reflect.get(t, p) }) as unknown as CanvasRenderingContext2D;
    // jsdom has no canvas, so the cached orb sprite is missing and the orb falls back to a plain disc: both paths draw
    drawNode(ctx, node("n", { x: 5, y: 5, degree: 3, val: 3 }), 1, st);
    expect(modes).toContain("lighter");
    expect(f.count("drawImage") + f.count("arc")).toBeGreaterThan(0);
  });

  it("gives the selected paper rings: two that pulse when animation is allowed, one still ring when it is not", () => {
    const animated = newPaintState(true);
    animated.reveal = 1;
    animated.centerId = "c";
    animated.ring = 0.3;
    const a = fakeCtx();
    drawNode(a.ctx, node("c", { x: 0, y: 0, isCenter: true, val: 4 }), 1, animated);
    const still = newPaintState(false);
    still.centerId = "c";
    const s = fakeCtx();
    drawNode(s.ctx, node("c", { x: 0, y: 0, isCenter: true, val: 4 }), 1, still);
    expect(a.count("stroke")).toBe(2);
    expect(s.count("stroke")).toBe(1);
  });

  const a = node("a", { x: 0, y: 0, color: "#3B82F6" });
  const b = node("b", { x: 100, y: 0, color: "#10B981" });

  it("draws a link as a thin gradient from one end's colour to the other's", () => {
    const f = fakeCtx();
    drawLink(f.ctx, { source: a, target: b, type: "WROTE" } as PaintLink, 1, newPaintState(false));
    expect(f.count("createLinearGradient")).toBe(1);
    expect(f.gradientStops[0]![1]).toContain("59, 130, 246");
    expect(f.gradientStops[1]![1]).toContain("16, 185, 129");
    expect(f.count("stroke")).toBe(1);
  });

  it("falls back to a flat line when there are too many links for a gradient each", () => {
    const f = fakeCtx();
    drawLink(f.ctx, { source: a, target: b, type: "WROTE" } as PaintLink, 1, newPaintState(false), false);
    expect(f.count("createLinearGradient")).toBe(0);
    expect(f.count("stroke")).toBe(1);
  });

  it("puts particles on citation links only while animating, and none otherwise or on other links", () => {
    const cites = { source: a, target: b, type: "CITES" } as PaintLink;
    const moving = newPaintState(true);
    moving.reveal = 1;
    const m = fakeCtx();
    drawLink(m.ctx, cites, 1, moving);
    expect(m.count("arc")).toBe(2);
    const staticSt = newPaintState(false);
    const s = fakeCtx();
    drawLink(s.ctx, cites, 1, staticSt);
    expect(s.count("arc")).toBe(0); // reduced motion: no particles
    const other = fakeCtx();
    drawLink(other.ctx, { source: a, target: b, type: "WROTE" } as PaintLink, 1, moving);
    expect(other.count("arc")).toBe(0);
  });

  it("does not draw a link whose ends are not nodes with a position yet", () => {
    const f = fakeCtx();
    drawLink(f.ctx, { source: "a", target: "b", type: "CITES" }, 1, newPaintState(false));
    expect(f.count("stroke")).toBe(0);
  });
});

describe("capDevicePixelRatio", () => {
  const original = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");
  afterEach(() => {
    if (original) Object.defineProperty(window, "devicePixelRatio", original);
  });

  it("reports at most 2 while capped, and puts the real value back", () => {
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, get: () => 3 });
    expect(window.devicePixelRatio).toBe(3);
    const restore = capDevicePixelRatio();
    expect(MAX_DPR).toBe(2);
    expect(window.devicePixelRatio).toBe(2);
    restore();
    expect(window.devicePixelRatio).toBe(3);
  });

  it("leaves a smaller ratio alone", () => {
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, get: () => 1.25 });
    const restore = capDevicePixelRatio();
    expect(window.devicePixelRatio).toBe(1.25);
    restore();
  });

  it("is safe to apply and restore more than once", () => {
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, get: () => 4 });
    const r1 = capDevicePixelRatio();
    const r2 = capDevicePixelRatio();
    expect(window.devicePixelRatio).toBe(2);
    r2();
    r1();
    expect(window.devicePixelRatio).toBe(4);
  });
});

