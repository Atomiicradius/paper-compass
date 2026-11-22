import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EMPTY_FILTERS, type CandidateFilters } from "@/lib/opportunities";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";
import { setReducedMotion } from "@/test/motion";
import { FiltersPanel } from "@/components/FiltersPanel";
import { TooltipProvider } from "@/components/ui/primitives";
import type { SearchForm } from "@/components/Sidebar";

vi.mock("@/components/story/NetworkCanvas", async () => {
  const React = await import("react");
  return { default: () => React.createElement("div", { "data-testid": "network-canvas" }) };
});
vi.mock("@/components/GraphView", async () => {
  const React = await import("react");
  return { GraphView: ({ filterButton, filterChips }: { filterButton?: React.ReactNode; filterChips?: React.ReactNode }) => React.createElement("section", { "aria-label": "Research graph stub" }, React.createElement("h2", null, "Research graph"), filterButton, filterChips) };
});
vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn(), search: vi.fn() } };
});
import { api } from "@/api/client";
import App from "@/App";

const nav = () => within(screen.getByRole("navigation", { name: "Views" }));
const filtersButton = () => screen.getByRole("button", { name: /^Filters/ });
/** the panel slides out (and the rest of the page is hidden from assistive technology until it has gone) */
const panelGone = () => waitFor(() => expect(screen.queryByRole("dialog", { name: "Filters" })).not.toBeInTheDocument(), { timeout: 5000 });

function mockApi() {
  vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
  vi.mocked(api.clusters).mockResolvedValue(makeClusters());
  vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
  vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
  vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
  vi.mocked(api.search).mockResolvedValue({ query: "q", mode: "auto", score_type: "cosine_similarity", model: null, note: null, results: [] } as never);
}

