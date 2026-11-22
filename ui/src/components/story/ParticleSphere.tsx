import { useEffect, useRef } from "react";

/*
 * The first picture of the story: a sphere of about 1,200 points (a Fibonacci sphere: evenly spread), slowly turning. It
 * tilts a little towards the pointer; points near the pointer are pushed outward and spring back. Points in front are
 * larger and brighter than points at the back (perspective shading), in the accent colour at the front and the teal
 * colour at the back. It is an ILLUSTRATION: the points are not papers (the tag on the story canvas says so).
 *
 * `visible` false fades it out (moving to step 1, where the network canvas takes over) and, once it has faded, the
 * animation loop stops. `still` draws one frame and nothing else (reduced motion). Everything is cleaned up on unmount.
 */

export const POINT_COUNT = 1200;
export const MAX_DPR = 2;
/** the fade between the sphere and the network, in ms */
export const FADE_MS = 800;
const PUSH_RADIUS = 110;
const MAX_PUSH = 26;
const DEPTH_BINS = 8;

/** `n` points spread evenly over the unit sphere (Fibonacci / golden-angle spiral). Returned as x, y, z triples. */
export function fibonacciSphere(n: number): Float32Array {
  const pts = new Float32Array(n * 3);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i += 1) {
    const y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const a = golden * i;
    pts[i * 3] = Math.cos(a) * r;
    pts[i * 3 + 1] = y;
    pts[i * 3 + 2] = Math.sin(a) * r;
  }
  return pts;
}

/** Rotate a point around the y axis by `yaw`, then around the x axis by `pitch`. */
export function rotate(x: number, y: number, z: number, yaw: number, pitch: number): [number, number, number] {
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}

/** Perspective: the scale of a point at depth z (-1 back .. 1 front) for a camera `distance` radii away. */
export function perspective(z: number, distance = 3): number {
  return distance / (distance - z);
}

function readColors(): { accent: string; teal: string } {
  const cs = getComputedStyle(document.documentElement);
  return { accent: cs.getPropertyValue("--primary").trim() || "#38bdf8", teal: cs.getPropertyValue("--teal").trim() || "#2dd4bf" };
}

