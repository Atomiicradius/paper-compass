import { useState } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AsyncState } from "@/lib/hooks";
import type { Opportunity } from "@/api/types";
import { EMPTY_FILTERS, type CandidateFilters } from "@/lib/opportunities";
import { makeExplanation, makeOpportunities, makeOpportunity } from "@/test/fixtures";
import { TooltipProvider } from "@/components/ui/primitives";
import { CandidateDetail, trackPositions, isLowConfidence } from "@/components/CandidateDetail";
import { CandidateRow } from "@/components/CandidateRow";
import { ringFill } from "@/components/ScoreRing";
import { CandidatesView } from "@/components/CandidatesView";
import type { SearchForm } from "@/components/Sidebar";
import { FiltersPanel } from "@/components/FiltersPanel";
import { PapersSearchBar } from "@/components/PapersSearchBar";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, explain: vi.fn(), rag: vi.fn() } };
});
import { api, ApiError } from "@/api/client";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

function state(items: Opportunity[]): AsyncState<{ items: Opportunity[]; total: number }> {
  return { data: { items, total: items.length }, error: null, loading: false, reload: () => {} };
}

describe("CandidateDetail", () => {
  it("shows the combination, score ring, count badges, confidence and the three signal meters", () => {
    const o = makeOpportunity(14);
    wrap(<CandidateDetail opportunity={o} rank={1} score={73.73} scoreLabel="Stored score." onOpenEvidence={() => {}} />);
    const card = screen.getByTestId("candidate-detail");
    expect(within(card).getByText("Masked Language Modeling")).toBeInTheDocument();
    expect(within(card).getByText("Machine Translation")).toBeInTheDocument();
    expect(within(card).getByText("Observed Count: 1")).toBeInTheDocument();
    expect(within(card).getByText("Expected: 11.9")).toBeInTheDocument();
    expect(within(card).getByText("Confidence: 1.00")).toBeInTheDocument();
    expect(within(card).queryByText("Low confidence")).toBeNull();
    const meters = within(card).getAllByRole("meter");
    expect(meters.map((m) => m.getAttribute("aria-label"))).toEqual(["Sparsity", "Semantic", "Temporal"]);
    expect(Number(meters[0]?.getAttribute("aria-valuenow"))).toBeCloseTo(0.84447473);
    expect(within(card).getByText("Score")).toBeInTheDocument();
    expect(within(card).getByTestId("score-badge")).toHaveTextContent("74");
    expect(within(card).getByTestId("observed-expected-track")).toBeInTheDocument();
  });

  it("opens the evidence only with the Evidence & explanation button", async () => {
    const user = userEvent.setup();
    const onOpenEvidence = vi.fn();
    const o = makeOpportunity(14);
    wrap(<CandidateDetail opportunity={o} rank={1} score={70} scoreLabel="" onOpenEvidence={onOpenEvidence} />);
    await user.click(screen.getByRole("button", { name: /Evidence & explanation/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(o);
  });

  it("flags a low confidence in the warning colour and with the words Low confidence", () => {
    wrap(<CandidateDetail opportunity={makeOpportunity(1, { confidence: 0.32 })} rank={2} score={40} scoreLabel="" onOpenEvidence={() => {}} />);
    expect(screen.getByText("Confidence: 0.32").className).toMatch(/warning/);
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });

  it("shows n/a when a signal is not implemented instead of inventing a value", () => {
    const o = makeOpportunity(1, { signals: { sparsity: null, semantic_compatibility: 0.5, temporal_activity: 0.5, graph_bridge_strength: null, method_compatibility: null } });
    wrap(<CandidateDetail opportunity={o} rank={1} score={50} scoreLabel="" onOpenEvidence={() => {}} />);
    expect(screen.getByTestId("meter-sparsity")).toHaveTextContent("n/a");
  });

  it("puts the expected marker and the observed dot on one shared scale", () => {
    const o = makeOpportunity(14);
    const p = trackPositions(o.observed_count, o.expected_count);
    expect(p.expected).toBeGreaterThan(p.observed);
    expect(p.expected).toBeLessThanOrEqual(1);
    expect(trackPositions(0, 0)).toEqual({ observed: 0, expected: 0 });
    wrap(<CandidateDetail opportunity={o} rank={1} score={70} scoreLabel="" onOpenEvidence={() => {}} />);
    expect(parseFloat(screen.getByTestId("expected-marker").style.left)).toBeCloseTo(p.expected * 100);
    expect(parseFloat(screen.getByTestId("observed-dot").style.left)).toBeCloseTo(p.observed * 100);
  });

  it("uses the existing confidence rule: below 0.5 or missing is low", () => {
    expect(isLowConfidence(0.49)).toBe(true);
    expect(isLowConfidence(null)).toBe(true);
    expect(isLowConfidence(0.5)).toBe(false);
  });

  it("fills the ring in proportion to the score, clamped to 0..1", () => {
    expect(ringFill(50)).toBeCloseTo(0.5);
    expect(ringFill(150)).toBe(1);
    expect(ringFill(-5)).toBe(0);
  });
});

describe("CandidateRow", () => {
  it("shows the rank, both elements and a mini ring, and selects with a click", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const o = makeOpportunity(14);
    wrap(<CandidateRow opportunity={o} rank={1} score={73.73} selected={false} onSelect={onSelect} />);
    const row = screen.getByRole("option");
    expect(row).toHaveTextContent("01");
    expect(row).toHaveTextContent("Masked Language Modeling");
    expect(row).toHaveTextContent("Machine Translation");
    expect(within(row).getByTestId("score-ring-mini")).toHaveTextContent("74");
    expect(row).toHaveAttribute("aria-selected", "false");
    await user.click(row);
    expect(onSelect).toHaveBeenCalledWith(o);
  });
});

describe("CandidatesView", () => {
  function Harness({ items, initial = EMPTY_FILTERS, onEvidence = () => {} }: { items: Opportunity[]; initial?: CandidateFilters; onEvidence?: (o: Opportunity) => void }) {
    const [filters, setFilters] = useState(initial);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    return (
      <>
        <button onClick={() => setFilters({ ...EMPTY_FILTERS, methods: ["Back-translation"] })}>apply method filter</button>
        <button onClick={() => setFilters(EMPTY_FILTERS)}>reset filters</button>
        <CandidatesView state={state(items)} filters={filters} selectedId={selectedId} onSelect={(o) => setSelectedId(o.opportunity_id)} onOpenEvidence={onEvidence} onClearFilters={() => setFilters(EMPTY_FILTERS)} />
      </>
    );
  }

  const rows = () => screen.getAllByTestId("candidate-row");

  it("lists all 13 candidates ranked by stored score, with the one ranked first selected and shown in the detail", () => {
    wrap(<Harness items={makeOpportunities()} />);
    expect(rows()).toHaveLength(13);
    expect(screen.getByText(/Showing/).textContent).toMatch(/13 of 13/);
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");
    expect(rows().filter((r) => r.getAttribute("aria-selected") === "true")).toHaveLength(1);
    expect(screen.getByTestId("candidate-detail")).toHaveTextContent("#1 · opportunity");
    expect(screen.queryByRole("button", { name: "Next page" })).toBeNull();
  });

  it("selects a row with a click and shows its detail without opening the evidence", async () => {
    const user = userEvent.setup();
    const onEvidence = vi.fn();
    wrap(<Harness items={makeOpportunities()} onEvidence={onEvidence} />);
    await user.click(rows()[1]!);
    expect(rows()[1]).toHaveAttribute("aria-selected", "true");
    expect(rows()[0]).toHaveAttribute("aria-selected", "false");
    expect(screen.getByTestId("candidate-detail")).toHaveTextContent("#2 · opportunity");
    expect(onEvidence).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Evidence & explanation/ }));
    expect(onEvidence).toHaveBeenCalledTimes(1);
  });

  it("moves the selection with Up / Down / Home / End while the list has the focus, and stops at the ends", async () => {
    const user = userEvent.setup();
    wrap(<Harness items={makeOpportunities()} />);
    screen.getByRole("listbox", { name: "Ranked candidates" }).focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(rows()[2]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}");
    expect(rows()[1]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(rows()[12]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}");
    expect(rows()[12]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}{ArrowUp}");
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("listbox")).toHaveAttribute("aria-activedescendant", rows()[0]!.id);
  });

  it("falls back to the first row when the selected one is filtered out", async () => {
    const user = userEvent.setup();
    wrap(<Harness items={makeOpportunities()} />);
    await user.click(rows()[3]!);
    await user.click(screen.getByText("apply method filter"));
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByText("reset filters"));
    expect(rows()).toHaveLength(13);
  });

  it("filters candidates and shows an empty state with a way out", async () => {
    const user = userEvent.setup();
    wrap(<Harness items={makeOpportunities()} />);
    await user.click(screen.getByText("apply method filter"));
    const cards = rows();
    expect(cards.length).toBeGreaterThan(0);
    expect(cards.length).toBeLessThan(13);
    expect(screen.getByTestId("candidate-detail")).toBeInTheDocument();
    const noMatch = wrap(<Harness items={makeOpportunities()} initial={{ ...EMPTY_FILTERS, tasks: ["No such task"] }} />);
    expect(noMatch.getAllByText(/No candidate matches these filters/).length).toBeGreaterThan(0);
  });

  it("what-if weights are labelled sliders and re-rank without touching the stored score", async () => {
    const user = userEvent.setup();
    const items = [
      makeOpportunity(1, { score: 90, signals: { sparsity: 1, semantic_compatibility: 0, temporal_activity: 0, graph_bridge_strength: null, method_compatibility: null } }),
      makeOpportunity(2, { score: 80, signals: { sparsity: 0, semantic_compatibility: 1, temporal_activity: 0, graph_bridge_strength: null, method_compatibility: null } }),
    ];
    wrap(<Harness items={items} />);
    const order = () => rows().map((r) => r.textContent ?? "");
    expect(order()[0]).toMatch(/Masked/);
    await user.click(screen.getByRole("button", { name: /What-if weights/ }));
    const sliders = screen.getAllByRole("slider");
    expect(sliders.map((s) => s.getAttribute("aria-label"))).toEqual(["Sparsity weight", "Semantic weight", "Temporal weight"]);
    expect(screen.getByRole("button", { name: /Reset to v1/ })).toBeDisabled();
    // semantic weight to 1.0 (keyboard End), sparsity and temporal to 0 (Home)
    for (const [i, key] of [[0, "{Home}"], [1, "{End}"], [2, "{Home}"]] as const) {
      sliders[i]?.focus();
      await user.keyboard(key);
    }
    await waitFor(() => expect(screen.getByRole("button", { name: /Reset to v1/ })).toBeEnabled());
    await waitFor(() => expect(screen.getByTestId("score-badge")).toHaveTextContent("100"));
  });

  it("shows an error with a retry, a loading skeleton and the no-data message", async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    const { unmount } = wrap(<CandidatesView state={{ data: null, error: new ApiError(0, "API not reachable"), loading: false, reload }} filters={EMPTY_FILTERS} selectedId={null} onSelect={() => {}} onClearFilters={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API not reachable");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(reload).toHaveBeenCalled();
    unmount();
    const l = wrap(<CandidatesView state={{ data: null, error: null, loading: true, reload }} filters={EMPTY_FILTERS} selectedId={null} onSelect={() => {}} onClearFilters={() => {}} />);
    expect(l.getByLabelText("Loading candidates")).toBeInTheDocument();
    l.unmount();
    wrap(<CandidatesView state={state([])} filters={EMPTY_FILTERS} selectedId={null} onSelect={() => {}} onClearFilters={() => {}} />);
    expect(screen.getByText(/No opportunities are stored yet/)).toBeInTheDocument();
  });
});

