import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { AsyncState } from "@/lib/hooks";
import type { Opportunity } from "@/api/types";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { EMPTY_FILTERS } from "@/lib/opportunities";
import { makeExplanation, makeOpportunities, makeOpportunity } from "@/test/fixtures";
import { setReducedMotion } from "@/test/motion";
import { TooltipProvider } from "@/components/ui/primitives";
import { CandidatesView } from "@/components/CandidatesView";
import { CandidateCard } from "@/components/CandidateCard";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, explain: vi.fn(), rag: vi.fn() } };
});
import { api } from "@/api/client";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);
const state = (items: Opportunity[]): AsyncState<{ items: Opportunity[]; total: number }> => ({ data: { items, total: items.length }, error: null, loading: false, reload: () => {} });

// The visual rework changed classes and added motion, not content: these tests pin down what must stay true.
describe("the visual rework keeps the content", () => {
  let restore = () => {};
  beforeEach(() => vi.mocked(api.explain).mockReset());
  afterEach(() => restore());

  it("keeps the heading text (an italic accent word inside it does not change the accessible name)", () => {
    wrap(<CandidatesView state={state(makeOpportunities())} filters={EMPTY_FILTERS} selectedId={null} onOpen={() => {}} onClearFilters={() => {}} />);
    const h = screen.getByRole("heading", { level: 2, name: "Candidate opportunities" });
    expect(h).toHaveClass("display-heading");
    expect(h.querySelector(".accent-word")).toHaveTextContent("opportunities");
  });

  it("has the final score in the card's DOM text and label (CountUp), and the card is a glass surface", () => {
    wrap(<CandidateCard opportunity={makeOpportunity(14)} rank={1} selected={false} onOpen={() => {}} score={73.73} scoreLabel="Stored score." />);
    const badge = screen.getByTestId("score-badge");
    expect(badge).toHaveTextContent("74");
    expect(within(badge).getByRole("img")).toHaveAttribute("aria-label", "74");
    expect(screen.getByTestId("candidate-card")).toHaveClass("glass");
  });

  it("reveals the list of cards through GSAP, with every card in the DOM", () => {
    wrap(<CandidatesView state={state(makeOpportunities())} filters={EMPTY_FILTERS} selectedId={null} onOpen={() => {}} onClearFilters={() => {}} />);
    expect(screen.getAllByTestId("candidate-card")).toHaveLength(6);
    // one hidden-state set per Reveal (the header at mount, the list on scroll); the list's targets are the 6 cards
    const sets = vi.mocked(gsap.set).mock.calls.map((c) => c[0] as Element[]);
    expect(sets.some((targets) => targets.length === 6 && targets.every((t) => (t as HTMLElement).dataset.testid === "candidate-card"))).toBe(true);
    expect(ScrollTrigger.create).toHaveBeenCalled();
  });

  it("shows everything with no GSAP work at all when the visitor prefers reduced motion", () => {
    restore = setReducedMotion(true);
    wrap(<CandidatesView state={state(makeOpportunities())} filters={EMPTY_FILTERS} selectedId={null} onOpen={() => {}} onClearFilters={() => {}} />);
    expect(screen.getAllByTestId("candidate-card")).toHaveLength(6);
    expect(screen.getAllByTestId("score-badge")[0]).toHaveTextContent(/\d/);
    expect(gsap.set).not.toHaveBeenCalled();
    expect(gsap.to).not.toHaveBeenCalled();
    expect(ScrollTrigger.create).not.toHaveBeenCalled();
  });

  it("keeps the warning, the limitations and the confidence wording in the drawer, and lets the drawer scroll on its own", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    expect(screen.getByTestId("warning-banner")).toHaveTextContent("A candidate opportunity is a signal for human review, not proof of a research gap.");
    await screen.findByRole("tab", { name: /Supports A/ });
    expect(screen.getByRole("heading", { name: "Limitations" })).toBeInTheDocument();
    // the panel and its scroll area are excluded from Lenis smooth scrolling
    const panel = screen.getByRole("dialog");
    expect(panel).toHaveAttribute("data-lenis-prevent");
    expect(panel.querySelector("[data-lenis-prevent].overflow-y-auto")).not.toBeNull();
    // the drawer content reveals at once (it is outside the scrolling pane), without hiding anything from the DOM
    await waitFor(() => expect(gsap.to).toHaveBeenCalled());
    expect(screen.getByTestId("citation-check")).toBeInTheDocument();
  });
});
