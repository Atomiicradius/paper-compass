import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ParticleSphere, { FADE_MS, POINT_COUNT, fibonacciSphere, perspective, rotate } from "@/components/story/ParticleSphere";

describe("sphere geometry", () => {
  it("has about 1,200 points, all on the unit sphere and spread over both hemispheres", () => {
    expect(POINT_COUNT).toBe(1200);
    const p = fibonacciSphere(POINT_COUNT);
    expect(p.length).toBe(POINT_COUNT * 3);
    let north = 0;
    for (let i = 0; i < POINT_COUNT; i += 1) {
      expect(Math.hypot(p[i * 3]!, p[i * 3 + 1]!, p[i * 3 + 2]!)).toBeCloseTo(1, 4);
      if (p[i * 3 + 1]! > 0) north += 1;
    }
    expect(Math.abs(north - POINT_COUNT / 2)).toBeLessThanOrEqual(2);
  });

  it("rotation keeps the length, and points in front are scaled up by the perspective", () => {
    const [x, y, z] = rotate(0.6, 0.3, Math.sqrt(1 - 0.45), 0.8, 0.4);
    expect(Math.hypot(x, y, z)).toBeCloseTo(1, 5);
    expect(perspective(1)).toBeGreaterThan(perspective(0));
    expect(perspective(0)).toBeGreaterThan(perspective(-1));
    expect(FADE_MS).toBeGreaterThan(0);
  });
});

describe("ParticleSphere", () => {
  const arc = vi.fn();
  const fakeCtx = new Proxy({} as Record<string, unknown>, {
    get: (t, p: string) => (p === "arc" ? arc : p in t ? t[p] : vi.fn()),
    set: (t, p: string, v) => ((t[p] = v), true),
  });
  let frames: Array<(t: number) => void> = [];
  const raf = vi.fn((cb: (t: number) => void) => (frames.push(cb), frames.length));
  const caf = vi.fn();
  const disconnect = vi.fn();
  const sizes: Array<[object, string, PropertyDescriptor | undefined]> = [];
  const define = (key: string, value: number) => {
    sizes.push([HTMLElement.prototype, key, Object.getOwnPropertyDescriptor(HTMLElement.prototype, key)]);
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  };

  beforeEach(() => {
    frames = [];
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);
    vi.stubGlobal("ResizeObserver", class { observe = vi.fn(); unobserve = vi.fn(); disconnect = disconnect; });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(fakeCtx as unknown as CanvasRenderingContext2D);
    define("clientWidth", 1000);
    define("clientHeight", 600);
  });
  afterEach(() => {
    for (const [o, k, d] of sizes.splice(0)) d ? Object.defineProperty(o, k, d) : delete (o as Record<string, unknown>)[k];
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("is decoration, draws one frame of ~1,200 points in a few batches, and keeps animating while visible", () => {
    render(<ParticleSphere visible />);
    expect(screen.getByTestId("particle-sphere")).toHaveAttribute("aria-hidden", "true");
    arc.mockClear();
    frames.splice(0).forEach((f) => f(1000));
    expect(arc.mock.calls.length).toBe(POINT_COUNT); // every point once
    expect(frames).toHaveLength(1); // the next frame is queued
  });

  it("fades out when not visible and then stops its loop; it wakes again when visible", () => {
    const { rerender } = render(<ParticleSphere visible />);
    frames.splice(0).forEach((f) => f(1000));
    rerender(<ParticleSphere visible={false} />);
    let t = 1000;
    for (let i = 0; i < 400 && frames.length; i += 1) {
      t += 16;
      frames.splice(0).forEach((f) => f(t));
    }
    expect(frames).toHaveLength(0); // faded out and stopped
    rerender(<ParticleSphere visible />);
    expect(frames).toHaveLength(1);
  });

  it("still mode draws exactly one frame and registers no pointer listener", () => {
    const add = vi.spyOn(document, "addEventListener");
    render(<ParticleSphere visible still />);
    frames.splice(0).forEach((f) => f(1000));
    expect(frames).toHaveLength(0);
    expect(arc.mock.calls.length).toBeGreaterThan(0);
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(0);
  });

  it("cleans up on unmount: the frame is cancelled, the observer disconnected and the listeners removed", () => {
    const rem = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<ParticleSphere visible />);
    unmount();
    expect(caf).toHaveBeenCalled();
    expect(disconnect).toHaveBeenCalled();
    expect(rem).toHaveBeenCalledWith("pointermove", expect.any(Function));
    expect(rem).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });
});
