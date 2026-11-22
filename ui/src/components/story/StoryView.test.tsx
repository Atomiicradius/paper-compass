import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";
import { setReducedMotion } from "@/test/motion";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn() } };
});
import { api } from "@/api/client";
import StoryView, { stepFromProgress } from "@/components/story/StoryView";

type TriggerConfig = { trigger: Element; start: string; end: string; onUpdate: (self: { progress: number }) => void };
const triggerConfig = () => vi.mocked(ScrollTrigger.create).mock.calls.at(-1)![0] as unknown as TriggerConfig;
const scrollTo = (progress: number) => act(() => triggerConfig().onUpdate({ progress }));

function mockApi() {
  vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
  vi.mocked(api.clusters).mockResolvedValue(makeClusters());
  vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
  vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
  vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
}

describe("stepFromProgress", () => {
  it("splits the scroll progress into 8 equal steps and clamps", () => {
    expect([0, 0.124, 0.125, 0.5, 0.874, 0.875, 1, 1.4, -0.2, NaN].map(stepFromProgress)).toEqual([0, 0, 1, 4, 6, 7, 7, 7, 0, 0]);
  });
});

describe("StoryView: the pinned stage", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());

  it("pins a full-height stage in a section as tall as the 8 steps, and listens to the scroll through a ScrollTrigger", () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    const stage = screen.getByTestId("story-stage");
    expect(stage.className).toContain("sticky");
    const section = screen.getByRole("region", { name: "Story" });
    expect(section.style.height).toBe(`${640 * 8}px`); // 8 screens (640 px until the real pane is measured)
    const cfg = triggerConfig();
    expect(cfg.trigger).toBe(section);
    expect(cfg.start).toBe("top top");
    expect(cfg.end).toBe("bottom bottom");
  });

  it("has all 8 steps in the DOM, with the exact eyebrow and heading of each numbered step", () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    const eyebrows = ["01 · DISCOVER · WHAT IS IN THE CORPUS?", "02 · CONNECT · WHAT DO THE PAPERS USE?", "03 · MAP · WHERE DO PAPERS CLUSTER?", "04 · DETECT · WHICH COMBINATIONS ARE RARE?", "05 · SCORE · HOW STRONG IS THE SIGNAL?", "06 · EXPLAIN · WHAT IS THE EVIDENCE?", "07 · LIMITS · WHAT THIS IS NOT"];
    const headings = ["The corpus", "Methods and tasks", "Clusters", "Observed versus expected", "Three signals and a confidence", "Evidence you can check", "A signal, not a verdict"];
    eyebrows.forEach((e) => expect(screen.getByText(e)).toBeInTheDocument());
    headings.forEach((h) => expect(screen.getByRole("heading", { level: 3, name: h })).toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    expect(document.querySelectorAll("[data-step]")).toHaveLength(8);
  });

  it("shows the counter and moves the counter and the progress rail with the scroll", () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    const counter = screen.getByTestId("story-counter");
    const rail = within(screen.getByRole("navigation", { name: "Story steps" })).getAllByRole("button");
    expect(rail).toHaveLength(8);
    expect(counter).toHaveTextContent("00 / 07");
    expect(rail[0]).toHaveAttribute("aria-current", "step");

    scrollTo(0.5);
    expect(counter).toHaveTextContent("04 / 07");
    expect(rail[4]).toHaveAttribute("aria-current", "step");
    expect(rail[0]).not.toHaveAttribute("aria-current");

    scrollTo(1);
    expect(counter).toHaveTextContent("07 / 07");
    expect(rail[7]).toHaveAttribute("aria-current", "step");
  });

  it("hides every step but the first through GSAP, and animates the leaving and the entering step on a change", () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    const panels = Array.from(document.querySelectorAll("[data-step]"));
    expect(vi.mocked(gsap.set).mock.calls.some(([t, v]) => Array.isArray(t) && t.length === 8 && (v as { autoAlpha: number }).autoAlpha === 0)).toBe(true);
    scrollTo(0.2); // step 1
    expect(gsap.to).toHaveBeenCalledWith(panels[0], expect.objectContaining({ autoAlpha: 0 }));
    expect(gsap.fromTo).toHaveBeenCalledWith(panels[1], expect.objectContaining({ autoAlpha: 0 }), expect.objectContaining({ autoAlpha: 1, y: 0 }));
  });

  it("makes the step panels their own scroll areas for Lenis", () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    document.querySelectorAll("[data-step]").forEach((p) => expect(p).toHaveAttribute("data-lenis-prevent"));
  });

  it("kills the ScrollTrigger and reverts the GSAP context on unmount", () => {
    const { unmount } = render(<StoryView onOpenExplorer={() => {}} />);
    const trigger = vi.mocked(ScrollTrigger.create).mock.results.at(-1)!.value as { kill: ReturnType<typeof vi.fn> };
    const ctx = vi.mocked(gsap.context).mock.results.at(-1)!.value as { revert: ReturnType<typeof vi.fn> };
    unmount();
    expect(trigger.kill).toHaveBeenCalled();
    expect(ctx.revert).toHaveBeenCalled();
  });

  it("has 'Open the explorer' in the last step", async () => {
    const onOpen = vi.fn();
    render(<StoryView onOpenExplorer={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /Open the explorer/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("under reduced motion: all steps stacked, nothing pinned, no counter or rail, no trigger, no GSAP work", () => {
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    expect(screen.queryByTestId("story-stage")).not.toBeInTheDocument();
    expect(screen.queryByTestId("story-counter")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Story steps" })).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-step]")).toHaveLength(8);
    expect(screen.getByRole("heading", { level: 3, name: "A signal, not a verdict" })).toBeInTheDocument();
    expect(ScrollTrigger.create).not.toHaveBeenCalled();
    expect(gsap.set).not.toHaveBeenCalled();
    expect(gsap.to).not.toHaveBeenCalled();
    expect(gsap.fromTo).not.toHaveBeenCalled();
  });
});
