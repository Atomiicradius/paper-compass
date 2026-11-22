import { normalizePaperId } from "@/lib/ids";

/**
 * What the address bar remembers: which view is open, which opportunity's evidence drawer, which paper's details
 * and which paper the graph is centred on. It lives in the hash, so reloading restores the screen, Back closes a
 * drawer, and a link to "#/candidates?opp=14" opens that opportunity. The search text and filters are not stored.
 */
export const VIEWS = ["candidates", "papers", "graph", "landscape"] as const;
export type View = (typeof VIEWS)[number];

export interface Route {
  view: View;
  opp: number | null;
  paper: string | null;
  graph: string;
}

export const DEFAULT_ROUTE: Route = { view: "candidates", opp: null, paper: null, graph: "" };

/** Anything unrecognised is ignored (never an error): a hand-edited or old link must not break the app. */
export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [path = "", query = ""] = raw.split("?", 2);
  const view = (VIEWS as readonly string[]).includes(path) ? (path as View) : DEFAULT_ROUTE.view;
  const params = new URLSearchParams(query);
  const opp = params.get("opp");
  const oppNum = opp !== null && /^[1-9]\d{0,9}$/.test(opp) ? Number(opp) : null;
  const paper = normalizePaperId(params.get("paper"));
  const graph = normalizePaperId(params.get("graph"));
  return { view, opp: oppNum, paper: paper || null, graph };
}

/** The hash for a route; the default route (candidates, nothing open) is the empty string. */
export function formatRoute(r: Route): string {
  const params = new URLSearchParams();
  if (r.opp !== null) params.set("opp", String(r.opp));
  if (r.paper) params.set("paper", r.paper);
  if (r.graph) params.set("graph", r.graph);
  const q = params.toString();
  if (r.view === DEFAULT_ROUTE.view && !q) return "";
  return `#/${r.view}${q ? "?" + q : ""}`;
}

export function sameRoute(a: Route, b: Route): boolean {
  return formatRoute(a) === formatRoute(b);
}
