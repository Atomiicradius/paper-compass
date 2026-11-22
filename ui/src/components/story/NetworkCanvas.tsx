import { useEffect, useRef } from "react";

/*
 * A decorative network drawn on a <canvas>, behind the story. It is an ILLUSTRATION: the groups are as large (relative to
 * each other) as the real clusters returned by the API, but the dots are not papers and their positions mean nothing.
 * The tag "ILLUSTRATION · NOT TO SCALE" says so on the canvas.
 */

export const MAX_NODES = 300;
export const MAX_DPR = 2;
/** how many links are drawn between different clusters (a handful: they are context, the highlighted pair is the point) */
export const MAX_CROSS_LINKS = 8;

/** The look of the canvas. Each story step has one (see canvasStateForStep). */
export type CanvasState = "scattered" | "time" | "clusters" | "lines" | "pair" | "pulse";

// step 0 scattered; 1-2 spread along a time axis; 3 coloured by cluster; 4 connecting lines; 5 one highlighted pair; 6-7 a pulsing link
const STATE_BY_STEP: CanvasState[] = ["scattered", "time", "time", "clusters", "lines", "pair", "pulse", "pulse"];
export function canvasStateForStep(step: number): CanvasState {
  return STATE_BY_STEP[Math.min(STATE_BY_STEP.length - 1, Math.max(0, Math.round(step)))] ?? "scattered";
}

/**
 * How many dots each group gets: proportional to its size (the real cluster size), at least 1, and at most `cap` in
 * total. With no sizes (the clusters were not available) there is one neutral group of fixed size: purely decoration.
 */
export function allocateNodes(sizes: readonly number[], cap = MAX_NODES): number[] {
  const real = sizes.filter((s) => Number.isFinite(s) && s > 0);
  if (real.length === 0) return [Math.min(cap, 120)];
  const groups = real.slice(0, cap);
  const total = groups.reduce((a, b) => a + b, 0);
  const exact = groups.map((s) => (s / total) * cap);
  const counts = exact.map((x) => Math.max(1, Math.floor(x)));
  let sum = counts.reduce((a, b) => a + b, 0);
  // trim the largest groups if the minimum of 1 pushed the total over the cap
  while (sum > cap) {
    let k = 0;
    counts.forEach((c, i) => {
      if (c > (counts[k] ?? 0)) k = i;
    });
    counts[k] = (counts[k] ?? 1) - 1;
    sum -= 1;
  }
  // hand out what is left to the groups that lost the most when rounding down
  const order = exact.map((x, i) => ({ i, rem: x - Math.floor(x) })).sort((a, b) => b.rem - a.rem);
  for (let n = 0; sum < cap && n < order.length; n += 1) {
    const { i } = order[n]!;
    counts[i] = (counts[i] ?? 0) + 1;
    sum += 1;
  }
  return counts;
}

/** A small seeded random generator, so the picture is the same every time. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Node {
  group: number;
  phase: number;
  /** targets: scattered, along the time axis, and in the group */
  sx: number; sy: number; tx: number; ty: number; cx: number; cy: number;
  /** current position */
  x: number; y: number;
}

interface Scene {
  nodes: Node[];
  centers: { x: number; y: number }[];
  edges: [number, number][];
  pair: [number, number] | null;
  axisY: number;
  left: number;
  right: number;
}

