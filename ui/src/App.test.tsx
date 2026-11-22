import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn() } };
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