describe("App: the filters panel replaces the sidebar", () => {
  beforeEach(mockApi);
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("has no permanent left sidebar on any screen, and no Filters button on the story", async () => {
    window.history.replaceState(null, "", "/");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Filters/ })).not.toBeInTheDocument(); // not on the story page
    const user = userEvent.setup();
    for (const screenName of ["Candidates", "Papers", "Graph", "Landscape"]) {
      await user.click(nav().getByRole("button", { name: screenName }));
      expect(screen.queryByLabelText("Search and filters")).not.toBeInTheDocument(); // the old sidebar
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(await screen.findByRole("button", { name: /^Filters/ })).toBeInTheDocument(); // the button is in every screen's header area
    }
  });

  it("opens the panel with all the filter controls, closes it with Escape, and keeps the panel's list as its own scroll area", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /^Filters/ }));
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    for (const name of [/Publication year/, /Methods/, /Tasks/, /Datasets/, /Settings/, /Confidence/, /Search options/]) expect(within(panel).getByRole("button", { name })).toBeInTheDocument();
    expect(within(panel).getAllByRole("slider").map((s) => s.getAttribute("aria-label"))).toEqual(["Publication year range minimum", "Publication year range maximum", "Minimum confidence"]);
    expect(panel.querySelector("[data-lenis-prevent].overflow-y-auto")).not.toBeNull();
    await new Promise((r) => setTimeout(r, 80)); // the dialog registers its Escape listener a moment after it mounts
    // regression: focus used to land on the Close button, whose tooltip took the first Escape (two presses were needed)
    expect(panel).toHaveFocus();
    await user.keyboard("{Escape}"); // one press closes it
    await panelGone();
  });

  it("shows how many filters are active, as removable chips under the title, and the candidates follow the filters", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" })).toBeInTheDocument();
    expect(filtersButton()).toHaveAccessibleName("Filters");
    expect(screen.queryByRole("list", { name: "Active filters" })).not.toBeInTheDocument();

    await user.click(filtersButton());
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(await within(panel).findByRole("checkbox", { name: "Back-translation" }));
    await user.click(within(panel).getByRole("checkbox", { name: "Transformer" }));
    expect(within(panel).getByTestId("panel-filter-count")).toHaveTextContent("2");
    await user.keyboard("{Escape}");
    await panelGone();

    expect(filtersButton()).toHaveAccessibleName("Filters, 2 active");
    expect(screen.getByTestId("filter-count")).toHaveTextContent("2");
    const chips = within(screen.getByRole("list", { name: "Active filters" })).getAllByRole("button").map((b) => b.getAttribute("aria-label"));
    expect(chips).toEqual(["Remove filter: Method: Back-translation", "Remove filter: Method: Transformer"]);
    // the chips sit under the screen title
    const title = screen.getByRole("heading", { level: 2, name: "Candidate opportunities" });
    expect(title.compareDocumentPosition(screen.getByRole("list", { name: "Active filters" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // removing a chip removes that filter only
    await user.click(screen.getByRole("button", { name: "Remove filter: Method: Back-translation" }));
    expect(filtersButton()).toHaveAccessibleName("Filters, 1 active");
    expect(screen.queryByRole("button", { name: "Remove filter: Method: Back-translation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove filter: Method: Transformer" })).toBeInTheDocument();
  });

  it("'Clear all' (next to the chips, and in the panel) removes every filter", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /^Filters/ }));
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(await within(panel).findByRole("checkbox", { name: "Fine-tuning" }));
    expect(within(panel).getByRole("button", { name: "Clear all" })).toBeInTheDocument();
    await user.click(within(panel).getByRole("checkbox", { name: "Beam Search" }));
    await user.click(within(panel).getByRole("button", { name: "Clear all" })); // in the panel
    expect(within(panel).getByRole("checkbox", { name: "Fine-tuning" })).not.toBeChecked();
    expect(within(panel).queryByTestId("panel-filter-count")).not.toBeInTheDocument();
    await user.click(within(panel).getByRole("checkbox", { name: "Fine-tuning" }));
    await user.keyboard("{Escape}");
    await panelGone();
    expect(filtersButton()).toHaveAccessibleName("Filters, 1 active");
    await user.click(screen.getByRole("button", { name: "Clear all" })); // next to the chips
    expect(filtersButton()).toHaveAccessibleName("Filters");
    expect(screen.queryByRole("list", { name: "Active filters" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear all" })).not.toBeInTheDocument();
  });

  it("keeps the filters when the screen changes, and shows them in the Papers page header", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /^Filters/ }));
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(await within(panel).findByRole("checkbox", { name: "Transformer" }));
    await user.keyboard("{Escape}");
    await panelGone();
    await user.click(nav().getByRole("button", { name: "Papers" }));
    const header = (await screen.findByRole("heading", { level: 2, name: "Papers" })).closest("header")!;
    expect(within(header).getByRole("button", { name: "Remove filter: Method: Transformer" })).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Filters, 1 active" })).toBeInTheDocument();
    expect(header.compareDocumentPosition(screen.getByRole("region", { name: "Paper search" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // the header is above the search bar
  });

  it("the search options (the duplicate switch) are in the panel and stay in step with the one on the Papers screen", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/papers");
    render(<App />);
    const bar = await screen.findByRole("region", { name: "Paper search" });
    expect(within(bar).getByRole("switch", { name: "Hide duplicate records of one title" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("button", { name: "Filters" })); // in the page header, above the search bar
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(within(panel).getByRole("button", { name: /Search options/ }));
    const inPanel = await within(panel).findByRole("switch", { name: "Hide duplicate records of one title" });
    await user.click(inPanel);
    expect(inPanel).toHaveAttribute("aria-checked", "false");
    await user.keyboard("{Escape}");
    await panelGone();
    expect(within(screen.getByRole("region", { name: "Paper search" })).getByRole("switch", { name: "Hide duplicate records of one title" })).toHaveAttribute("aria-checked", "false");
  });

  it("the Papers screen's hint points at the search box, not at a left pane", async () => {
    window.history.replaceState(null, "", "#/papers");
    render(<App />);
    expect(await screen.findByText(/Describe a research idea in the search box above and press Search/)).toBeInTheDocument();
    expect(screen.queryByText(/left pane/)).not.toBeInTheDocument();
  });

  it("the content is a wide centred column", async () => {
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    const title = await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" });
    const column = title.closest(".mx-auto");
    expect(column?.className).toContain("max-w-6xl");
  });
});

describe("App: every screen has the same page header", () => {
  beforeEach(mockApi);
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("has a serif title, a description and the Filters button in the actions row on Candidates, Papers and Landscape, and no orphaned filters line", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    for (const [screenName, title] of [["Candidates", "Candidate opportunities"], ["Papers", "Papers"], ["Landscape", "Landscape"]] as const) {
      await user.click(nav().getByRole("button", { name: screenName }));
      const heading = await screen.findByRole("heading", { level: 2, name: title });
      expect(heading).toHaveClass("display-heading");
      const header = heading.closest("header")!;
      expect(header.querySelector("p.text-muted")).not.toBeNull(); // the one-line description
      expect(within(within(header).getByTestId("page-actions")).getByRole("button", { name: /^Filters/ })).toBeInTheDocument();
      // exactly one Filters button on the screen (the old separate line is gone)
      expect(screen.getAllByRole("button", { name: /^Filters/ })).toHaveLength(1);
    }
  });

  it("keeps What-if weights in the Candidates actions row, next to the Filters button", async () => {
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    const actions = within(await screen.findByTestId("page-actions"));
    expect(actions.getByRole("button", { name: /^Filters/ })).toBeInTheDocument();
    expect(actions.getByRole("button", { name: /What-if weights/ })).toBeInTheDocument();
  });

  it("puts the chips under the title on every screen, and Papers has the shared header above its search bar", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/papers");
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /^Filters/ }));
    const panel = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(await within(panel).findByRole("checkbox", { name: "Transformer" }));
    await user.keyboard("{Escape}");
    await panelGone();
    const header = screen.getByRole("heading", { level: 2, name: "Papers" }).closest("header")!;
    expect(within(header).getByTestId("filter-chips")).toBeInTheDocument();
    expect(within(header).queryByRole("region", { name: "Paper search" })).not.toBeInTheDocument();
  });

  it("puts the Graph screen in the same centred column as the others", async () => {
    window.history.replaceState(null, "", "#/graph");
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Research graph" });
    const column = document.querySelector("main > div") as HTMLElement;
    expect(column.className).toContain("max-w-6xl");
    expect(column.className).not.toContain("max-w-none");
  });
});

