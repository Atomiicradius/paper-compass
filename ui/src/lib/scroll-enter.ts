import { ScrollTrigger } from "@/lib/gsap";

export interface EnterOptions {
  /** "scroll": fire when the element scrolls into view. "mount": fire at once (for things outside the scrolling pane, e.g. the header or a drawer). */
  trigger?: "scroll" | "mount";
  /** the element that scrolls (null: the window) */
  scroller?: HTMLElement | null;
  /** ScrollTrigger start position. `clamp()` keeps a trigger near the end of the page reachable. */
  start?: string;
}

/** How far down the scroller's viewport an element's top must be to count as "in view" (the same 92% as the default start). */
const IN_VIEW_RATIO = 0.92;

/**
 * Is the element already in view, or already scrolled past? ScrollTrigger cannot tell for content near the top of the
 * page: with `clamp()` its start is 0 there, and it does not fire when the scroll position equals the start exactly,
 * so such content would stay hidden until the first scroll. This geometric check covers that case.
 */
function alreadyInView(el: Element, scroller: HTMLElement | null): boolean {
  const r = el.getBoundingClientRect();
  const box = scroller ? scroller.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
  return r.top < box.top + (box.bottom - box.top) * IN_VIEW_RATIO;
}

/**
 * Call `fire` once, when `el` scrolls into view (or at once with trigger "mount"). Returns a cleanup that kills the
 * ScrollTrigger and makes sure `fire` can no longer run.
 *
 * Content is never left hidden: the trigger also fires when the element is already past its start point
 * (`onLeave`, a check of `progress`, and the geometric check above), so only content still below the fold waits.
 */
export function onceInView(el: Element, { trigger = "scroll", scroller = null, start = "clamp(top 92%)" }: EnterOptions, fire: () => void): () => void {
  let done = false;
  const run = () => {
    if (done) return;
    done = true;
    fire();
  };
  if (trigger === "mount") {
    run();
    return () => {
      done = true;
    };
  }
  const st = ScrollTrigger.create({
    trigger: el,
    scroller: scroller ?? undefined,
    start,
    once: true,
    onEnter: run,
    onEnterBack: run,
    onLeave: run,
  });
  if ((st && (st.progress ?? 0) > 0) || alreadyInView(el, scroller)) run();
  return () => {
    done = true;
    st?.kill?.();
  };
}
