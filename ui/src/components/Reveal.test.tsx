import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { placeElements, setReducedMotion } from "@/test/motion";
import { Reveal } from "@/components/Reveal";
import { SmoothScrollProvider, useRegisterScroller } from "@/components/SmoothScroll";

type TriggerConfig = { trigger: Element; scroller?: Element; start: string; once: boolean; onEnter: () => void; onLeave: () => void };
const triggerConfig = () => vi.mocked(ScrollTrigger.create).mock.calls.at(-1)![0] as unknown as TriggerConfig;

describe("Reveal", () => {
  let restore = () => {};
  let unplace = () => {};
  beforeEach(() => {
    unplace = placeElements(5000); // below the fold: nothing is in view until a scroll
  });
  afterEach(() => {
    restore();
    unplace();
  });

  it("hides the children only through GSAP and shows them with one staggered tween when it scrolls into view", () => {
    render(<Reveal data-testid="r"><p>first</p><p>second</p></Reveal>);
    const container = screen.getByTestId("r");

    // the content is in the DOM the whole time (GSAP is the only thing that hides it)
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();

    // hidden state is set inside a gsap context, on the children, only after the trigger was created
    expect(gsap.context).toHaveBeenCalledTimes(1);
    expect(gsap.set).toHaveBeenCalledTimes(1);
    const [targets, from] = vi.mocked(gsap.set).mock.calls[0]!;
    expect(targets).toEqual([screen.getByText("first"), screen.getByText("second")]);
    expect(from).toEqual({ opacity: 0, y: 16 });
    expect(ScrollTrigger.create).toHaveBeenCalledTimes(1);
    const cfg = triggerConfig();
    expect(cfg.trigger).toBe(container);
    expect(cfg.once).toBe(true);
    expect(cfg.start).toContain("clamp(");
    expect(gsap.to).not.toHaveBeenCalled(); // not before it is in view

    cfg.onEnter();
    expect(gsap.to).toHaveBeenCalledTimes(1);
    const [toTargets, toVars] = vi.mocked(gsap.to).mock.calls[0]! as [Element[], Record<string, unknown>];
    expect(toTargets).toEqual(targets);
    expect(toVars).toMatchObject({ opacity: 1, y: 0, stagger: 0.08 });
    expect(String(toVars.clearProps)).toContain("transform");

    cfg.onEnter();
    cfg.onLeave(); // firing again (or leaving past the end) does not start a second tween
    expect(gsap.to).toHaveBeenCalledTimes(1);
  });

  it("reveals content that is already in view at once, even though ScrollTrigger would not fire for it", () => {
    // regression: near the top of the page the clamped start is 0 and ScrollTrigger does not fire at scroll 0
    unplace();
    unplace = placeElements(100);
    render(<Reveal><p>top of the page</p></Reveal>);
    expect(gsap.set).toHaveBeenCalledTimes(1);
    expect(gsap.to).toHaveBeenCalledTimes(1);
  });

  it("reveals content that is already past its start point instead of leaving it hidden", () => {
    render(<Reveal><p>late</p></Reveal>);
    triggerConfig().onLeave();
    expect(gsap.to).toHaveBeenCalledTimes(1);
  });

  it("animates the element itself with `self`, and with the trigger `mount` it starts at once without a ScrollTrigger", () => {
    render(<Reveal self trigger="mount" data-testid="s">x</Reveal>);
    expect(ScrollTrigger.create).not.toHaveBeenCalled();
    expect(vi.mocked(gsap.set).mock.calls[0]![0]).toEqual([screen.getByTestId("s")]);
    expect(gsap.to).toHaveBeenCalledTimes(1);
  });

  it("kills the tween and the trigger and reverts the styles on unmount", () => {
    const { unmount } = render(<Reveal><p>x</p></Reveal>);
    const trigger = vi.mocked(ScrollTrigger.create).mock.results[0]!.value as { kill: ReturnType<typeof vi.fn> };
    triggerConfig().onEnter();
    const tween = vi.mocked(gsap.to).mock.results[0]!.value as { kill: ReturnType<typeof vi.fn> };
    const ctx = vi.mocked(gsap.context).mock.results[0]!.value as { revert: ReturnType<typeof vi.fn> };

    unmount();
    expect(trigger.kill).toHaveBeenCalledTimes(1);
    expect(tween.kill).toHaveBeenCalledTimes(1);
    expect(ctx.revert).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the visitor prefers reduced motion: nothing hidden, no trigger, no tween", () => {
    restore = setReducedMotion(true);
    render(<Reveal><p>still here</p></Reveal>);
    expect(screen.getByText("still here")).toBeInTheDocument();
    expect(gsap.context).not.toHaveBeenCalled();
    expect(gsap.set).not.toHaveBeenCalled();
    expect(ScrollTrigger.create).not.toHaveBeenCalled();
    expect(gsap.to).not.toHaveBeenCalled();
  });

  it("uses the scrolling pane as the ScrollTrigger scroller under the provider (and waits until the pane is known)", () => {
    function Pane() {
      const register = useRegisterScroller();
      return (
        <div ref={register} data-testid="pane">
          <div><Reveal><p>inside</p></Reveal></div>
        </div>
      );
    }
    render(<SmoothScrollProvider><Pane /></SmoothScrollProvider>);
    // no trigger was ever created against the window: the first one already has the pane as its scroller
    const configs = vi.mocked(ScrollTrigger.create).mock.calls.map((c) => c[0] as unknown as TriggerConfig);
    expect(configs.length).toBeGreaterThan(0);
    for (const c of configs) expect(c.scroller).toBe(screen.getByTestId("pane"));
  });
});
