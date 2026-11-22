/*
 * How the research graph is drawn: glowing orbs, thin gradient links, particles along citation links, and the rules for
 * which labels show and what a hover highlights. Everything here is a plain function of its inputs (no React), so it can
 * be tested; GraphView only wires it to the force-graph canvas.
 */
import type { ViewNode } from "@/lib/graph";

/** how many of the best-connected nodes carry a label (besides the selected paper, the clicked node and the hovered node) */
export const MAX_LABELLED = 5;
export const MAX_DPR = 2;
/** the accent of the rings and highlights (the same sky blue as the dark theme's primary) */
export const ACCENT = "#38bdf8";
const LABEL_RGB = "230, 237, 247";

export type PaintNode = ViewNode & { x: number; y: number; vx?: number; vy?: number };
type NodeRef = string | { id?: string | number };
export interface PaintLink { source: NodeRef | PaintNode; target: NodeRef | PaintNode; type: string }

const idOf = (n: NodeRef | PaintNode): string => (typeof n === "string" ? n : String((n as { id?: string | number }).id ?? ""));
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/* ------------------------------------------------------------------------------------------------ colour */

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.trim().replace(/^#/, "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return [148, 163, 184];
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}
export function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${Math.round(clamp01(alpha) * 1000) / 1000})`;
}

/* ------------------------------------------------------------------------------------------------ labels */

/** The best-connected nodes (most links in the view first, then by name), at most `n`, never a node with no link. */
export function topDegreeIds(nodes: readonly Pick<ViewNode, "id" | "degree" | "name">[], n = MAX_LABELLED): string[] {
  return [...nodes]
    .filter((x) => x.degree > 0)
    .sort((a, b) => b.degree - a.degree || a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
    .slice(0, n)
    .map((x) => x.id);
}

/**
 * The nodes that carry a label: the selected paper (the centre of the graph), the node that was clicked, the node under
 * the pointer, and the few best-connected nodes. Nothing else is labelled, however far the view is zoomed in.
 */
export function labelTargets(o: {
  nodes: readonly Pick<ViewNode, "id" | "degree" | "name">[];
  centerId: string | null;
  selectedId: string | null;
  hoverId: string | null;
  topN?: number;
}): Set<string> {
  const present = new Set(o.nodes.map((n) => n.id));
  const out = new Set<string>();
  for (const id of [o.centerId, o.selectedId, o.hoverId]) if (id && present.has(id)) out.add(id);
  for (const id of topDegreeIds(o.nodes, o.topN ?? MAX_LABELLED)) out.add(id);
  return out;
}

/** Move each label's opacity toward 1 (it should show) or 0 (it should not): labels fade in and out. */
export function stepLabelAlpha(alpha: Map<string, number>, ids: Iterable<string>, targets: ReadonlySet<string>, dt: number, rate = 9): void {
  const k = 1 - Math.exp(-Math.max(0, dt) * rate);
  const all = new Set<string>(ids);
  for (const id of alpha.keys()) all.add(id);
  for (const id of all) {
    const cur = alpha.get(id) ?? 0;
    const next = cur + ((targets.has(id) ? 1 : 0) - cur) * k;
    if (next < 0.004 && !targets.has(id)) alpha.delete(id);
    else alpha.set(id, next);
  }
}

/** Move a value toward a target (an exponential ease, independent of the frame rate). */
export function easeToward(current: number, target: number, dt: number, rate = 8): number {
  return current + (target - current) * (1 - Math.exp(-Math.max(0, dt) * rate));
}

/* ------------------------------------------------------------------------------------------------ hover */

/** node id -> the ids it is linked to */
export function buildAdjacency(links: readonly { source: NodeRef | PaintNode; target: NodeRef | PaintNode }[]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    if (!adj.has(a)) adj.set(a, new Set());
    adj.get(a)!.add(b);
  };
  for (const l of links) {
    const a = idOf(l.source);
    const b = idOf(l.target);
    add(a, b);
    add(b, a);
  }
  return adj;
}

/** The node under the pointer and its neighbours: what stays lit while everything else dims. null = nothing hovered. */
export function highlightSet(adj: ReadonlyMap<string, ReadonlySet<string>>, hoverId: string | null): Set<string> | null {
  if (!hoverId) return null;
  return new Set([hoverId, ...(adj.get(hoverId) ?? [])]);
}

/** Does this link touch the hovered node? */
export function linkTouches(hoverId: string | null, link: { source: NodeRef | PaintNode; target: NodeRef | PaintNode }): boolean {
  return !!hoverId && (idOf(link.source) === hoverId || idOf(link.target) === hoverId);
}

/* ------------------------------------------------------------------------------------------------ entrance */

/** How far a node has appeared (0..1): nodes near the selected paper first, far ones later. `distance` is 0..1 (0 = at the paper). */
export function appearProgress(distance: number, reveal: number, spread = 0.5): number {
  return clamp01((reveal - clamp01(distance) * (1 - spread)) / spread);
}

/** How much of each link is drawn (0..1): the links draw in after the nodes started to appear. */
export function linkProgress(reveal: number): number {
  const p = clamp01((reveal - 0.25) / 0.75);
  return 1 - (1 - p) * (1 - p); // ease out
}

/** Positions (0..1 along the link, from source to target) of `count` particles at time `t` seconds. */
export function particlePositions(count: number, t: number, speed = 0.22): number[] {
  return Array.from({ length: count }, (_, i) => (((t * speed + i / count) % 1) + 1) % 1);
}

/** A small stable number (0..2π) per node id, so each node drifts out of step with the others. */
export function hashPhase(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i += 1) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return ((h >>> 0) / 4294967296) * Math.PI * 2;
}

/* ------------------------------------------------------------------------------------------------ pixel ratio */

/**
 * force-graph reads window.devicePixelRatio itself (to size its canvas and to pick nodes), with no option for it. This
 * makes that property report at most `max` while the graph is mounted, and returns a function that puts it back.
 */
export function capDevicePixelRatio(max = MAX_DPR): () => void {
  if (typeof window === "undefined") return () => {};
  const original = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");
  const real = () => (original?.get ? original.get.call(window) : (original?.value ?? 1)) as number;
  Object.defineProperty(window, "devicePixelRatio", { configurable: true, get: () => Math.min(real() || 1, max) });
  return () => {
    if (original) Object.defineProperty(window, "devicePixelRatio", original);
    else delete (window as unknown as Record<string, unknown>).devicePixelRatio;
  };
}

/* ------------------------------------------------------------------------------------------------ painting */

/** What the painters need to know about the current moment. */
export interface PaintState {
  /** entrance progress, 0..1 (1 = fully revealed) */
  reveal: number;
  /** seconds, for the idle drift and the particles */
  time: number;
  /** 0..1, the phase of the pulsing rings */
  ring: number;
  /** false = reduced motion: no drift, no particles, no pulsing, no entrance */
  animate: boolean;
  /** false on large graphs: the particles are left out to keep the frame rate up */
  particles: boolean;
  centerId: string | null;
  selectedId: string | null;
  hoverId: string | null;
  /** the hovered node and its neighbours (null = no hover) */
  highlight: Set<string> | null;
  /** 0..1, how far everything else has dimmed */
  dim: number;
  /** opacity of each node's label (see stepLabelAlpha) */
  labelAlpha: Map<string, number>;
  /** distance from the selected paper, 0..1, by node id (for the entrance) */
  distance: Map<string, number>;
}

export function newPaintState(animate: boolean): PaintState {
  return {
    reveal: animate ? 0 : 1, time: 0, ring: 0, animate, particles: true, centerId: null, selectedId: null, hoverId: null,
    highlight: null, dim: 0, labelAlpha: new Map(), distance: new Map(),
  };
}

/** The distance of every node from the selected paper in the current layout, scaled to 0..1. */
export function distancesFromCenter(nodes: readonly PaintNode[], centerId: string | null): Map<string, number> {
  const out = new Map<string, number>();
  const c = nodes.find((n) => n.id === centerId);
  if (!c) return out;
  let max = 0;
  for (const n of nodes) max = Math.max(max, Math.hypot((n.x ?? 0) - (c.x ?? 0), (n.y ?? 0) - (c.y ?? 0)));
  for (const n of nodes) out.set(n.id, max > 0 ? Math.hypot((n.x ?? 0) - (c.x ?? 0), (n.y ?? 0) - (c.y ?? 0)) / max : 0);
  return out;
}

const sprites = new Map<string, HTMLCanvasElement>();
/** A glowing orb drawn once per colour: a hot core fading through the colour to nothing. Drawn many times, cheaply. */
export function orbSprite(color: string): HTMLCanvasElement | null {
  if (typeof document === "undefined") return null;
  const hit = sprites.get(color);
  if (hit) return hit;
  const c = document.createElement("canvas");
  c.width = c.height = 96;
  const g = c.getContext("2d");
  if (!g) return null;
  const grad = g.createRadialGradient(48, 48, 0, 48, 48, 48);
  grad.addColorStop(0, "rgba(255, 255, 255, 0.95)");
  grad.addColorStop(0.14, rgba(color, 0.95));
  grad.addColorStop(0.42, rgba(color, 0.3));
  grad.addColorStop(1, rgba(color, 0));
  g.fillStyle = grad;
  g.fillRect(0, 0, 96, 96);
  sprites.set(color, c);
  return c;
}

/** The radius of the core of a node: larger for better-connected nodes. */
export function nodeRadius(n: Pick<ViewNode, "val" | "isCenter">): number {
  return 2 + n.val * 0.95 + (n.isCenter ? 2.5 : 0);
}

function drift(n: { id: string }, st: PaintState): [number, number] {
  if (!st.animate) return [0, 0];
  const p = hashPhase(n.id);
  return [Math.sin(st.time * 0.55 + p) * 1.8, Math.cos(st.time * 0.47 + p * 1.3) * 1.8];
}

type Pt = { id: string; x: number; y: number };
const pos = (n: Pt, st: PaintState): [number, number] => {
  const [dx, dy] = drift(n, st);
  return [n.x + dx, n.y + dy];
};

function dimOf(id: string, st: PaintState): number {
  return st.highlight && !st.highlight.has(id) ? 1 - 0.84 * st.dim : 1;
}

/** Draw one node: a glowing orb sized by its degree; the selected paper as a larger core with pulsing rings; its label if it has one. */
export function drawNode(ctx: CanvasRenderingContext2D, n: PaintNode, scale: number, st: PaintState): void {
  const appear = st.animate ? appearProgress(st.distance.get(n.id) ?? 0, st.reveal) : 1;
  if (appear <= 0.002) return;
  const [x, y] = pos(n, st);
  const r = nodeRadius(n) * (0.55 + 0.45 * appear);
  const dim = dimOf(n.id, st);
  const isCenter = n.id === st.centerId;

  ctx.save();
  // additive blending: overlapping glows add up instead of covering each other
  ctx.globalCompositeOperation = "lighter";
  const sprite = orbSprite(n.color);
  const R = r * (isCenter ? 4.2 : 3.3);
  ctx.globalAlpha = appear * dim * (isCenter ? 1 : 0.92);
  if (sprite) ctx.drawImage(sprite, x - R, y - R, R * 2, R * 2);
  else {
    ctx.fillStyle = n.color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  if (isCenter) {
    // a hotter core, and one or two slow rings (a single still ring when nothing may animate)
    const core = orbSprite("#ffffff");
    if (core) {
      ctx.globalAlpha = appear * dim * 0.55;
      ctx.drawImage(core, x - r * 1.5, y - r * 1.5, r * 3, r * 3);
    }
    ctx.lineWidth = 1.2 / scale;
    ctx.strokeStyle = ACCENT;
    if (st.animate) {
      for (const offset of [0, 0.5]) {
        const phase = (st.ring + offset) % 1;
        ctx.globalAlpha = appear * dim * Math.pow(1 - phase, 1.6) * 0.6;
        ctx.beginPath();
        ctx.arc(x, y, r * (1.7 + 3.4 * phase), 0, Math.PI * 2);
        ctx.stroke();
      }
    } else {
      ctx.globalAlpha = dim * 0.4;
      ctx.beginPath();
      ctx.arc(x, y, r * 2.4, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  if (n.id === st.selectedId && !isCenter) {
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 0.9 * dim;
    ctx.lineWidth = 1.3 / scale;
    ctx.strokeStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(x, y, r * 2, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();

  const la = st.labelAlpha.get(n.id) ?? 0;
  if (la > 0.02 && appear > 0.5) {
    const text = n.name.length > 38 ? n.name.slice(0, 37) + "…" : n.name;
    ctx.save();
    ctx.font = `${Math.max(3, 11 / scale)}px Inter Variable, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.shadowColor = "rgba(5, 8, 16, 0.9)";
    ctx.shadowBlur = 4;
    ctx.fillStyle = `rgba(${LABEL_RGB}, ${Math.round(la * dim * 1000) / 1000})`;
    ctx.fillText(text, x, y + r * 1.6 + 2);
    ctx.restore();
  }
}