describe("EvidenceDrawer", () => {
  beforeEach(() => vi.mocked(api.explain).mockReset());

  it("shows the warning banner, the real counts and four evidence tabs", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    expect(screen.getByTestId("warning-banner")).toHaveTextContent("A candidate opportunity is a signal for human review, not proof of a research gap.");
    await screen.findByRole("tab", { name: /Supports A/ });
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Supports A1", "Supports B1", "Bridge Work0", "Nearest Existing2"]);
    expect(screen.getByText("399")).toBeInTheDocument();           // universe N
    expect(api.explain).toHaveBeenCalledWith(14, expect.anything());
  });

  it("verifies a citation only when it is cited AND part of the evidence set; flags the rest", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    await screen.findByRole("tab", { name: /Supports A/ });
    const chips = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-status]"));
    expect(chips.map((c) => [c.textContent, c.dataset.status])).toEqual([["WN1", "verified"], ["WZZ", "unknown"]]);
    expect(chips[1]).toBeDisabled();                                // an unverified claim cannot be followed as if it were evidence
    expect(screen.getByTestId("citation-check")).toHaveTextContent(/citation check failed/i);   // 1 of 2 verified: not "all verified"
  });

  it("jumps to the cited paper's tab when a verified citation is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    await screen.findByRole("tab", { name: /Supports A/ });
    expect(screen.getByRole("tab", { name: /Supports A/ })).toHaveAttribute("data-state", "active");
    await user.click(document.querySelector<HTMLButtonElement>("button[data-status=verified]") as HTMLButtonElement);
    expect(screen.getByRole("tab", { name: /Nearest Existing/ })).toHaveAttribute("data-state", "active");
    expect(document.getElementById("ev-WN1")).not.toBeNull();
  });

  it("highlights both entities in source sentences with their tag colours", async () => {
    const user = userEvent.setup();
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    await user.click(await screen.findByRole("tab", { name: /Nearest Existing/ }));
    const card = document.getElementById("ev-WN1") as HTMLElement;
    const marks = Array.from(card.querySelectorAll("mark")).map((m) => [m.dataset.kind, m.textContent]);
    expect(marks).toEqual([["method", "Masked language models"], ["task", "machine translation"]]);
    expect(within(card).getByText("exact: uses both")).toBeInTheDocument();
    const close = document.getElementById("ev-WN2") as HTMLElement;
    expect(close).toHaveTextContent("similarity 0.964");
    expect(close).toHaveTextContent("No source sentence stored");   // missing data is stated, not invented
  });

  it("explains a failed load and can retry", async () => {
    const user = userEvent.setup();
    vi.mocked(api.explain).mockRejectedValueOnce(new ApiError(422, "not exactly one pair")).mockResolvedValueOnce(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("not exactly one pair");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("tab", { name: /Supports A/ })).toBeInTheDocument();
  });

  it("renders nothing when no opportunity is selected, and answers a free-form question with the 501 explanation", async () => {
    const user = userEvent.setup();
    const { unmount } = wrap(<EvidenceDrawer opportunity={null} onClose={() => {}} onOpenGraph={() => {}} />);
    expect(screen.queryByTestId("warning-banner")).toBeNull();
    unmount();
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    vi.mocked(api.rag).mockRejectedValue(new ApiError(501, "not implemented"));
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    await user.type(await screen.findByLabelText("Ask about this opportunity"), "Which is closest?");
    await user.click(screen.getByRole("button", { name: /Ask/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(/not available yet/);
  });
});

// The sidebar became the filters panel; its search box moved to the Papers screen (see PapersSearchBar.test.tsx).
describe("FiltersPanel (the controls the sidebar held)", () => {
  const baseForm: SearchForm = { query: "", mode: "auto", collapse: true, years: [1951, 2026] };
  const options = { methods: ["Back-translation", "Transformer"], tasks: ["Machine Translation"], datasets: [], settings: [] };

  function Host({ onFilters = () => {} }: { onFilters?: (f: CandidateFilters) => void }) {
    const [form, setForm] = useState(baseForm);
    const [filters, setFilters] = useState(EMPTY_FILTERS);
    return (
      <FiltersPanel
        open onClose={() => {}} form={form} onForm={setForm}
        filters={filters} onFilters={(f) => { setFilters(f); onFilters(f); }} options={options} yearBounds={[1951, 2026]}
      />
    );
  }

  it("checking a method updates the filters, and Clear all clears them", async () => {
    const user = userEvent.setup();
    const onFilters = vi.fn();
    wrap(<Host onFilters={onFilters} />);
    await user.click(screen.getByRole("checkbox", { name: "Back-translation" }));
    expect(onFilters).toHaveBeenLastCalledWith({ ...EMPTY_FILTERS, methods: ["Back-translation"] });
    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onFilters).toHaveBeenLastCalledWith(EMPTY_FILTERS);
  });

  it("labels both year thumbs and the confidence thumb, and explains the empty settings list", async () => {
    const user = userEvent.setup();
    wrap(<Host />);
    expect(screen.getAllByRole("slider").map((s) => s.getAttribute("aria-label"))).toEqual([
      "Publication year range minimum", "Publication year range maximum", "Minimum confidence",
    ]);
    await user.click(screen.getByRole("button", { name: /Settings/ }));
    expect(screen.getByText(/None does yet/)).toBeInTheDocument();
  });
});