/** Lay the dots out for a canvas of this size (css pixels). Pure: the same input always gives the same scene. */
export function buildScene(counts: readonly number[], w: number, h: number): Scene {
  const rand = mulberry32(20261122);
  const left = Math.min(90, w * 0.1);
  const right = Math.max(left + 60, w * 0.62); // the glass panel sits on the right: keep the picture on the left
  const groups = counts.length;
  const cx0 = (left + right) / 2;
  const cy0 = h * 0.5;
  const ring = Math.min((right - left) * 0.36, h * 0.3);
  const centers = counts.map((_, g) => {
    if (groups === 1) return { x: cx0, y: cy0 };
    const a = (g / groups) * Math.PI * 2 - Math.PI / 2;
    return { x: cx0 + Math.cos(a) * ring * 1.15, y: cy0 + Math.sin(a) * ring };
  });
  const axisY = h * 0.72;
  const nodes: Node[] = [];
  counts.forEach((n, g) => {
    const spread = 14 + 5 * Math.sqrt(n);
    for (let k = 0; k < n; k += 1) {
      const r = spread * Math.sqrt(rand());
      const ang = rand() * Math.PI * 2;
      const sx = left + rand() * (right - left);
      const sy = h * 0.12 + rand() * h * 0.76;
      nodes.push({
        group: g, phase: rand() * Math.PI * 2,
        sx, sy,
        tx: left + rand() * (right - left), ty: axisY - 8 - Math.abs(rand() + rand() - 1) * h * 0.38,
        cx: centers[g]!.x + Math.cos(ang) * r, cy: centers[g]!.y + Math.sin(ang) * r,
        x: sx, y: sy,
      });
    }
  });
  // lines: a chain through each group, and a few links between groups
  const edges: [number, number][] = [];
  let offset = 0;
  counts.forEach((n) => {
    for (let k = 1; k < n; k += 1) edges.push([offset + k - 1, offset + k]);
    for (let k = 0; k < Math.floor(n / 6); k += 1) edges.push([offset + Math.floor(rand() * n), offset + Math.floor(rand() * n)]);
    offset += n;
  });
  // only a few links between clusters, so the highlighted pair is easy to see among them
  let between = 0;
  for (let tries = 0; tries < 400 && between < MAX_CROSS_LINKS && groups > 1; tries += 1) {
    const a = Math.floor(rand() * nodes.length);
    const b = Math.floor(rand() * nodes.length);
    if (nodes[a]!.group !== nodes[b]!.group) {
      edges.push([a, b]);
      between += 1;
    }
  }
  const pair: [number, number] | null = groups >= 2 ? [0, Math.min(groups - 1, Math.ceil(groups / 2))] : null;
  return { nodes, centers, edges, pair, axisY, left, right };
}

/** colours of the groups: the semantic palette of the app plus a few neighbours, repeated if there are more groups */
const PALETTE = ["#3B82F6", "#10B981", "#F97316", "#8B5CF6", "#EC4899", "#0EA5E9", "#EAB308", "#14B8A6", "#A78BFA", "#F43F5E"];

function readColors() {
  const cs = getComputedStyle(document.documentElement);
  const get = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  return { accent: get("--primary", "#38bdf8"), muted: get("--muted-foreground", "#94a3b8") };
}

export interface NetworkCanvasProps {
  /** the story step (0..7); it selects the look */
  step: number;
  /** the size of each real cluster (from the API); the groups follow these sizes */
  groupSizes: readonly number[];
}

