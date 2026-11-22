import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import NetworkCanvas, { allocateNodes, buildScene, canvasStateForStep, MAX_DPR, MAX_NODES, mulberry32 } from "@/components/story/NetworkCanvas";

const REAL_SIZES = [420, 398, 135, 69, 38, 37, 19];

describe("allocateNodes", () => {
  it("never draws more than 300 dots, gives every group at least one, and follows the real sizes", () => {
    const counts = allocateNodes(REAL_SIZES);
    const sum = counts.reduce((a, b) => a + b, 0);
    expect(sum).toBeLessThanOrEqual(MAX_NODES);
    expect(sum).toBeGreaterThanOrEqual(MAX_NODES - 1);
    expect(counts).toHaveLength(7);
    expect(Math.min(...counts)).toBeGreaterThanOrEqual(1);
    // the bigger the real cluster, the more dots (the order of the sizes is kept)
    for (let i = 1; i < counts.length; i += 1) expect(counts[i - 1]!).toBeGreaterThanOrEqual(counts[i]!);
    expect(counts[0]! / counts[2]!).toBeGreaterThan(2.5); // 420 versus 135 is about 3.1
  });

  it("caps the total however many groups or however large the corpus", () => {
    expect(allocateNodes(Array.from({ length: 500 }, () => 10)).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(MAX_NODES);
    expect(allocateNodes([1_000_000, 5, 5]).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(MAX_NODES);
    expect(allocateNodes([1_000_000, 5, 5]).every((c) => c >= 1)).toBe(true);
  });

  it("falls back to one neutral decorative group when there are no cluster sizes", () => {
    expect(allocateNodes([])).toEqual([120]);
    expect(allocateNodes([0, NaN, -3])).toEqual([120]);
  });
});

describe("canvasStateForStep", () => {
  it("has the six looks, in order, across the eight steps", () => {
    const states = Array.from({ length: 8 }, (_, i) => canvasStateForStep(i));
    expect(states).toEqual(["scattered", "time", "time", "clusters", "lines", "pair", "pulse", "pulse"]);
    expect(new Set(states).size).toBe(6);
    expect(canvasStateForStep(-3)).toBe("scattered");
    expect(canvasStateForStep(99)).toBe("pulse");
  });
});

describe("buildScene", () => {
  it("is the same picture every time and keeps the dots on the canvas", () => {
    const counts = allocateNodes(REAL_SIZES);
    const a = buildScene(counts, 1200, 800);
    const b = buildScene(counts, 1200, 800);
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    expect(a.nodes).toHaveLength(counts.reduce((x, y) => x + y, 0));
    for (const n of a.nodes) {
      for (const [x, y] of [[n.sx, n.sy], [n.tx, n.ty], [n.cx, n.cy]] as const) {
        expect(x).toBeGreaterThan(-20);
        expect(x).toBeLessThan(1220);
        expect(y).toBeGreaterThan(-20);
        expect(y).toBeLessThan(820);
      }
    }
    expect(a.pair).not.toBeNull();
    expect(a.pair![0]).not.toBe(a.pair![1]);
  });

  it("has no highlighted pair when there is only one group, and does not fail", () => {
    expect(buildScene([120], 800, 600).pair).toBeNull();
  });

  it("mulberry32 is deterministic and in [0, 1)", () => {
    const r1 = mulberry32(7);
    const r2 = mulberry32(7);
    const xs = Array.from({ length: 50 }, () => r1());
    expect(xs).toEqual(Array.from({ length: 50 }, () => r2()));
    expect(xs.every((x) => x >= 0 && x < 1)).toBe(true);
  });
});

describe("NetworkCanvas", () => {
  const arc = vi.fn();
  const fakeCtx = new Proxy({} as Record<string, unknown>, {
    get: (t, p: string) => (p === "arc" ? arc : p in t ? t[p] : vi.fn()),
    set: (t, p: string, v) => ((t[p] = v), true),
  });
  const disconnect = vi.fn();
  let frame: ((t: number) => void) | null = null;
  const raf = vi.fn((cb: (t: number) => void) => ((frame = cb), 1));
  const caf = vi.fn();
  const restoreProps: Array<() => void> = [];
  const define = (obj: object, key: string, value: unknown) => {
    const had = Object.getOwnPropertyDescriptor(obj, key);
    Object.defineProperty(obj, key, { configurable: true, get: () => value });
    restoreProps.push(() => (had ? Object.defineProperty(obj, key, had) : delete (obj as Record<string, unknown>)[key]));
  };

  beforeEach(() => {
    frame = null;
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", caf);
    vi.stubGlobal("ResizeObserver", class { observe = vi.fn(); unobserve = vi.fn(); disconnect = disconnect; });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(fakeCtx as unknown as CanvasRenderingContext2D);
    define(HTMLElement.prototype, "clientWidth", 1000);
    define(HTMLElement.prototype, "clientHeight", 600);
    define(window, "devicePixelRatio", 3);
    define(document, "hidden", false);
  });
  afterEach(() => {
    restoreProps.splice(0).forEach((f) => f());
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("is marked as an illustration, is hidden from assistive technology, and draws at most 300 dots per frame", () => {
    const { container } = render(<NetworkCanvas step={3} groupSizes={REAL_SIZES} />);
    expect(screen.getByText("ILLUSTRATION · NOT TO SCALE")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(frame).not.toBeNull();
    arc.mockClear();
    frame!(1000);
    expect(arc.mock.calls.length).toBeGreaterThan(0);
    // one neutral dot and at most one coloured dot per node, plus a few halos: never more than 2 x 300 + the pulse halos
    expect(arc.mock.calls.length).toBeLessThanOrEqual(MAX_NODES * 2 + 2);
  });

  it("caps the device pixel ratio at 2", () => {
    render(<NetworkCanvas step={0} groupSizes={REAL_SIZES} />);
    const canvas = screen.getByTestId("network-canvas") as HTMLCanvasElement;
    expect(MAX_DPR).toBe(2);
    expect(canvas.width).toBe(1000 * 2); // the screen says 3, the canvas uses 2
    expect(canvas.height).toBe(600 * 2);
  });

  it("stops its loop while the tab is hidden and starts it again when it is shown", () => {
    render(<NetworkCanvas step={0} groupSizes={REAL_SIZES} />);
    raf.mockClear();
    caf.mockClear();
    define(document, "hidden", true);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(caf).toHaveBeenCalled();
    frame!(2000); // a frame that was already queued does nothing and queues no more
    expect(raf).not.toHaveBeenCalled();
    define(document, "hidden", false);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(raf).toHaveBeenCalledTimes(1);
  });

  it("cleans up on unmount: cancels the frame, stops watching the size, removes the listener", () => {
    const remove = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<NetworkCanvas step={0} groupSizes={REAL_SIZES} />);
    caf.mockClear();
    unmount();
    expect(caf).toHaveBeenCalled();
    expect(disconnect).toHaveBeenCalled();
    expect(remove).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });

  it("still draws, as one neutral group, when no cluster sizes are available", () => {
    render(<NetworkCanvas step={5} groupSizes={[]} />);
    arc.mockClear();
    frame!(1000);
    expect(arc.mock.calls.length).toBeGreaterThan(0);
    expect(arc.mock.calls.length).toBeLessThanOrEqual(MAX_NODES * 2 + 2);
  });
});