describe("PapersView and search modes", () => {
  const hit = (id: string, extra = {}) => ({ paper_id: id, title: "Paper " + id, year: 2024, venue: "ACL", score: 0.0328, methods: ["Back-translation"], datasets: [], tasks: [], ...extra });
  const result = (mode: "vector" | "hybrid" | "keyword", hits: ReturnType<typeof hit>[], note: string | null = null) => ({
    data: { query: "q", mode, score_type: mode === "hybrid" ? "rrf_fused" : "cosine_similarity", model: null, note, results: hits } as never,
    error: null, loading: false, reload: () => {},
  });

  it("shows vector and keyword ranks only for hybrid hits", async () => {
    const { PapersView } = await import("@/components/PapersView");
    const hybrid = wrap(<PapersView state={result("hybrid", [hit("W1", { vector_rank: 3, keyword_rank: null }), hit("W2", { vector_rank: null, keyword_rank: 1 })])} submitted notes={[]} onOpenPaper={() => {}} />);
    expect(hybrid.getByText("vector #3")).toBeInTheDocument();
    expect(hybrid.getByText("keyword –")).toBeInTheDocument();      // not in the keyword list: a dash, not a made-up rank
    expect(hybrid.getByText("keyword #1")).toBeInTheDocument();
    expect(hybrid.getByText("vector –")).toBeInTheDocument();
    hybrid.unmount();
    const plain = wrap(<PapersView state={result("vector", [hit("W3", {})])} submitted notes={[]} onOpenPaper={() => {}} />);
    expect(plain.queryByText(/^vector (#\d+|–)$/)).toBeNull();      // a rank chip, not the "mode vector" label
    expect(plain.queryByText(/^keyword (#\d+|–)$/)).toBeNull();
  });

  it("shows the API's note (e.g. why keyword search found nothing) and the UI's own notes", async () => {
    const { PapersView } = await import("@/components/PapersView");
    wrap(<PapersView state={result("keyword", [], "no paper contains every word of the query; try fewer words, or the vector or hybrid mode")} submitted notes={["Hybrid search applies only the year range, so your method filters were not used."]} onOpenPaper={() => {}} />);
    expect(screen.getByText(/no paper contains every word/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/Hybrid search applies only the year range/);
    expect(screen.getByText(/No papers matched/)).toBeInTheDocument();
  });

  it("offers all four search modes (now a segmented control on the Papers screen)", () => {
    wrap(<PapersSearchBar form={{ query: "", mode: "auto", collapse: true, years: [1951, 2026] }} onForm={() => {}} onSearch={() => {}} searching={false} />);
    const modes = within(screen.getByRole("radiogroup", { name: "Search mode" })).getAllByRole("radio").map((r) => r.textContent);
    expect(modes).toEqual(["Auto", "Vector", "Keyword", "Hybrid"]);
  });
});

describe("LandscapeView", () => {
  const land = (pairs: { a: number; b: number; cross_citations: number; citation_density: number; semantic_similarity: number; weakly_connected: boolean }[]) => ({
    data: { corpus: { papers: 1999, cutoff_year: 2026 }, papers_per_year: { "2020": 10, "2021": 12 }, n_clusters: 2, emerging: [], declining: [],
      weakly_connected_cluster_pairs: pairs, bridge_papers: [], disclaimer: "x" } as never,
    error: null, loading: false, reload: () => {},
  });

  it("lists weakly connected cluster pairs when there are some, with a caveat, and nothing when there are none", async () => {
    const { LandscapeView } = await import("@/components/LandscapeView");
    const { api: realApi } = await import("@/api/client");
    vi.spyOn(realApi, "clusters").mockResolvedValue({ method: "hdbscan", min_cluster_size: 15, min_samples: 5, pca_dims: 20, n_papers: 10, n_noise: 2, clusters: [] });
    vi.spyOn(realApi, "trends").mockResolvedValue([]);
    const withPairs = wrap(<LandscapeView state={land([{ a: 3, b: 6, cross_citations: 0, citation_density: 0, semantic_similarity: 0.9234, weakly_connected: true }])} onOpenGraph={() => {}} />);
    const region = await withPairs.findByRole("region", { name: "Weakly connected cluster pairs" });
    expect(region).toHaveTextContent("3 ↔ 6");
    expect(region).toHaveTextContent("0.923");
    expect(region).toHaveTextContent(/not proof that the two areas are unconnected/);
    withPairs.unmount();
    const none = wrap(<LandscapeView state={land([])} onOpenGraph={() => {}} />);
    await none.findByText(/Papers per year/i);
    expect(none.queryByRole("region", { name: "Weakly connected cluster pairs" })).toBeNull();
  });
});
