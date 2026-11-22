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

  it("opens on the story when there is no hash; the story is the home page, not a tab, and no tab is highlighted", async () => {
    window.history.replaceState(null, "", "/");
    render(<App />);
    expect(nav().getAllByRole("button").map((b) => b.textContent)).toEqual(["Candidates", "Papers", "Graph", "Landscape"]);
    expect(nav().queryByRole("button", { name: "Story" })).not.toBeInTheDocument();
    for (const tab of nav().getAllByRole("button")) expect(tab).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Paper Compass home" })).toHaveAttribute("aria-current", "page");
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

  it("has no fixed footer bar on any screen", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" });
    for (const tab of ["Candidates", "Papers", "Graph", "Landscape"]) {
      await user.click(nav().getByRole("button", { name: tab }));
      expect(document.querySelector("footer")).toBeNull();
      expect(screen.queryByRole("contentinfo")).toBeNull();
      expect(screen.queryByText(/Evidence-grounded analysis of a curated corpus/)).toBeNull();
    }
  });

  it("a new screen enters with a fade-and-rise: each screen is a fresh element with the screen-enter class", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    const heading = await screen.findByRole("heading", { level: 2, name: "Candidate opportunities" });
    const column = heading.closest(".screen-enter");
    expect(column).not.toBeNull();
    await user.click(nav().getByRole("button", { name: "Landscape" }));
    const next = (await screen.findByRole("heading", { level: 2, name: /Landscape/ })).closest(".screen-enter");
    expect(next).not.toBeNull();
    expect(next).not.toBe(column);
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
    await user.click(screen.getByRole("link", { name: "Paper Compass home" })); // home is the logo
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
    window.history.replaceState(null, "", "#/papers");
    render(<App />);
    await user.click(await screen.findByRole("radio", { name: "Hybrid" })); // the mode chosen in the segmented control of the Papers screen
    await user.keyboard("{Control>}k{/Control}");
    await user.type(await screen.findByRole("combobox", { name: "Search or jump to" }), "back-translation for low-resource languages{Enter}");
    await waitFor(() => expect(api.search).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.search).mock.calls[0]![0]).toMatchObject({ query: "back-translation for low-resource languages", mode: "hybrid", collapse_same_title: true });
    expect(nav().getByRole("button", { name: "Papers" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { level: 2, name: "Papers" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
    // the same text is now in the search box, so it can be edited and run again
    expect(within(screen.getByRole("region", { name: "Paper search" })).getByRole("textbox", { name: "Search the corpus" })).toHaveValue("back-translation for low-resource languages");
    expect(screen.getByRole("radio", { name: "Hybrid" })).toHaveAttribute("aria-checked", "true");
  });

  it("has a sliding indicator on the active tab only, and none on the home page", async () => {
    window.history.replaceState(null, "", "#/candidates");
    render(<App />);
    expect(nav().getByRole("button", { name: "Candidates" }).querySelectorAll("[aria-hidden]")).toHaveLength(1); // the indicator
    expect(nav().getByRole("button", { name: "Papers" }).querySelectorAll("[aria-hidden]")).toHaveLength(0);
    window.history.replaceState(null, "", "/");
  });
});

describe("App: the home link", () => {
  beforeEach(() => {
    vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
    vi.mocked(api.clusters).mockResolvedValue(makeClusters());
    vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
    vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
    vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
  });
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("the logo and name are a keyboard-focusable link to #/story, named 'Paper Compass home'", async () => {
    window.history.replaceState(null, "", "#/landscape");
    render(<App />);
    const home = screen.getByRole("link", { name: "Paper Compass home" });
    expect(home).toHaveAttribute("href", "#/story");
    expect(home.tabIndex).toBeGreaterThanOrEqual(0); // reachable with Tab
    expect(home.className).toContain("hover:bg-hover"); // a hover state
    expect(home).not.toHaveAttribute("aria-current"); // no active state away from the home page
    home.focus();
    expect(home).toHaveFocus();
  });

  it("Enter on the focused link goes home, and the link is then marked as the current page", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/landscape");
    render(<App />);
    screen.getByRole("link", { name: "Paper Compass home" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Paper Compass home" })).toHaveAttribute("aria-current", "page");
    for (const tab of nav().getAllByRole("button")) expect(tab).not.toHaveAttribute("aria-current");
    await waitFor(() => expect(window.location.hash).toBe("")); // the home page is the empty hash
  });

  it("an explicit #/story opens the home page too, and the explorer button still leads to Candidates", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/story");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /Open the explorer/ }));
    expect(nav().getByRole("button", { name: "Candidates" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Paper Compass home" })).not.toHaveAttribute("aria-current");
  });

  it("the command palette calls the story 'Home' in its Go to group, and Enter on it goes home", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "#/landscape");
    render(<App />);
    await user.keyboard("{Control>}k{/Control}");
    const box = await screen.findByRole("combobox", { name: "Search or jump to" });
    const group = screen.getByRole("group", { name: "Go to" });
    expect(within(group).getAllByRole("option").map((o) => o.textContent?.replace(/current$/, ""))).toEqual(["Home", "Candidates", "Papers", "Graph", "Landscape"]);
    expect(within(group).queryByText("Story")).not.toBeInTheDocument();
    await user.type(box, "home{Enter}");
    expect(await screen.findByRole("heading", { level: 2, name: "Paper Compass" })).toBeInTheDocument();
  });
});