/** Draw one link: a thin, low-opacity gradient from one end's colour to the other's, drawn in; citations carry moving particles. */
export function drawLink(ctx: CanvasRenderingContext2D, link: PaintLink, scale: number, st: PaintState, gradient = true): void {
  const s = link.source as PaintNode;
  const t = link.target as PaintNode;
  if (typeof s !== "object" || typeof t !== "object" || s.x === undefined || t.x === undefined) return;
  const p = st.animate ? linkProgress(st.reveal) : 1;
  if (p <= 0.002) return;
  const [sx, sy] = pos(s, st);
  const [tx, ty] = pos(t, st);
  const ex = sx + (tx - sx) * p;
  const ey = sy + (ty - sy) * p;
  const touches = linkTouches(st.hoverId, link);
  const dim = st.highlight ? (touches ? 1 : 1 - 0.88 * st.dim) : 1;
  const alpha = (touches ? 0.75 : 0.24) * dim * p;
  ctx.save();
  ctx.lineWidth = Math.max(0.3, (touches ? 1.5 : 0.9) / scale);
  if (gradient) {
    const g = ctx.createLinearGradient(sx, sy, ex, ey);
    g.addColorStop(0, rgba(s.color, alpha));
    g.addColorStop(1, rgba(t.color, alpha));
    ctx.strokeStyle = g;
  } else {
    ctx.strokeStyle = rgba(s.color, alpha);
  }
  ctx.beginPath();
  ctx.moveTo(sx, sy);
  ctx.lineTo(ex, ey);
  ctx.stroke();

  // particles flow along a citation, in its direction (source cites target); none when nothing may animate
  if (st.animate && st.particles && link.type === "CITES" && p > 0.98) {
    ctx.globalCompositeOperation = "lighter";
    const size = Math.min(2.2, 1.7 / Math.sqrt(scale));
    for (const f of particlePositions(2, st.time)) {
      ctx.globalAlpha = Math.min(1, dim * (touches ? 1 : 0.85));
      ctx.fillStyle = rgba(f < 0.5 ? s.color : t.color, 0.95);
      ctx.beginPath();
      ctx.arc(sx + (tx - sx) * f, sy + (ty - sy) * f, size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}
