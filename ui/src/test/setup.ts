import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.clearAllMocks(); // forget recorded calls between tests (the mock implementations stay)
});

// jsdom lacks these browser APIs that Radix, motion and the layout hooks use
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= function scrollIntoView() {};
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => {};
window.matchMedia ??= ((q: string) => ({
  matches: false, media: q, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

/*
 * GSAP, ScrollTrigger and Lenis need a real layout engine and animation clock, which jsdom does not have. They are
 * replaced by recording mocks for every test: nothing animates, nothing is hidden (content stays visible in the DOM),
 * and the tests can check what the motion components asked GSAP and Lenis to do (see Reveal.test.tsx,
 * CountUp.test.tsx and SmoothScroll.test.tsx).
 */
vi.mock("gsap", () => {
  const gsap = {
    registerPlugin: vi.fn(),
    // gsap.context(fn, scope): runs fn and returns an object whose revert() undoes everything fn created
    context: vi.fn((fn?: () => void) => {
      fn?.();
      return { revert: vi.fn(), kill: vi.fn(), add: vi.fn((f?: () => void) => f?.()) };
    }),
    set: vi.fn(),
    // a count-up style tween (a plain object with an onComplete callback) finishes at once, so its final text is in the DOM
    to: vi.fn((target: unknown, vars?: Record<string, unknown>) => {
      if (target && !Array.isArray(target) && typeof vars?.onComplete === "function") {
        (target as Record<string, unknown>).v = vars.v;
        (vars.onUpdate as (() => void) | undefined)?.();
        (vars.onComplete as () => void)();
      }
      return { kill: vi.fn() };
    }),
    from: vi.fn(() => ({ kill: vi.fn() })),
    fromTo: vi.fn(() => ({ kill: vi.fn() })),
    killTweensOf: vi.fn(),
    ticker: { add: vi.fn(), remove: vi.fn(), lagSmoothing: vi.fn() },
  };
  return { default: gsap, gsap };
});

vi.mock("gsap/ScrollTrigger", () => ({
  ScrollTrigger: {
    create: vi.fn(() => ({ kill: vi.fn() })),
    update: vi.fn(),
    refresh: vi.fn(),
    getAll: vi.fn(() => []),
    defaults: vi.fn(),
    kill: vi.fn(),
  },
}));

vi.mock("lenis", () => {
  class Lenis {
    static instances: Lenis[] = [];
    options: Record<string, unknown>;
    on = vi.fn((_event: string, _cb: () => void) => () => {});
    off = vi.fn();
    raf = vi.fn();
    destroy = vi.fn();
    constructor(options: Record<string, unknown> = {}) {
      this.options = options;
      Lenis.instances.push(this);
    }
  }
  return { default: Lenis };
});
