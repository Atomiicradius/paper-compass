import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScrollTrigger } from "@/lib/gsap";
import { ApiError } from "@/api/client";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";
import { setReducedMotion } from "@/test/motion";

vi.mock("@/components/story/NetworkCanvas", async () => {
  const React = await import("react");
  return { default: () => React.createElement("div", { "data-testid": "network-canvas" }) };
});
vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn() } };
});
import { api } from "@/api/client";
import StoryView from "@/components/story/StoryView";

const step = (i: number) => document.querySelector(`[data-step="${i}"]`) as HTMLElement;
const down = () => Promise.reject(new ApiError(503, "unavailable"));

function mockApi() {
  vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
  vi.mocked(api.clusters).mockResolvedValue(makeClusters());
  vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
  vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
  vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
}

/** Render the story with every step stacked (reduced motion) and wait until all the data has arrived. */
async function renderStacked() {
  const restore = setReducedMotion(true);
  render(<StoryView onOpenExplorer={() => {}} />);
  await waitFor(() => expect(within(step(6)).getByText(/citations verified/)).toBeInTheDocument());
  return restore;
}

describe("story steps: the content, with fixture data", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());

  it("hero: the title with 'Compass' as the italic accent word, the subtitle, the corpus size from the API, SCROLL TO BEGIN", async () => {
    restore = await renderStacked();
    const hero = step(0);
    const title = within(hero).getByRole("heading", { level: 2, name: "Paper Compass" });
    expect(title.querySelector(".accent-word")).toHaveTextContent("Compass");
    expect(within(hero).getByText("Finding what the literature has not connected yet.")).toBeInTheDocument();
    expect(hero.textContent).toContain("An evidence-grounded exploration of a curated corpus of 1,999 papers.");
    expect(within(hero).getByText("SCROLL TO BEGIN")).toBeInTheDocument();
  });

  it("01 · the corpus: the papers numeral and the papers-per-year chart", async () => {
    restore = await renderStacked();
    const s = step(1);
    expect(within(s).getByText("01 · DISCOVER · WHAT IS IN THE CORPUS?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "The corpus" })).toBeInTheDocument();
    expect(within(s).getByText("1,999")).toBeInTheDocument();
    expect(within(s).getByRole("img", { name: "Papers per year from 2019 to 2022" })).toBeInTheDocument();
  });

  it("02 · methods and tasks: the exact sentence and the most used extracted elements with their counts", async () => {
    restore = await renderStacked();
    const s = step(2);
    expect(within(s).getByText("02 · CONNECT · WHAT DO THE PAPERS USE?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "Methods and tasks" })).toBeInTheDocument();
    expect(within(s).getByText("Methods, tasks and datasets are extracted from titles and abstracts by a rule-based extractor (rules-v1).")).toBeInTheDocument();
    for (const name of ["Transformer", "Fine-tuning", "Back-translation", "Beam Search", "Machine Translation", "Language Modeling"]) expect(within(s).getByText(name)).toBeInTheDocument();
    expect(within(s).queryByText("Byte-Pair Encoding")).not.toBeInTheDocument(); // only the top four of each
    expect(within(s).getAllByText("300 papers")).toHaveLength(2); // the most used method and the most used task
  });

  it("03 · clusters: the number of clusters, the papers in no cluster, and the exact sentence", async () => {
    restore = await renderStacked();
    const s = step(3);
    expect(within(s).getByText("03 · MAP · WHERE DO PAPERS CLUSTER?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "Clusters" })).toBeInTheDocument();
    expect(within(s).getByText("7")).toBeInTheDocument();
    expect(within(s).getByText("883")).toBeInTheDocument();
    expect(within(s).getByText("Papers in no cluster")).toBeInTheDocument();
    expect(within(s).getByText("HDBSCAN on SPECTER2 embeddings.")).toBeInTheDocument();
  });

  it("04 · observed versus expected: the top opportunity (rank 1), its two elements, both bars and the universe N", async () => {
    restore = await renderStacked();
    const s = step(4);
    expect(within(s).getByText("04 · DETECT · WHICH COMBINATIONS ARE RARE?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "Observed versus expected" })).toBeInTheDocument();
    expect(s.textContent).toContain("Masked Language Modeling");
    expect(s.textContent).toContain("Machine Translation");
    expect(within(s).getByText("1")).toBeInTheDocument(); // observed
    expect(within(s).getByText("11.9")).toBeInTheDocument(); // expected, one decimal
    expect(within(s).getByText("399")).toBeInTheDocument(); // universe N, from the explanation
    expect(within(s).getByText("Universe N")).toBeInTheDocument();
    const observed = within(s).getByRole("meter", { name: "Observed" });
    const expected = within(s).getByRole("meter", { name: "Expected" });
    expect(Number(expected.getAttribute("aria-valuenow"))).toBe(1); // the larger of the two is the full bar
    expect(Number(observed.getAttribute("aria-valuenow"))).toBeCloseTo(1 / 11.859649, 3);
  });

  it("05 · three signals and a confidence: the three signals and the confidence of the top opportunity, and the exact line", async () => {
    restore = await renderStacked();
    const s = step(5);
    expect(within(s).getByText("05 · SCORE · HOW STRONG IS THE SIGNAL?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "Three signals and a confidence" })).toBeInTheDocument();
    for (const [label, value] of [["Sparsity", "0.84"], ["Semantic", "0.75"], ["Temporal", "0.55"]] as const) {
      expect(within(s).getByText(label)).toBeInTheDocument();
      expect(within(s).getByText(value)).toBeInTheDocument();
    }
    expect(within(s).getByText("Confidence")).toBeInTheDocument();
    expect(within(s).getByText("0.32")).toBeInTheDocument(); // the top opportunity's confidence
    expect(within(s).getByText("Low expected counts lower the confidence.")).toBeInTheDocument();
  });

  it("06 · evidence: two or three papers with their ids from the explanation, and '{n} citations verified'", async () => {
    restore = await renderStacked();
    const s = step(6);
    expect(within(s).getByText("06 · EXPLAIN · WHAT IS THE EVIDENCE?")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "Evidence you can check" })).toBeInTheDocument();
    const ids = Array.from(s.querySelectorAll("li")).map((li) => li.querySelector("span[title='OpenAlex id']")?.textContent);
    expect(ids.length).toBeGreaterThanOrEqual(2);
    expect(ids.length).toBeLessThanOrEqual(3);
    expect(ids.slice(0, 2)).toEqual(["WN1", "WN2"]);
    expect(within(s).getByText("Exact neighbour", { exact: false })).toBeInTheDocument();
    expect(Array.from(s.querySelectorAll("p")).some((p) => p.textContent === "2 citations verified")).toBe(true);
  });

  it("07 · limits: the exact sentences and the 'Open the explorer' button", async () => {
    const onOpen = vi.fn();
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={onOpen} />);
    const s = step(7);
    expect(within(s).getByText("07 · LIMITS · WHAT THIS IS NOT")).toBeInTheDocument();
    expect(within(s).getByRole("heading", { level: 3, name: "A signal, not a verdict" })).toBeInTheDocument();
    expect(within(s).getByText("A candidate opportunity is a signal for human review, not proof of a research gap. Counts come from rule-based extraction over a curated corpus, not the whole literature.")).toBeInTheDocument();
    await userEvent.click(within(s).getByRole("button", { name: /Open the explorer/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("uses none of the banned words, and 'gap' only in the quoted limits sentence", async () => {
    restore = await renderStacked();
    const text = screen.getByRole("region", { name: "Story" }).textContent ?? "";
    for (const word of [/undiscovered/i, /\bproven\b/i, /\bnovel\b/i]) expect(text).not.toMatch(word);
    expect(text.match(/\bgap\b/gi)).toHaveLength(1);
    expect(step(7).textContent).toMatch(/\bgap\b/);
  });

  it("shows no 'undefined', 'NaN' or 'null' anywhere", async () => {
    restore = await renderStacked();
    expect(screen.getByRole("region", { name: "Story" }).textContent).not.toMatch(/undefined|NaN|\bnull\b/);
  });
});

describe("story steps: a number the API could not provide is not shown (and nothing is made up)", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());

  it("with every API call failing or empty: no figure, no chart, no list, only the fixed sentences", async () => {
    vi.mocked(api.landscape).mockImplementation(down);
    vi.mocked(api.clusters).mockImplementation(down);
    vi.mocked(api.trends).mockImplementation(down);
    vi.mocked(api.opportunities).mockResolvedValue({ total: 0, items: [], disclaimer: "x" });
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    await waitFor(() => expect(api.opportunities).toHaveBeenCalled());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });

    const root = screen.getByRole("region", { name: "Story" });
    expect(root.querySelectorAll(".mono-figure")).toHaveLength(0); // no numeral at all
    expect(root.querySelector("svg[role=img]")).toBeNull(); // no chart (the only other svg is the arrow icon of the button)
    expect(root.querySelectorAll("li")).toHaveLength(0); // no element list, no evidence
    expect(root.querySelectorAll("[role=meter]")).toHaveLength(0);
    expect(root.textContent).not.toContain("An evidence-grounded exploration"); // the hero line has no number, so it is not shown
    expect(root.textContent).not.toContain("citations verified");
    expect(root.textContent).not.toContain("Universe N");
    expect(root.textContent).not.toMatch(/undefined|NaN|\bnull\b/);
    // what does not depend on a number is still there
    expect(within(step(0)).getByText("Finding what the literature has not connected yet.")).toBeInTheDocument();
    expect(within(step(2)).getByText(/rule-based extractor \(rules-v1\)/)).toBeInTheDocument();
    expect(within(step(3)).getByText("HDBSCAN on SPECTER2 embeddings.")).toBeInTheDocument();
    expect(within(step(5)).queryByText("Low expected counts lower the confidence.")).not.toBeInTheDocument(); // no confidence shown, so nothing to explain
    expect(within(step(7)).getByRole("button", { name: /Open the explorer/ })).toBeInTheDocument();
  });

  it("leaves out only what is missing: no clusters endpoint means no 'papers in no cluster', but the rest stays", async () => {
    vi.mocked(api.clusters).mockImplementation(down);
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    await waitFor(() => expect(within(step(6)).getByText(/citations verified/)).toBeInTheDocument());
    expect(within(step(3)).queryByText("Papers in no cluster")).not.toBeInTheDocument();
    expect(within(step(3)).getByText("Clusters", { selector: ".mono-label" })).toBeInTheDocument(); // the count falls back to the landscape's
    expect(within(step(1)).getByText("1,999")).toBeInTheDocument();
  });

  it("shows no verified-citations line when the explanation's own check did not pass in full", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation({ citation_check: { ok: false, cited: ["WN1", "WZZ"], unknown: ["WZZ"], uncited_markers_count: 0, has_no_citations: false } }));
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    await waitFor(() => expect(within(step(4)).getByText("399")).toBeInTheDocument());
    expect(within(step(6)).queryByText(/citations verified/)).not.toBeInTheDocument();
    expect(within(step(6)).getByText("WN1")).toBeInTheDocument(); // the evidence itself is still listed
  });
});

describe("story step 05: the confidence sentence", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());
  const SENTENCE = "Low expected counts lower the confidence.";

  async function withConfidence(confidence: number | null) {
    const list = makeOpportunityList();
    list.items[1] = { ...list.items[1]!, confidence }; // opportunity 7 is the top one
    vi.mocked(api.opportunities).mockResolvedValue(list);
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    await waitFor(() => expect(within(step(4)).getByText("399")).toBeInTheDocument());
  }

  it("is shown when the confidence shown is below 1.00", async () => {
    await withConfidence(0.32);
    expect(within(step(5)).getByText("0.32")).toBeInTheDocument();
    expect(within(step(5)).getByText(SENTENCE)).toBeInTheDocument();
  });

  it("is shown for 0.994, which is displayed as 0.99", async () => {
    await withConfidence(0.994);
    expect(within(step(5)).getByText("0.99")).toBeInTheDocument();
    expect(within(step(5)).getByText(SENTENCE)).toBeInTheDocument();
  });

  it("is not shown at 1.00, nor for 0.996 (displayed as 1.00)", async () => {
    await withConfidence(1);
    expect(within(step(5)).getByText("1.00")).toBeInTheDocument();
    expect(within(step(5)).queryByText(SENTENCE)).not.toBeInTheDocument();
  });

  it("is not shown when 0.996 is displayed as 1.00", async () => {
    await withConfidence(0.996);
    expect(within(step(5)).getByText("1.00")).toBeInTheDocument();
    expect(within(step(5)).queryByText(SENTENCE)).not.toBeInTheDocument();
  });

  it("is not shown when there is no confidence to show", async () => {
    await withConfidence(null);
    expect(within(step(5)).queryByText("Confidence")).not.toBeInTheDocument();
    expect(within(step(5)).queryByText(SENTENCE)).not.toBeInTheDocument();
  });
});

describe("story steps: the card content is centred", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());

  it("centres every step's content vertically in its card (min-h-full, so a tall step can still scroll)", async () => {
    restore = setReducedMotion(true);
    render(<StoryView onOpenExplorer={() => {}} />);
    for (let i = 0; i < 8; i += 1) {
      const wrapper = step(i).firstElementChild as HTMLElement;
      expect(wrapper.className).toContain("justify-center");
      expect(wrapper.className).toContain("min-h-full");
      expect(wrapper.className).not.toMatch(/(^|\s)h-full(\s|$)/);
    }
  });
});

describe("story steps: the pinned stage", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => restore());

  it("keeps the final numbers in the DOM, and fills a step's bars only once that step is active", async () => {
    render(<StoryView onOpenExplorer={() => {}} />);
    await waitFor(() => expect(within(step(3)).getByText("883")).toBeInTheDocument()); // the final value is in the DOM text even for a step that is not on screen
    await waitFor(() => expect(within(step(4)).getByRole("meter", { name: "Observed" })).toBeInTheDocument());
    const fill = () => within(step(4)).getByRole("meter", { name: "Expected" }).firstElementChild as HTMLElement;
    expect(fill().style.width).toBe("0%"); // not active yet
    const cfg = vi.mocked(ScrollTrigger.create).mock.calls.at(-1)![0] as unknown as { onUpdate: (s: { progress: number }) => void };
    act(() => cfg.onUpdate({ progress: 0.55 })); // step 4
    expect(fill().style.width).toBe("100%");
  });

  it("under reduced motion the bars are full at once", async () => {
    restore = await renderStacked();
    const fill = within(step(4)).getByRole("meter", { name: "Expected" }).firstElementChild as HTMLElement;
    expect(fill.style.width).toBe("100%");
  });
});
