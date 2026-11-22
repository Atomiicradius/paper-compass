import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import Lenis from "lenis";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { setReducedMotion } from "@/test/motion";
import { SmoothScrollProvider, useRegisterScroller, useScroller } from "@/components/SmoothScroll";

// the mocked Lenis class keeps every instance (see src/test/setup.ts)
const instances = () => (Lenis as unknown as { instances: Array<{ options: Record<string, unknown>; on: ReturnType<typeof vi.fn>; raf: ReturnType<typeof vi.fn>; destroy: ReturnType<typeof vi.fn> }> }).instances;

function Pane() {
  const register = useRegisterScroller();
  const scroller = useScroller();
  return (
    <div ref={register} data-testid="pane" data-registered={scroller ? "yes" : "no"}>
      <div data-testid="content">content</div>
    </div>
  );
}

describe("SmoothScrollProvider", () => {
  let restore = () => {};
  beforeEach(() => {
    instances().length = 0;
  });
  afterEach(() => restore());

  it("drives Lenis from the one shared GSAP ticker and connects it to ScrollTrigger", () => {
    restore = setReducedMotion(false);
    const { getByTestId, unmount } = render(<SmoothScrollProvider><Pane /></SmoothScrollProvider>);
    expect(instances()).toHaveLength(1);
    const lenis = instances()[0]!;
    // the scrolling pane is the wrapper and its first child is the content; Lenis has no loop of its own
    expect(lenis.options.wrapper).toBe(getByTestId("pane"));
    expect(lenis.options.content).toBe(getByTestId("content"));
    expect(lenis.options.autoRaf).toBe(false);
    expect(getByTestId("pane").dataset.registered).toBe("yes");

    // exactly one ticker callback, which advances Lenis (gsap seconds -> Lenis milliseconds)
    expect(gsap.ticker.add).toHaveBeenCalledTimes(1);
    const tick = vi.mocked(gsap.ticker.add).mock.calls[0]![0] as (t: number) => void;
    tick(1.5);
    expect(lenis.raf).toHaveBeenCalledWith(1500);

    // every Lenis scroll event updates ScrollTrigger
    expect(lenis.on).toHaveBeenCalledWith("scroll", expect.any(Function));
    const onScroll = lenis.on.mock.calls[0]![1] as () => void;
    onScroll();
    expect(ScrollTrigger.update).toHaveBeenCalledTimes(1);

    // unmounting removes the same ticker callback and destroys Lenis
    unmount();
    expect(gsap.ticker.remove).toHaveBeenCalledWith(tick);
    expect(lenis.destroy).toHaveBeenCalledTimes(1);
  });

  it("does not create Lenis or a ticker callback when the visitor prefers reduced motion", () => {
    restore = setReducedMotion(true);
    const { getByTestId } = render(<SmoothScrollProvider><Pane /></SmoothScrollProvider>);
    expect(instances()).toHaveLength(0);
    expect(gsap.ticker.add).not.toHaveBeenCalled();
    expect(getByTestId("content")).toBeInTheDocument(); // native scrolling, nothing hidden
  });

  it("works without a provider (the hooks fall back to doing nothing)", () => {
    const { getByTestId } = render(<Pane />);
    expect(getByTestId("pane").dataset.registered).toBe("no");
    expect(instances()).toHaveLength(0);
  });
});
