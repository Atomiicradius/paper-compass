import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Explanation } from "@/api/types";
import { clearClosestWorkCache, closestPapers, MAX_CLOSEST } from "@/lib/closest-work";
import { makeExplanation, makeOpportunity } from "@/test/fixtures";
import { TooltipProvider } from "@/components/ui/primitives";
import { CandidateDetail, trackTicks } from "@/components/CandidateDetail";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, explain: vi.fn(), rag: vi.fn() } };
});
import { api, ApiError } from "@/api/client";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);
const detail = (id = 14) => <CandidateDetail opportunity={makeOpportunity(id)} rank={1} score={73.7} scoreLabel="Stored score (rules-v1)." onOpenEvidence={() => {}} />;

function withNeighbours(n: number): Explanation {
  const e = makeExplanation();
  e.evidence.roles.nearest_existing = Array.from({ length: n }, (_, i) => ({
    paper_id: `WN${i + 1}`, title: `Neighbour paper ${i + 1}`, year: 2020, venue: null, source_sentence: null, extractor: "rules-v1", tier: "close" as const, similarity: 0.9, uses: null,
  }));
  return e;
}

describe("the header of the detail panel and its tooltips", () => {
  beforeEach(() => {
    clearClosestWorkCache();
    vi.mocked(api.explain).mockReset();
    vi.mocked(api.explain).mockResolvedValue(withNeighbours(0));
  });

  it("starts with the chip that names the rank and the opportunity", () => {
    wrap(detail(14));
    expect(screen.getByTestId("candidate-detail").querySelector("p.mono-label")).toHaveTextContent("#1 · opportunity 14");
  });

  it("explains the score on hover: the stored score and its weights version", async () => {
    const user = userEvent.setup();
    wrap(detail());
    await user.hover(screen.getByTestId("score-badge"));
    expect((await screen.findAllByText("Stored score (rules-v1).", {}, { timeout: 3000 })).length).toBeGreaterThan(0);
  });

  it("explains the confidence on hover with the existing formula text", async () => {
    const user = userEvent.setup();
    wrap(detail());
    await user.hover(screen.getByText("Confidence: 1.00"));
    expect((await screen.findAllByText(/min\(1, expected \/ 5\): a low observed count means little when few papers were expected\./, {}, { timeout: 3000 })).length).toBeGreaterThan(0);
  });

  it("puts a labelled scale under the observed-versus-expected track", () => {
    wrap(detail());
    const scale = screen.getByTestId("track-scale");
    const o = makeOpportunity(14);
    expect(within(scale).getAllByText(/\d/).map((e) => e.textContent)).toEqual(trackTicks(o.observed_count, o.expected_count).map((t) => t.label));
    expect(trackTicks(1, 11.9).map((t) => t.label)).toEqual(["0", "7.1", "14"]);
    expect(trackTicks(0, 0).map((t) => t.label)).toEqual(["0", "0.6", "1.2"]);
  });

  it("shows the three signals as equal cards in one row, and has no horizontal overflow of its own", () => {
    wrap(detail());
    const panel = screen.getByTestId("candidate-detail");
    const meters = ["sparsity", "semantic", "temporal"].map((k) => screen.getByTestId("meter-" + k));
    meters.forEach((m) => expect(m.className).toMatch(/glass/));
    expect(meters[0]!.parentElement?.className).toMatch(/grid-cols-3/);
    expect(panel.className).toMatch(/overflow-x-hidden/);
    expect(panel).toHaveAttribute("data-lenis-prevent");
  });
});

describe("Closest existing work", () => {
  beforeEach(() => {
    clearClosestWorkCache();
    vi.mocked(api.explain).mockReset();
  });

  it("shows a skeleton under its heading while the explanation loads, then the titles with their paper ids", async () => {
    let resolve!: (e: Explanation) => void;
    vi.mocked(api.explain).mockReturnValue(new Promise<Explanation>((r) => (resolve = r)));
    wrap(detail());
    const block = await screen.findByTestId("closest-work");
    expect(within(block).getByRole("heading", { name: "Closest existing work" })).toBeInTheDocument();
    expect(screen.getByTestId("closest-work-skeleton").querySelectorAll(".shimmer")).toHaveLength(3);
    expect(block).toHaveAttribute("aria-busy", "true");
    resolve(withNeighbours(2));
    await waitFor(() => expect(screen.queryByTestId("closest-work-skeleton")).toBeNull());
    expect(within(block).getByText("Neighbour paper 1")).toBeInTheDocument();
    expect(within(block).getByText("WN1")).toBeInTheDocument();
    expect(within(block).getByText("Neighbour paper 2")).toBeInTheDocument();
    expect(within(block).getByText("WN2")).toBeInTheDocument();
    expect(block).toHaveAttribute("aria-busy", "false");
  });

  it("lists at most three titles", async () => {
    vi.mocked(api.explain).mockResolvedValue(withNeighbours(5));
    wrap(detail());
    expect(await screen.findByText("Neighbour paper 3")).toBeInTheDocument();
    expect(screen.queryByText("Neighbour paper 4")).toBeNull();
    expect(MAX_CLOSEST).toBe(3);
    expect(closestPapers({ nearest_existing: withNeighbours(5).evidence.roles.nearest_existing })).toHaveLength(3);
  });

  it("is loaded for the selected opportunity only, once, and cached by id", async () => {
    vi.mocked(api.explain).mockResolvedValue(withNeighbours(1));
    const { rerender } = wrap(detail(14));
    await screen.findByText("Neighbour paper 1");
    expect(api.explain).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.explain).mock.calls[0]![0]).toBe(14);
    rerender(<TooltipProvider>{detail(15)}</TooltipProvider>);
    await waitFor(() => expect(api.explain).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.explain).mock.calls[1]![0]).toBe(15);
    rerender(<TooltipProvider>{detail(14)}</TooltipProvider>);
    expect(await screen.findByText("Neighbour paper 1")).toBeInTheDocument(); // back to 14: from the cache, at once
    expect(api.explain).toHaveBeenCalledTimes(2);
  });

  it("is hidden when the call fails (no heading, no error text), and tried again on a later selection", async () => {
    vi.mocked(api.explain).mockRejectedValue(new ApiError(500, "boom"));
    wrap(detail());
    await waitFor(() => expect(screen.queryByTestId("closest-work")).toBeNull());
    expect(screen.queryByText("Closest existing work")).toBeNull();
    expect(screen.queryByText(/boom/)).toBeNull();
    expect(screen.getByTestId("candidate-detail")).toBeInTheDocument(); // the rest of the panel is not affected
  });

  it("is hidden when the explanation has no closest existing work", async () => {
    vi.mocked(api.explain).mockResolvedValue(withNeighbours(0));
    wrap(detail());
    await waitFor(() => expect(screen.queryByTestId("closest-work")).toBeNull());
    expect(api.explain).toHaveBeenCalledTimes(1);
  });
});
