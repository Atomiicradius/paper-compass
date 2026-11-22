import type { GraphLabel, PaperGraph } from "@/api/types";
import { GRAPH_COLORS } from "@/lib/colors";
import { nodePaperId } from "@/lib/ids";

export interface ViewNode {
  id: string;
  label: GraphLabel;
  name: string;
  year: number | null;
  /** "Bridge" for paper nodes that bridge clusters or opportunities, else the node's own label */
  kind: GraphLabel | "Bridge";
  color: string;
  /** node size (degree based) */
  val: number;
  isCenter: boolean;
  degree: number;
}

export interface ViewLink { source: string; target: string; type: string }

export interface ViewGraph {
  nodes: ViewNode[];
  links: ViewLink[];
  /** node count per label in the whole response (before hiding), for the legend */
  counts: Partial<Record<GraphLabel | "Bridge", number>>;
}

/**
 * Turn the API graph into what the canvas draws.
 * - nodes whose label is in `hidden` are removed (the centre paper is never removed), with their links
 * - paper nodes whose plain id is in `bridgeIds` get kind "Bridge" (rose)
 * - links to removed or unknown nodes are dropped, so the canvas never sees a dangling link
 * - size grows with the number of drawn links
 */
export function buildViewGraph(g: PaperGraph, hidden: ReadonlySet<GraphLabel | "Bridge">, bridgeIds: ReadonlySet<string>): ViewGraph {
  const counts: ViewGraph["counts"] = {};
  const kindOf = (label: GraphLabel, id: string): GraphLabel | "Bridge" => (label === "Paper" && bridgeIds.has(nodePaperId(id)) ? "Bridge" : label);
  for (const n of g.nodes) {
    const k = kindOf(n.label, n.id);
    counts[k] = (counts[k] ?? 0) + 1;
  }
  const kept = new Map<string, ViewNode>();
  for (const n of g.nodes) {
    const kind = kindOf(n.label, n.id);
    const isCenter = n.id === g.center;
    if (!isCenter && hidden.has(kind)) continue;
    kept.set(n.id, {
      id: n.id, label: n.label, name: n.name ?? n.id, year: n.year, kind, color: GRAPH_COLORS[kind], val: 1, isCenter, degree: 0,
    });
  }
  const links: ViewLink[] = [];
  const seen = new Set<string>();
  for (const e of g.edges) {
    const a = kept.get(e.source), b = kept.get(e.target);
    if (!a || !b) continue;
    const key = e.source + "|" + e.type + "|" + e.target;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({ source: e.source, target: e.target, type: e.type });
    a.degree++;
    b.degree++;
  }
  for (const n of kept.values()) n.val = 1 + Math.min(8, Math.sqrt(n.degree)) + (n.isCenter ? 3 : 0);
  return { nodes: [...kept.values()], links, counts };
}

/** What the reader needs to know when the API cut the neighbourhood short (see graph.queries.select_links). */
export function graphNote(g: { truncated?: boolean; neighbors_total?: number } | undefined, limit: number): string | null {
  if (!g?.truncated || !g.neighbors_total) return null;
  const shown = Math.max(0, limit - 1);
  const total = g.neighbors_total.toLocaleString("en-US");
  const first = `Showing ${shown.toLocaleString("en-US")} of ${total} neighbours: the paper's own authors, venue and extracted elements first, then its most recent citations.`;
  return limit >= 1000 ? `${first} ${total} neighbours is more than the 1,000 nodes the API can return, so the rest cannot be shown.` : `${first} Raise “Max nodes” to see more.`;
}
