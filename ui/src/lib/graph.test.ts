import { describe, expect, it } from "vitest";
import type { PaperGraph } from "@/api/types";
import { buildViewGraph } from "./graph";
import { GRAPH_COLORS, KIND_COLORS } from "./colors";

const g: PaperGraph = {
  center: "Paper:W1",
  nodes: [
    { id: "Paper:W1", label: "Paper", name: "Center", year: 2020 },
    { id: "Paper:W2", label: "Paper", name: "Neighbour", year: 2021 },
    { id: "Method:3", label: "Method", name: "Back-translation", year: null },
    { id: "Task:1", label: "Task", name: "Machine Translation", year: null },
    { id: "Author:A1", label: "Author", name: "Ada", year: null },
  ],
  edges: [
    { source: "Paper:W1", target: "Method:3", type: "USES_METHOD" },
    { source: "Paper:W1", target: "Task:1", type: "SOLVES" },
    { source: "Paper:W2", target: "Paper:W1", type: "CITES" },
    { source: "Author:A1", target: "Paper:W1", type: "WROTE" },
    { source: "Paper:W1", target: "Method:3", type: "USES_METHOD" }, // duplicate
    { source: "Paper:W1", target: "Ghost:9", type: "CITES" }, // dangling
  ],
};

describe("buildViewGraph", () => {
  it("keeps all nodes, drops duplicate and dangling links, counts per label", () => {
    const v = buildViewGraph(g, new Set(), new Set());
    expect(v.nodes).toHaveLength(5);
    expect(v.links).toHaveLength(4);
    expect(v.counts).toEqual({ Paper: 2, Method: 1, Task: 1, Author: 1 });
  });

  it("uses the semantic colours for method, task and bridge", () => {
    const v = buildViewGraph(g, new Set(), new Set(["W2"]));
    const byId = Object.fromEntries(v.nodes.map((n) => [n.id, n]));
    expect(byId["Method:3"]?.color).toBe(KIND_COLORS.method);
    expect(byId["Task:1"]?.color).toBe(KIND_COLORS.task);
    expect(byId["Paper:W2"]?.kind).toBe("Bridge");
    expect(byId["Paper:W2"]?.color).toBe(GRAPH_COLORS.Bridge);
    expect(byId["Paper:W1"]?.kind).toBe("Paper");
    expect(v.counts).toMatchObject({ Paper: 1, Bridge: 1 });
  });

  it("hiding a label removes its nodes and their links, never the centre, never leaves dangling links", () => {
    const v = buildViewGraph(g, new Set(["Method", "Author"]), new Set());
    expect(v.nodes.map((n) => n.id).sort()).toEqual(["Paper:W1", "Paper:W2", "Task:1"]);
    expect(v.links.every((l) => v.nodes.some((n) => n.id === l.source) && v.nodes.some((n) => n.id === l.target))).toBe(true);
    expect(v.links).toHaveLength(2);
    // even hiding "Paper" keeps the centre paper
    const p = buildViewGraph(g, new Set(["Paper"]), new Set());
    expect(p.nodes.some((n) => n.id === "Paper:W1" && n.isCenter)).toBe(true);
    expect(p.nodes.some((n) => n.id === "Paper:W2")).toBe(false);
  });

  it("sizes nodes by degree and gives the centre extra size", () => {
    const v = buildViewGraph(g, new Set(), new Set());
    const c = v.nodes.find((n) => n.isCenter)!;
    const leaf = v.nodes.find((n) => n.id === "Author:A1")!;
    expect(c.degree).toBe(4);
    expect(leaf.degree).toBe(1);
    expect(c.val).toBeGreaterThan(leaf.val);
  });

  it("handles an empty graph and a 1,500-node graph quickly", () => {
    expect(buildViewGraph({ center: "Paper:W1", nodes: [], edges: [] }, new Set(), new Set())).toEqual({ nodes: [], links: [], counts: {} });
    const big: PaperGraph = {
      center: "Paper:W0",
      nodes: Array.from({ length: 1500 }, (_, i) => ({ id: "Paper:W" + i, label: "Paper" as const, name: "p" + i, year: 2000 + (i % 25) })),
      edges: Array.from({ length: 4000 }, (_, i) => ({ source: "Paper:W" + (i % 1500), target: "Paper:W" + ((i * 7 + 1) % 1500), type: "CITES" })),
    };
    const t = performance.now();
    const v = buildViewGraph(big, new Set(), new Set(["W5"]));
    expect(performance.now() - t).toBeLessThan(500);
    expect(v.nodes).toHaveLength(1500);
  });
});