export default function ParticleSphere({ visible, still = false, centerX = 0.36, className }: { visible: boolean; still?: boolean; centerX?: number; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const visibleRef = useRef(visible);
  const wake = useRef<(() => void) | null>(null);
  useEffect(() => {
    visibleRef.current = visible;
    wake.current?.();
  }, [visible]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const box = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !box || !ctx) return;

    const base = fibonacciSphere(POINT_COUNT);
    // the spring offset of each point on the screen (x, y) and its velocity
    const off = new Float32Array(POINT_COUNT * 2);
    const vel = new Float32Array(POINT_COUNT * 2);
    const sx = new Float32Array(POINT_COUNT);
    const sy = new Float32Array(POINT_COUNT);
    const depth = new Float32Array(POINT_COUNT);
    let w = 0, h = 0;
    let colors = readColors();
    let px = -1e4, py = -1e4;
    let tiltX = 0, tiltY = 0, tiltTX = 0, tiltTY = 0;
    let raf = 0, last = 0, t0 = 0;
    let opacity = visibleRef.current ? 1 : 0;

    const draw = (now: number) => {
      raf = 0;
      if (document.hidden) return;
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
      last = now;
      if (!t0) t0 = now;
      const t = still ? 0 : (now - t0) / 1000;
      opacity += ((visibleRef.current ? 1 : 0) - opacity) * (1 - Math.exp((-dt * 1000 * 3) / FADE_MS));
      if (!visibleRef.current && opacity < 0.01) {
        opacity = 0;
        ctx.clearRect(0, 0, w, h);
        last = 0;
        return; // faded out: the loop stops here, and wakes when it becomes visible again
      }
      canvas.style.opacity = String(opacity);

      const cx = w * centerX, cy = h * 0.5;
      const R = Math.max(40, Math.min(h * 0.36, w * 0.26));
      tiltTX = Math.max(-1, Math.min(1, (px - cx) / (w / 2))) * 0.35;
      tiltTY = Math.max(-1, Math.min(1, (py - cy) / (h / 2))) * 0.3;
      const ease = 1 - Math.exp(-dt * 3);
      tiltX += (tiltTX - tiltX) * ease;
      tiltY += (tiltTY - tiltY) * ease;
      const yaw = t * 0.12 + tiltX;
      const pitch = 0.25 + tiltY;

      const spring = 150, damp = Math.exp(-dt * 8);
      for (let i = 0; i < POINT_COUNT; i += 1) {
        const [x, y, z] = rotate(base[i * 3]!, base[i * 3 + 1]!, base[i * 3 + 2]!, yaw, pitch);
        const s = perspective(z);
        const bx = cx + x * R * s, by = cy + y * R * s;
        let tx = 0, ty = 0;
        if (!still) {
          const dx = bx - px, dy = by - py;
          const d = Math.hypot(dx, dy);
          if (d < PUSH_RADIUS && d > 0.001) {
            const f = (1 - d / PUSH_RADIUS) ** 2 * MAX_PUSH;
            tx = (dx / d) * f;
            ty = (dy / d) * f;
          }
          const k = i * 2;
          vel[k] = (vel[k]! + (tx - off[k]!) * spring * dt) * damp;
          vel[k + 1] = (vel[k + 1]! + (ty - off[k + 1]!) * spring * dt) * damp;
          off[k] = off[k]! + vel[k]! * dt;
          off[k + 1] = off[k + 1]! + vel[k + 1]! * dt;
        }
        sx[i] = bx + off[i * 2]!;
        sy[i] = by + off[i * 2 + 1]!;
        depth[i] = (z + 1) / 2; // 0 back .. 1 front
      }

      ctx.clearRect(0, 0, w, h);
      // points are drawn in depth bins (back to front): one fill per bin, each with its own size, brightness and colour
      for (let bin = 0; bin < DEPTH_BINS; bin += 1) {
        const lo = bin / DEPTH_BINS, hi = (bin + 1) / DEPTH_BINS;
        const mid = (lo + hi) / 2;
        ctx.fillStyle = mid > 0.5 ? colors.accent : colors.teal;
        ctx.globalAlpha = 0.18 + 0.78 * mid;
        const r = 0.7 + 1.5 * mid;
        ctx.beginPath();
        for (let i = 0; i < POINT_COUNT; i += 1) {
          const dpt = depth[i]!;
          if (dpt < lo || (dpt >= hi && bin < DEPTH_BINS - 1)) continue;
          ctx.moveTo(sx[i]! + r, sy[i]!);
          ctx.arc(sx[i]!, sy[i]!, r, 0, Math.PI * 2);
        }
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (!still) raf = requestAnimationFrame(draw);
    };

    const start = () => {
      if (!raf && !document.hidden) raf = requestAnimationFrame(draw);
    };
    wake.current = start;
    const resize = () => {
      w = box.clientWidth;
      h = box.clientHeight;
      if (w === 0 || h === 0) return;
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      colors = readColors();
      if (still) start(); // one new still frame
    };
    const onMove = (e: PointerEvent) => {
      const r = box.getBoundingClientRect();
      px = e.clientX - r.left;
      py = e.clientY - r.top;
    };
    const onVisibility = () => {
      if (document.hidden) {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        last = 0;
      } else {
        start();
      }
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    if (!still) {
      document.addEventListener("pointermove", onMove, { passive: true });
      document.addEventListener("visibilitychange", onVisibility);
    }
    start();
    return () => {
      wake.current = null;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      ro.disconnect();
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [still, centerX]);

  return (
    <div className={className ?? "pointer-events-none absolute inset-0"} aria-hidden data-testid="particle-sphere" data-visible={visible ? "" : undefined}>
      <canvas ref={canvasRef} className="absolute inset-0 size-full" />
    </div>
  );
}
