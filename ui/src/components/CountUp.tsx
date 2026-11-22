import { useLayoutEffect, useRef } from "react";
import { gsap } from "@/lib/gsap";
import { onceInView, type EnterOptions } from "@/lib/scroll-enter";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";
import { useScrollTarget } from "@/components/SmoothScroll";

export interface CountUpProps extends Omit<EnterOptions, "scroller"> {
  value: number;
  /** digits after the decimal point (default 0) */
  decimals?: number;
  /** replaces the default `value.toFixed(decimals)`; applied to the final value and to every step */
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}

/**
 * A number that counts up from 0 to `value` when it comes into view.
 *
 * The FINAL value is the element's text from the first render: React renders it, so it is in the DOM for tests,
 * search and screen readers, and with `prefers-reduced-motion: reduce` it is shown as it is, with no animation.
 * The text only changes once the count starts (when the number scrolls into view). While the count runs, only the data of that one text node is stepped through intermediate numbers (it is the node
 * React manages, so later renders still update it); the last step is the exact final text; and aria-label and
 * data-value always hold the final value, so assistive technology never reads an intermediate number. The tween and
 * the trigger are killed on unmount or when the value changes, and the final text is put back.
 */
export function CountUp({ value, decimals = 0, format, duration = 1.1, className, trigger = "scroll", start }: CountUpProps) {
  const formatRef = useRef(format);
  useLayoutEffect(() => {
    formatRef.current = format; // an inline function must not restart the count on every render
  });
  const fmt = (n: number) => (format ? format(n) : n.toFixed(decimals));
  const final = fmt(value);

  const ref = useRef<HTMLSpanElement>(null);
  const reduced = usePrefersReducedMotion();
  const { scroller, ready } = useScrollTarget();

  useLayoutEffect(() => {
    const el = ref.current;
    const node = el?.firstChild;
    if (!el || !node || reduced) return;
    if (trigger === "scroll" && !ready) return;
    const show = (n: number) => {
      node.nodeValue = formatRef.current ? formatRef.current(n) : n.toFixed(decimals);
    };

    let tween: { kill: () => void } | undefined;
    let stop: (() => void) | undefined;
    const proxy = { v: 0 };
    const ctx = gsap.context(() => {
      stop = onceInView(el, { trigger, scroller, start }, () => {
        show(0); // the text leaves its final value only at the moment the count really starts
        tween = gsap.to(proxy, {
          v: value,
          duration,
          ease: "power2.out",
          onUpdate: () => show(proxy.v),
          onComplete: () => show(value),
        });
      });
    }, el);

    return () => {
      stop?.();
      tween?.kill();
      ctx.revert();
      // React has already written the latest final value to data-value: never leave an intermediate number behind
      const latest = el.getAttribute("data-value");
      if (latest !== null) node.nodeValue = latest;
    };
  }, [reduced, ready, scroller, value, decimals, duration, trigger, start]);

  return (
    <span ref={ref} className={className} role="img" aria-label={final} data-value={final}>
      {final}
    </span>
  );
}
