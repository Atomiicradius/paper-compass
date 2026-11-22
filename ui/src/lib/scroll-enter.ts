import { ScrollTrigger } from "@/lib/gsap";

export interface EnterOptions {
  /** "scroll": fire when the element scrolls into view. "mount": fire at once (for things outside the scrolling pane, e.g. the header or a drawer). */
  trigger?: "scroll" | "mount";
  /** the element that scrolls (null: the window) */
  scroller?: HTMLElement | null;
  /** ScrollTrigger start position. `clamp()` keeps a trigger near the end of the page reachable. */
  start?: string;
}

/**
 * Call `fire` once, when `el` scrolls into view (or at once with trigger "mount"). Returns a cleanup that kills the
 * ScrollTrigger and makes sure `fire` can no longer run.
 *
 * Content is never left hidden: the trigger also fires when the element is already past its start point
 * (`onLeave`, and a check of `progress` right after creation), so only content still below the fold waits.
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
  if (st && (st.progress ?? 0) > 0) run();
  return () => {
    done = true;
    st?.kill?.();
  };
}