describe("App with reduced motion", () => {
  let restore = () => {};
  beforeEach(mockApi);
  afterEach(() => {
    restore();
    window.history.replaceState(null, "", "/");
  });

  it("hides nothing and animates nothing: a static ambient layer, instant tab indicator, and every screen still works", async () => {
    restore = setReducedMotion(true);
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    expect(screen.getByTestId("ambient")).toHaveAttribute("data-static");
    expect(await screen.findAllByTestId("candidate-card")).toHaveLength(3); // the three candidates of the fixture
    expect(nav().getByRole("button", { name: "Candidates" })).toHaveAttribute("aria-current", "page");
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: /^Filters/ }));
    expect(await screen.findByRole("dialog", { name: "Filters" })).toBeInTheDocument();
  });
});

describe("FiltersPanel: the year range", () => {
  const BOUNDS: [number, number] = [1951, 2026];
  function Host({ initialYears, onForm }: { initialYears: [number, number]; onForm: (f: SearchForm) => void }) {
    const [form, setForm] = useState<SearchForm>({ query: "", mode: "auto", collapse: true, years: initialYears });
    const [filters, setFilters] = useState<CandidateFilters>(EMPTY_FILTERS);
    return (
      <FiltersPanel open onClose={() => {}} form={form} onForm={(f) => { setForm(f); onForm(f); }} filters={filters} onFilters={setFilters}
        options={{ methods: [], tasks: [], datasets: [], settings: [] }} yearBounds={BOUNDS} />
    );
  }

  it("counts a narrowed year range, and Clear all puts the full range back", async () => {
    const user = userEvent.setup();
    const onForm = vi.fn();
    render(<TooltipProvider><Host initialYears={[1990, 2020]} onForm={onForm} /></TooltipProvider>);
    expect(screen.getByTestId("panel-filter-count")).toHaveTextContent("1");
    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onForm).toHaveBeenLastCalledWith(expect.objectContaining({ years: BOUNDS }));
    expect(screen.queryByTestId("panel-filter-count")).not.toBeInTheDocument();
  });
});
