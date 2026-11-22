import { useEffect } from "react";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";

/**
 * The cursor-following spotlight of the glass cards. ONE listener on the document (not one per card): it finds the glass
 * card under the pointer, and the cards around it, and writes the pointer position into their --mx and --my variables;
 * the `.glass:hover` rule in index.css turns that into a soft radial highlight. At most one write per animation frame.
 * Returns a function that removes the listener.
 */
export function installSpotlight(doc: Document = document): () => void {
  let frame = 0;
  let last: PointerEvent | null = null;

  const apply = () => {
    frame = 0;
    const e = last;
    if (!e) return;
    let card = (e.target as Element | null)?.closest?.(".glass") as HTMLElement | null;
    while (card) {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${Math.round(e.clientX - r.left)}px`);
      card.style.setProperty("--my", `${Math.round(e.clientY - r.top)}px`);
      card = card.parentElement?.closest?.(".glass") as HTMLElement | null; // a glass card inside another one
    }
  };
  const onMove = (e: PointerEvent) => {
    last = e;
    if (!frame) frame = requestAnimationFrame(apply);
  };

  doc.addEventListener("pointermove", onMove, { passive: true });
  return () => {
    doc.removeEventListener("pointermove", onMove);
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  };
}

/** Install the spotlight for as long as the component is mounted; not at all with reduced motion. */
export function useSpotlight(): void {
  const reduced = usePrefersReducedMotion();
  useEffect(() => (reduced ? undefined : installSpotlight()), [reduced]);
}
