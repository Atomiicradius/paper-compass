import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";

/*
 * The background of the whole app: one flat colour (the page background token) and, on top of it, ONE full-screen canvas
 * with a grid of small dots. At rest the dots are tiny and faint. Near the pointer they grow, brighten to the accent
 * colour and are pushed away, then spring back; the pointer also leaves a short light trail that fades in ~600 ms.
 *
 * It costs nothing when idle: the animation frame loop runs only while the pointer moved recently or some dot / trail
 * point is still moving, and it stops by itself. It pauses while the tab is hidden. With reduced motion or a touch screen
 * (coarse pointer) it draws the faint grid once and does not respond at all.
 */

/** distance between two dots of the grid, in CSS pixels */
export const GRID = 26;
/** how far from the pointer a dot reacts */
export const RADIUS = 140;
/** how long a point of the trail stays visible */
export const TRAIL_MS = 600;
/** the most a dot is pushed away from its place, in CSS pixels */
export const MAX_PUSH = 22;
export const MAX_DPR = 2;
/** the loop keeps running this long after the last pointer move (so the dots can settle) */
const IDLE_AFTER_MS = 700;
const REST_RADIUS = 0.9;
const REST_ALPHA = 0.17;

/** How strongly the pointer affects a dot at this distance: 1 at the pointer, 0 at RADIUS and beyond (smooth). */
export function influence(distance: number, radius = RADIUS): number {
  if (!Number.isFinite(distance) || distance >= radius) return 0;
  const x = 1 - Math.max(0, distance) / radius;
  return x * x;
}

/** The state of one dot that has moved: its offset from the grid place, its velocity and its glow (0..1). */
export interface DotState {
  ox: number; oy: number; vx: number; vy: number; glow: number;
}

/**
 * One physics step for a dot (dt in seconds). The dot is pulled towards the target (a push away from the pointer, scaled by
 * the influence) like a spring, with damping, and its glow follows the influence. Returns true while the dot is still moving.
 */
export function stepDot(d: DotState, targetX: number, targetY: number, targetGlow: number, dt: number): boolean {
  const k = 170; // spring stiffness
  const damping = Math.exp(-dt * 9);
  d.vx = (d.vx + (targetX - d.ox) * k * dt) * damping;
  d.vy = (d.vy + (targetY - d.oy) * k * dt) * damping;
  d.ox += d.vx * dt;
  d.oy += d.vy * dt;
  d.glow += (targetGlow - d.glow) * (1 - Math.exp(-dt * 10));
  return Math.abs(d.ox) > 0.04 || Math.abs(d.oy) > 0.04 || Math.abs(d.vx) > 0.04 || Math.abs(d.vy) > 0.04 || d.glow > 0.01 || targetGlow > 0;
}

interface TrailPoint { x: number; y: number; t: number }

/** The colours of the current theme, from the CSS tokens (`--dot-rgb`, `--dot-hot-rgb`: "r, g, b"). */
export function readDotColors(): { rest: string; hot: string } {
  const cs = getComputedStyle(document.documentElement);
  return { rest: cs.getPropertyValue("--dot-rgb").trim() || "148, 163, 184", hot: cs.getPropertyValue("--dot-hot-rgb").trim() || "56, 189, 248" };
}