export default function NetworkCanvas({ step, groupSizes }: NetworkCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<CanvasState>(canvasStateForStep(step));
  useEffect(() => {
    stateRef.current = canvasStateForStep(step);
  }, [step]);
  const sizesKey = groupSizes.join(",");

  useEffect(() => {
    const canvas = canvasRef.current;
    const box = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !box || !ctx) return;

    const counts = allocateNodes(sizesKey ? sizesKey.split(",").map(Number) : []);
    let scene: Scene | null = null;
    let w = 0;
    let h = 0;
    let colors = readColors();
    // animated amounts (0..1): how much each look is "on"
    const k = { color: 0, lines: 0, dim: 0, pulse: 0, time: 0 };
    let raf = 0;
    let last = 0;
    let frames = 0;
    let fpsStart = 0;
    let t0 = 0;

    const resize = () => {
      w = box.clientWidth;
      h = box.clientHeight;
      if (w === 0 || h === 0) return;
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR); // never more than 2, whatever the screen
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      scene = buildScene(counts, w, h);
    };

    const draw = (now: number) => {
      raf = 0;
      if (document.hidden) return; // paused while the tab is hidden; the visibilitychange handler restarts the loop
      raf = requestAnimationFrame(draw);
      if (!scene) return;
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
      last = now;
      if (!t0) t0 = now;
      const t = (now - t0) / 1000;
      frames += 1;
      if (now - fpsStart >= 1000) {
        if (fpsStart) canvas.dataset.fps = String(Math.round((frames * 1000) / (now - fpsStart)));
        fpsStart = now;
        frames = 0;
        colors = readColors(); // follow a theme change
      }
      const state = stateRef.current;
      const ease = (target: number, rate: number, v: number) => v + (target - v) * (1 - Math.exp(-dt * rate));
      k.color = ease(state === "scattered" || state === "time" ? 0 : 1, 3, k.color);
      k.lines = ease(state === "lines" || state === "pair" || state === "pulse" ? 1 : 0, 3, k.lines);
      // the pair is already half emphasised on the "lines" step, fully on "pair" and "pulse"
      k.dim = ease(state === "pair" || state === "pulse" ? 1 : state === "lines" ? 0.55 : 0, 3, k.dim);
      k.pulse = ease(state === "pulse" ? 1 : 0, 3, k.pulse);
      k.time = ease(state === "time" ? 1 : 0, 3, k.time);

      const move = 1 - Math.exp(-dt * 2.4);
      for (const n of scene.nodes) {
        const drift = state === "scattered" ? 1 : 0.15;
        const tx = state === "scattered" ? n.sx : state === "time" ? n.tx : n.cx;
        const ty = state === "scattered" ? n.sy : state === "time" ? n.ty : n.cy;
        n.x += (tx + Math.sin(t * 0.5 + n.phase) * 5 * drift - n.x) * move;
        n.y += (ty + Math.cos(t * 0.43 + n.phase) * 5 * drift - n.y) * move;
      }

      ctx.clearRect(0, 0, w, h);
      // the time axis: a plain line with ticks, no labels (there is no real data on it)
      if (k.time > 0.01) {
        ctx.globalAlpha = 0.5 * k.time;
        ctx.strokeStyle = colors.muted;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(scene.left, scene.axisY);
        ctx.lineTo(scene.right, scene.axisY);
        for (let i = 0; i <= 10; i += 1) {
          const x = scene.left + ((scene.right - scene.left) * i) / 10;
          ctx.moveTo(x, scene.axisY);
          ctx.lineTo(x, scene.axisY + (i % 5 === 0 ? 7 : 4));
        }
        ctx.stroke();
      }
      const inPair = (g: number) => !!scene && !!scene.pair && (g === scene.pair[0] || g === scene.pair[1]);
      // connecting lines
      if (k.lines > 0.01) {
        ctx.lineWidth = 0.8;
        ctx.strokeStyle = colors.muted;
        ctx.globalAlpha = 0.13 * k.lines * (1 - 0.6 * k.dim);
        ctx.beginPath();
        for (const [a, b] of scene.edges) {
          const na = scene.nodes[a]!;
          const nb = scene.nodes[b]!;
          ctx.moveTo(na.x, na.y);
          ctx.lineTo(nb.x, nb.y);
        }
        ctx.stroke();
      }
      // the dots: neutral first, then the group colour fading in on top
      for (const n of scene.nodes) {
        const dim = scene.pair && !inPair(n.group) ? 1 - 0.78 * k.dim : 1;
        const r = 2.1 + (inPair(n.group) ? 0.9 * k.dim : 0);
        ctx.fillStyle = colors.muted;
        ctx.globalAlpha = 0.55 * (1 - k.color) * dim;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();
        if (k.color > 0.01) {
          ctx.fillStyle = PALETTE[n.group % PALETTE.length]!;
          ctx.globalAlpha = 0.9 * k.color * dim;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      // the highlighted pair of groups, and the pulsing link between them
      if (scene.pair && k.dim > 0.01) {
        const a = scene.centers[scene.pair[0]]!;
        const b = scene.centers[scene.pair[1]]!;
        const beat = 0.5 + 0.5 * Math.sin(t * 3.2);
        ctx.strokeStyle = colors.accent;
        ctx.lineCap = "round";
        ctx.globalAlpha = Math.min(1, 0.2 + 0.55 * k.dim + 0.3 * k.pulse * beat);
        ctx.lineWidth = 1.4 + 2.6 * k.pulse * beat;
        ctx.setLineDash(k.pulse > 0.5 ? [] : [6, 6]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
        if (k.pulse > 0.01) {
          ctx.fillStyle = colors.accent;
          ctx.globalAlpha = k.pulse * (0.15 + 0.25 * beat);
          for (const c of [a, b]) {
            ctx.beginPath();
            ctx.arc(c.x, c.y, 26 + 14 * beat, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      ctx.globalAlpha = 1;
    };

    const start = () => {
      if (!raf && !document.hidden) {
        last = 0;
        raf = requestAnimationFrame(draw);
      }
    };
    const onVisibility = () => {
      if (document.hidden) {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
      } else {
        start();
      }
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    document.addEventListener("visibilitychange", onVisibility);
    start();
    return () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      document.removeEventListener("visibilitychange", onVisibility);
      ro.disconnect();
    };
  }, [sizesKey]);

  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      <canvas ref={canvasRef} className="absolute inset-0 size-full" data-testid="network-canvas" />
      <span className="mono-label absolute top-5 left-14 rounded-md border border-border bg-background/60 px-2 py-1 text-[10px] backdrop-blur-sm">ILLUSTRATION · NOT TO SCALE</span>
    </div>
  );
}
