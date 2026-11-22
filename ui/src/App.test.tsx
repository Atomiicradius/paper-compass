import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";

vi.mock("@/components/story/NetworkCanvas", async () => {
  const React = await import("react");
  return { default: ({ step, groupSizes }: { step: number; groupSizes: number[] }) => React.createElement("div", { "data-testid": "network-canvas", "data-canvas-step": step, "data-groups": groupSizes.join(",") }) };
});

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn(), search: vi.fn() } };
});
import { api } from "@/api/client";
import App from "@/App";

const nav = () => within(screen.getByRole("navigation", { name: "Views" }));

describe("App: the story is the landing view", () => {
  beforeEach(() => {
    vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
    vi.mocked(api.clusters).mockResolvedValue(makeClusters());
    vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
    vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
    vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
  });
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("opens on the story when there is no hash, with Story as the first navigation item", async () => {
    window.history.replaceState(null, "", "/");
    render(<App />);
    expect(nav().getAllByRole("button").map((b) => b.textContent)).toEqual(["Story", "Candidates", "Papers", "Graph", "Landscape"]);
    expect(nav().getByRole("button", { name: "Story" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    expect(window.location.hash).toBe("");
  });

  it("'Open the explorer' goes to the Candidates screen and writes #/candidates", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /Open the explorer/ }));
    expect(nav().getByRole("button", { name: "Candidates" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/candidates"));
  });

  it("#/story opens the story and #/candidates opens the explorer directly", async () => {
    window.history.replaceState(null, "", "#/story");
    const first = render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    first.unmount();

    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" })).toBeInTheDocument();
    expect(nav().getByRole("button", { name: "Candidates" })).toHaveAttribute("aria-current", "page");
  });

  it("the other screens are still reachable from the navigation", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    await user.click(nav().getByRole("button", { name: "Landscape" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Landscape" })).toBeInTheDocument();
    await user.click(nav().getByRole("button", { name: "Story" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
  });
});

describe("App: the command palette", () => {
  beforeEach(() => {
    vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
    vi.mocked(api.clusters).mockResolvedValue(makeClusters());
    vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
    vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
    vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
    vi.mocked(api.search).mockReset();
    vi.mocked(api.search).mockResolvedValue({ query: "q", mode: "hybrid", score_type: "rrf_fused", model: null, note: null, results: [] } as never);
  });
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("opens with Ctrl+K from anywhere and closes with Escape", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument());
  });

  it("opens from the command bar in the header, which shows the hint", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    const bar = screen.getByRole("button", { name: /Search or jump to…/ });
    expect(bar).toHaveTextContent("⌘K");
    await user.click(bar);
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });

  it("'Go to' changes the screen", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    await user.keyboard("{Control>}k{/Control}");
    await user.type(await screen.findByRole("combobox", { name: "Search or jump to" }), "landsc{Enter}");
    expect(await screen.findByRole("heading", { level: 2, name: "Landscape" })).toBeInTheDocument();
    expect(nav().getByRole("button", { name: "Landscape" })).toHaveAttribute("aria-current", "page");
  });

  it("'Search papers' runs the existing paper search with the typed text in the current mode and opens Papers", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/");
    render(<App />);
    await user.selectOptions(screen.getByLabelText("Search mode"), "hybrid"); // the mode chosen in the existing control
    await user.keyboard("{Control>}k{/Control}");
    await user.type(await screen.findByRole("combobox", { name: "Search or jump to" }), "back-translation for low-resource languages{Enter}");
    await waitFor(() => expect(api.search).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.search).mock.calls[0]![0]).toMatchObject({ query: "back-translation for low-resource languages", mode: "hybrid", collapse_same_title: true });
    expect(nav().getByRole("button", { name: "Papers" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { level: 2, name: "Papers" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
    // the same text is now in the search box, so it can be edited and run again
    expect(screen.getByPlaceholderText("Describe a research idea…")).toHaveValue("back-translation for low-resource languages");
  });

  it("has a sliding indicator on the active tab only", async () => {
    window.history.replaceState(null, "", "/");
    render(<App />);
    const active = nav().getByRole("button", { name: "Story" });
    expect(active.querySelectorAll("[aria-hidden]")).toHaveLength(1); // the indicator
    expect(nav().getByRole("button", { name: "Papers" }).querySelectorAll("[aria-hidden]")).toHaveLength(0);
  });
});