export function DotField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const coarse = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
    const interactive = !reduced && !coarse;

    let w = 0;
    let h = 0;
    let cols = 0;
    let colors = readDotColors();
    const moved = new Map<number, DotState>(); // only the dots that are away from their place
    let trail: TrailPoint[] = [];
    let px = -1e4;
    let py = -1e4;
    let lastMove = 0;
    let raf = 0;
    let last = 0;

    const drawRest = () => {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = `rgba(${colors.rest}, ${REST_ALPHA})`;
      ctx.beginPath();
      for (let y = GRID / 2; y < h; y += GRID) {
        for (let x = GRID / 2; x < w; x += GRID) {
          ctx.rect(x - REST_RADIUS, y - REST_RADIUS, REST_RADIUS * 2, REST_RADIUS * 2);
        }
      }
      ctx.fill();
    };

    const resize = () => {
      w = window.innerWidth;
      h = window.innerHeight;
      if (w === 0 || h === 0) return;
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.max(1, Math.ceil(w / GRID));
      colors = readDotColors();
      moved.clear();
      drawRest();
    };

    const frame = (now: number) => {
      raf = 0;
      if (document.hidden) return; // paused; the visibilitychange handler starts it again
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
      last = now;
      const pointerActive = now - lastMove < IDLE_AFTER_MS;

      // wake the dots near the pointer
      if (pointerActive) {
        const c0 = Math.max(0, Math.floor((px - RADIUS) / GRID));
        const c1 = Math.min(cols - 1, Math.floor((px + RADIUS) / GRID));
        const r0 = Math.max(0, Math.floor((py - RADIUS) / GRID));
        const r1 = Math.floor((py + RADIUS) / GRID);
        for (let r = r0; r <= r1; r += 1) {
          for (let c = c0; c <= c1; c += 1) {
            const key = r * cols + c;
            if (!moved.has(key) && influence(Math.hypot(c * GRID + GRID / 2 - px, r * GRID + GRID / 2 - py)) > 0) moved.set(key, { ox: 0, oy: 0, vx: 0, vy: 0, glow: 0 });
          }
        }
      }
      // the trail: drop the old points
      trail = trail.filter((p) => now - p.t < TRAIL_MS);

      let busy = trail.length > 0;
      ctx.clearRect(0, 0, w, h);
      // the resting grid, then the moved dots on top (a moved dot's resting place is drawn too: it is a tiny dot, the moved one covers it)
      ctx.fillStyle = `rgba(${colors.rest}, ${REST_ALPHA})`;
      ctx.beginPath();
      for (let y = GRID / 2; y < h; y += GRID) {
        for (let x = GRID / 2; x < w; x += GRID) {
          if (!moved.has(Math.floor(y / GRID) * cols + Math.floor(x / GRID))) ctx.rect(x - REST_RADIUS, y - REST_RADIUS, REST_RADIUS * 2, REST_RADIUS * 2);
        }
      }
      ctx.fill();

      ctx.fillStyle = `rgb(${colors.hot})`;
      for (const [key, d] of moved) {
        const cx = (key % cols) * GRID + GRID / 2;
        const cy = Math.floor(key / cols) * GRID + GRID / 2;
        const dist = Math.hypot(cx - px, cy - py);
        const f = pointerActive ? influence(dist) : 0;
        const dirX = dist > 0.001 ? (cx - px) / dist : 0;
        const dirY = dist > 0.001 ? (cy - py) / dist : 0;
        const alive = stepDot(d, dirX * f * MAX_PUSH, dirY * f * MAX_PUSH, f, dt);
        if (!alive) {
          moved.delete(key);
          continue;
        }
        busy = true;
        const radius = REST_RADIUS + d.glow * 2.4;
        ctx.globalAlpha = REST_ALPHA + d.glow * (0.95 - REST_ALPHA);
        ctx.beginPath();
        ctx.arc(cx + d.ox, cy + d.oy, radius, 0, Math.PI * 2);
        ctx.fill();
      }

      // the trail: short segments that fade out
      if (trail.length > 1) {
        ctx.strokeStyle = `rgb(${colors.hot})`;
        ctx.lineCap = "round";
        for (let i = 1; i < trail.length; i += 1) {
          const a = trail[i - 1]!;
          const b = trail[i]!;
          const life = 1 - (now - b.t) / TRAIL_MS;
          ctx.globalAlpha = Math.max(0, 0.45 * life);
          ctx.lineWidth = 1 + 2.2 * life;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;

      // keep going only while something is moving or the pointer has just moved: otherwise this was the last frame
      if (busy || pointerActive) raf = requestAnimationFrame(frame);
      else last = 0;
    };

    const start = () => {
      if (!raf && !document.hidden) raf = requestAnimationFrame(frame);
    };
    const onMove = (e: PointerEvent) => {
      px = e.clientX;
      py = e.clientY;
      lastMove = performance.now();
      trail.push({ x: px, y: py, t: lastMove });
      if (trail.length > 40) trail.shift();
      start();
    };
    const onLeave = () => {
      px = -1e4;
      py = -1e4;
    };
    const onVisibility = () => {
      if (document.hidden) {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        last = 0;
      } else if (moved.size > 0 || trail.length > 0) start();
    };
    // a theme change repaints the resting grid in the other colour
    const mo = new MutationObserver(() => {
      colors = readDotColors();
      if (!raf) drawRest();
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });

    resize();
    window.addEventListener("resize", resize);
    if (interactive) {
      document.addEventListener("pointermove", onMove, { passive: true }); // the one pointer listener of the whole field
      document.documentElement.addEventListener("pointerleave", onLeave);
      document.addEventListener("visibilitychange", onVisibility);
    }
    return () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      mo.disconnect();
      window.removeEventListener("resize", resize);
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduced]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      data-testid="dot-field"
      data-static={reduced ? "" : undefined}
      className="pointer-events-none fixed inset-0 z-0"
    />
  );
}
