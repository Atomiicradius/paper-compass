import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import Lenis from "lenis";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";

/**
 * Smooth scrolling for the app's scroll area.
 *
 * The page is a fixed-height layout whose centre pane (`<main>`) scrolls, not the window, so Lenis is given that
 * element as its wrapper: the pane registers itself with `useRegisterScroller()` (a ref callback).
 *
 * Lenis and GSAP ScrollTrigger share ONE clock: Lenis does not run its own requestAnimationFrame loop
 * (`autoRaf: false`); a single callback on `gsap.ticker` calls `lenis.raf()`, and every Lenis scroll event calls
 * `ScrollTrigger.update`. With `prefers-reduced-motion: reduce` Lenis is not created at all, so the browser's
 * native scrolling is used. Anything that scrolls on its own inside the pane (drawers, checklists, the graph
 * canvas) carries `data-lenis-prevent` so Lenis leaves its wheel and touch events alone.
 */
interface ScrollerContext {
  scroller: HTMLElement | null;
  setScroller: (el: HTMLElement | null) => void;
  hasProvider: boolean;
}

const Ctx = createContext<ScrollerContext>({ scroller: null, setScroller: () => {}, hasProvider: false });

/** The element that scrolls the page content (null before it mounts, or without a provider). */
export function useScroller(): HTMLElement | null {
  return useContext(Ctx).scroller;
}

/**
 * What scroll-triggered motion needs: the scrolling element, and whether it is known yet. Under the provider the pane
 * registers itself right after the first render, so `ready` is false for that one render and scroll triggers wait for
 * it (a trigger created against the window would never fire for content that scrolls inside the pane). Without a
 * provider (tests, or a page that scrolls normally) it is ready at once and ScrollTrigger uses the window.
 */
export function useScrollTarget(): { scroller: HTMLElement | null; ready: boolean } {
  const { scroller, hasProvider } = useContext(Ctx);
  return { scroller, ready: !hasProvider || scroller !== null };
}

/** A ref callback for the one scrolling element of the page. */
export function useRegisterScroller(): (el: HTMLElement | null) => void {
  return useContext(Ctx).setScroller;
}

export function SmoothScrollProvider({ children }: { children: ReactNode }) {
  const [scroller, setScroller] = useState<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (!scroller || reduced) return;
    const content = (scroller.firstElementChild as HTMLElement | null) ?? scroller;
    const lenis = new Lenis({ wrapper: scroller, content, autoRaf: false, lerp: 0.1, smoothWheel: true });
    const onScroll = () => ScrollTrigger.update();
    lenis.on("scroll", onScroll);
    const tick = (time: number) => lenis.raf(time * 1000); // gsap.ticker time is in seconds, Lenis wants milliseconds
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis.off("scroll", onScroll);
      lenis.destroy();
    };
  }, [scroller, reduced]);

  const value = useMemo(() => ({ scroller, setScroller, hasProvider: true }), [scroller]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
