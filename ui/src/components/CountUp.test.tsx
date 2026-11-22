import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { setReducedMotion } from "@/test/motion";
import { CountUp } from "@/components/CountUp";

type TriggerConfig = { onEnter: () => void };

describe("CountUp", () => {
  let restore = () => {};
  afterEach(() => restore());

  it("has the final value in the DOM text from the first render, and as its label", () => {
    render(<CountUp value={73.7} decimals={1} />);
    const el = screen.getByText("73.7");
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute("aria-label", "73.7");
    expect(el).toHaveAttribute("data-value", "73.7");
    // it waits for the number to scroll into view, and has not touched the text yet
    expect(ScrollTrigger.create).toHaveBeenCalledTimes(1);
    expect(gsap.to).not.toHaveBeenCalled();
  });

  it("steps the text through intermediate numbers while counting and ends on the exact final text", () => {
    // capture the tween instead of letting the test mock finish it at once
    let captured: Record<string, unknown> | undefined;
    let proxy: { v: number } | undefined;
    vi.mocked(gsap.to).mockImplementationOnce(((target: { v: number }, vars: Record<string, unknown>) => {
      proxy = target;
      captured = vars;
      return { kill: vi.fn() };
    }) as never);
    render(<CountUp value={73.7} decimals={1} />);
    const el = screen.getByText("73.7");

    (vi.mocked(ScrollTrigger.create).mock.calls[0]![0] as unknown as TriggerConfig).onEnter();
    expect(el.textContent).toBe("0.0");                         // the count starts from 0
    proxy!.v = 21.4;                                            // what GSAP does on a tick: move the animated value
    (captured!.onUpdate as () => void)();
    expect(el.textContent).toBe("21.4");                        // an intermediate step
    expect(el).toHaveAttribute("aria-label", "73.7");           // assistive technology still gets the final value
    (captured!.onComplete as () => void)();
    expect(el.textContent).toBe("73.7");                        // exact final text
    expect(captured).toMatchObject({ v: 73.7 });
  });

  it("applies a custom format to the final value and to every step", () => {
    render(<CountUp value={1234} format={(n) => Math.round(n).toLocaleString("en-US") + " papers"} trigger="mount" />);
    // the mock finishes the tween at once: the final, formatted text is what remains
    expect(screen.getByText("1,234 papers")).toBeInTheDocument();
  });

  it("kills the trigger and the tween on unmount and puts the final value back", () => {
    let captured: Record<string, unknown> | undefined;
    const kill = vi.fn();
    vi.mocked(gsap.to).mockImplementationOnce(((_t: unknown, vars: Record<string, unknown>) => {
      captured = vars;
      return { kill };
    }) as never);
    const { unmount } = render(<CountUp value={50} />);
    const el = screen.getByText("50");
    const trigger = vi.mocked(ScrollTrigger.create).mock.results[0]!.value as { kill: ReturnType<typeof vi.fn> };
    (vi.mocked(ScrollTrigger.create).mock.calls[0]![0] as unknown as TriggerConfig).onEnter();
    (captured!.onUpdate as () => void)();
    const ctx = vi.mocked(gsap.context).mock.results[0]!.value as { revert: ReturnType<typeof vi.fn> };

    unmount();
    expect(kill).toHaveBeenCalledTimes(1);
    expect(trigger.kill).toHaveBeenCalledTimes(1);
    expect(ctx.revert).toHaveBeenCalledTimes(1);
    expect(el.textContent).toBe("50");
  });

  it("shows a changed value as the final text, not the previous one", () => {
    const { rerender } = render(<CountUp value={10} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    rerender(<CountUp value={20} />);
    expect(screen.getByText("20")).toHaveAttribute("data-value", "20");
    expect(screen.queryByText("10")).not.toBeInTheDocument();
  });

  it("renders the final value with no animation when the visitor prefers reduced motion", () => {
    restore = setReducedMotion(true);
    render(<CountUp value={73.7} decimals={1} />);
    expect(screen.getByText("73.7")).toBeInTheDocument();
    expect(gsap.context).not.toHaveBeenCalled();
    expect(ScrollTrigger.create).not.toHaveBeenCalled();
    expect(gsap.to).not.toHaveBeenCalled();
  });
});
