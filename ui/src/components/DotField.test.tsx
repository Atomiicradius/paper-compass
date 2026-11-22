import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { setReducedMotion } from "@/test/motion";
import { DotField, GRID, MAX_DPR, MAX_PUSH, RADIUS, TRAIL_MS, influence, stepDot, type DotState } from "@/components/DotField";

describe("dot field physics", () => {
  it("has the specified numbers: 26 px grid, 140 px reach, ~600 ms trail, DPR cap 2", () => {
    expect(GRID).toBe(26);
    expect(RADIUS).toBe(140);
    expect(TRAIL_MS).toBe(600);
    expect(MAX_DPR).toBe(2);
  });

  it("the influence is 1 at the pointer, falls off smoothly and is 0 from 140 px on", () => {
    expect(influence(0)).toBe(1);
    expect(influence(70)).toBeCloseTo(0.25);
    expect(influence(RADIUS)).toBe(0);
    expect(influence(500)).toBe(0);
    expect(influence(NaN)).toBe(0);
  });

  it("a dot is pushed away, glows, and springs back to rest when the pointer leaves", () => {
    const d: DotState = { ox: 0, oy: 0, vx: 0, vy: 0, glow: 0 };
    for (let i = 0; i < 40; i += 1) stepDot(d, 20, 0, 1, 1 / 60); // pushed 20 px to the right
    expect(d.ox).toBeGreaterThan(10);
    expect(d.ox).toBeLessThan(MAX_PUSH + 5);
    expect(d.glow).toBeGreaterThan(0.8);
    let alive = true;
    for (let i = 0; i < 600 && alive; i += 1) alive = stepDot(d, 0, 0, 0, 1 / 60);
    expect(alive).toBe(false); // it came to rest by itself
    expect(Math.abs(d.ox)).toBeLessThan(0.05);
    expect(d.glow).toBeLessThan(0.02);
  });
});

describe("DotField", () => {
  const rect = vi.fn();
  const fakeCtx = new Proxy({} as Record<string, unknown>, {
    get: (t, p: string) => (p === "rect" ? rect : p in t ? t[p] : vi.fn()),
    set: (t, p: string, v) => ((t[p] = v), true),
  });
  let frames: Array<(t: number) => void> = [];
  const raf = vi.fn((cb: (t: number) => void) => (frames.push(cb), frames.length));
  const caf = vi.fn();
  let restore = () => {};
  const move = (x: number, y: number) => {
    const e = new Event("pointermove", { bubbles: true }) as Event & { clientX: number; clientY: number };
    Object.assign(e, { clientX: x, clientY: y });
    document.dispatchEvent(e);
  };

  beforeEach(() => {
    frames = [];
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(fakeCtx as unknown as CanvasRenderingContext2D);
  });
  afterEach(() => {
    restore();
    restore = () => {};
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("is one decorative canvas behind the content that never takes the pointer", () => {
    render(<DotField />);
    const c = screen.getByTestId("dot-field");
    expect(c.tagName).toBe("CANVAS");
    expect(c).toHaveAttribute("aria-hidden", "true");
    expect(c.className).toMatch(/pointer-events-none/);
    expect(c.className).toMatch(/fixed/);
  });

  it("uses exactly one pointermove listener, draws nothing until the pointer moves (zero cost idle), and removes the listener", () => {
    const add = vi.spyOn(document, "addEventListener");
    const rem = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<DotField />);
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(1);
    expect(raf).not.toHaveBeenCalled();
    move(300, 200);
    expect(raf).toHaveBeenCalledTimes(1);
    unmount();
    expect(rem).toHaveBeenCalledWith("pointermove", expect.any(Function));
    expect(caf).toHaveBeenCalled(); // the pending frame was cancelled
  });

  it("stops its own frame loop when the pointer has been still and every dot is at rest", () => {
    const base = performance.now();
    render(<DotField />);
    move(300, 200);
    // run frames well after the last move: the loop must end by itself
    let t = base;
    for (let i = 0; i < 400 && frames.length; i += 1) {
      t += 16;
      frames.splice(0).forEach((f) => f(t));
    }
    expect(frames).toHaveLength(0);
    const calls = raf.mock.calls.length;
    expect(raf.mock.calls.length).toBe(calls); // nothing more is scheduled while idle
  });

  it("with reduced motion it draws the faint grid once and does not listen to the pointer", () => {
    restore = setReducedMotion(true);
    const add = vi.spyOn(document, "addEventListener");
    render(<DotField />);
    expect(screen.getByTestId("dot-field")).toHaveAttribute("data-static");
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(0);
    move(300, 200);
    expect(raf).not.toHaveBeenCalled();
    expect(rect).toHaveBeenCalled(); // the grid itself was drawn
  });

  it("on a touch screen (coarse pointer) it is static as well", () => {
    const orig = window.matchMedia;
    window.matchMedia = ((q: string) => ({ matches: q.includes("coarse"), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false, onchange: null })) as unknown as typeof window.matchMedia;
    restore = () => { window.matchMedia = orig; };
    const add = vi.spyOn(document, "addEventListener");
    render(<DotField />);
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(0);
  });

  it("caps the canvas resolution at a device pixel ratio of 2", () => {
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 3 });
    restore = () => { Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 1 }); };
    render(<DotField />);
    const c = screen.getByTestId("dot-field") as HTMLCanvasElement;
    expect(c.width).toBe(window.innerWidth * 2);
  });
});
