import { vi } from "vitest";

/** Test helper: make `prefers-reduced-motion` true or false. Returns a function that restores the previous setting. */
export function setReducedMotion(reduce: boolean): () => void {
  const previous = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  return () => {
    window.matchMedia = previous;
  };
}

/**
 * Test helper: jsdom has no layout (every rectangle is 0), so say where elements are. `top` 5000 puts every element far
 * below a 768 px viewport (it must wait for a scroll); `top` 100 puts it in view. Returns a function that undoes it.
 */
export function placeElements(top: number): () => void {
  const spy = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(
    () => ({ x: 0, y: top, top, bottom: top + 100, left: 0, right: 100, width: 100, height: 100, toJSON: () => ({}) }) as DOMRect,
  );
  return () => spy.mockRestore();
}
