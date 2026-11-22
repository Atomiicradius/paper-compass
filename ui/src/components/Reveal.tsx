import { createElement, useLayoutEffect, useRef, type ElementType, type HTMLAttributes, type ReactNode, type RefObject } from "react";
import { gsap } from "@/lib/gsap";
import { onceInView, type EnterOptions } from "@/lib/scroll-enter";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";
import { useScrollTarget } from "@/components/SmoothScroll";

export interface RevealOptions extends EnterOptions {
  /** animate the element itself instead of its children */
  self?: boolean;
  /** animate the elements matching this selector (inside the element) instead of its direct children */
  selector?: string;
  /** how far (px) the content rises while it fades in */
  y?: number;
  duration?: number;
  /** seconds between one child and the next */
  stagger?: number;
  delay?: number;
}

/**
 * Fade and rise with a stagger, once, when the element comes into view.
 *
 * - The children (or `self`, or `selector`) are hidden with `gsap.set` only once the trigger exists, and shown by one
 *   tween when it fires. The text and elements are in the DOM the whole time, so tests and screen readers see them.
 * - With `prefers-reduced-motion: reduce` nothing is hidden and nothing animates.
 * - Everything is created inside a gsap context; on unmount (or when an option changes) the tween and the
 *   ScrollTrigger are killed and the inline styles are reverted.
 */
export function useReveal<T extends HTMLElement>(ref: RefObject<T | null>, options: RevealOptions = {}): void {
  const { self = false, selector, y = 16, duration = 0.7, stagger = 0.08, delay = 0, trigger = "scroll", start } = options;
  const reduced = usePrefersReducedMotion();
  const { scroller, ready } = useScrollTarget();

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    if (trigger === "scroll" && !ready) return;
    const targets: Element[] = self ? [el] : selector ? Array.from(el.querySelectorAll(selector)) : Array.from(el.children);
    if (targets.length === 0) return;

    let tween: { kill: () => void } | undefined;
    let stop: (() => void) | undefined;
    const ctx = gsap.context(() => {
      gsap.set(targets, { opacity: 0, y });
      stop = onceInView(el, { trigger, scroller, start }, () => {
        tween = gsap.to(targets, { opacity: 1, y: 0, duration, delay, stagger, ease: "power3.out", clearProps: "opacity,transform,translate" });
      });
    }, el);

    return () => {
      stop?.();
      tween?.kill();
      ctx.revert();
    };
  }, [ref, reduced, ready, scroller, self, selector, y, duration, stagger, delay, trigger, start]);
}

type RevealProps = RevealOptions & Omit<HTMLAttributes<HTMLElement>, "children"> & {
  as?: ElementType;
  children?: ReactNode;
};

/** A wrapper element whose children (or itself, with `self`) reveal as described in useReveal. */
export function Reveal({ as = "div", children, self, selector, y, duration, stagger, delay, trigger, scroller, start, ...rest }: RevealProps) {
  const ref = useRef<HTMLElement>(null);
  useReveal(ref, { self, selector, y, duration, stagger, delay, trigger, scroller, start });
  return createElement(as, { ref, ...rest }, children);
}
