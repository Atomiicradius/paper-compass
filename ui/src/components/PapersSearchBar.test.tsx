import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PapersSearchBar, MODE_SEGMENTS } from "@/components/PapersSearchBar";
import type { SearchForm } from "@/components/Sidebar";

const BASE: SearchForm = { query: "", mode: "auto", collapse: true, years: [1951, 2026] };

function Host({ initial = BASE, onSearch = () => {}, searching = false, onForm = () => {} }: { initial?: SearchForm; onSearch?: () => void; searching?: boolean; onForm?: (f: SearchForm) => void }) {
  const [form, setForm] = useState(initial);
  return (
    <PapersSearchBar form={form} onForm={(f) => { setForm(f); onForm(f); }} onSearch={onSearch} searching={searching}>
      <p>under the controls</p>
    </PapersSearchBar>
  );
}
const box = () => screen.getByRole("textbox", { name: "Search the corpus" });
const radios = () => within(screen.getByRole("radiogroup", { name: "Search mode" })).getAllByRole("radio");

describe("PapersSearchBar", () => {
  it("has a large search box with the existing placeholder, a Search button, and shows what is passed as children", () => {
    render(<Host />);
    expect(box()).toHaveAttribute("placeholder", "Describe a research idea…");
    expect(box().className).toContain("h-14"); // large
    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
    expect(screen.getByText("under the controls")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Paper search" })).toBeInTheDocument();
  });

  it("disables Search for a blank query and submits (button or Enter) otherwise, like the old search box", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    render(<Host onSearch={onSearch} />);
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
    await user.type(box(), "  ");
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled(); // whitespace only
    await user.type(box(), "back-translation{Enter}");
    expect(onSearch).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(onSearch).toHaveBeenCalledTimes(2);
  });

  it("edits the shared state: typing sets the query, and the clear button empties it", async () => {
    const user = userEvent.setup();
    const onForm = vi.fn();
    render(<Host onForm={onForm} />);
    await user.type(box(), "ab");
    expect(onForm).toHaveBeenLastCalledWith({ ...BASE, query: "ab" });
    await user.click(screen.getByRole("button", { name: "Clear search text" }));
    expect(onForm).toHaveBeenLastCalledWith({ ...BASE, query: "" });
    expect(box()).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Clear search text" })).not.toBeInTheDocument();
  });

  it("shows 'Searching…' and cannot be pressed again while a search runs", () => {
    render(<Host initial={{ ...BASE, query: "x" }} searching />);
    expect(screen.getByRole("button", { name: "Searching…" })).toBeDisabled();
  });

  it("has a segmented control with the four modes, the current one checked", () => {
    render(<Host initial={{ ...BASE, mode: "keyword" }} />);
    expect(MODE_SEGMENTS.map((s) => s.mode)).toEqual(["auto", "vector", "keyword", "hybrid"]);
    expect(radios().map((r) => r.textContent)).toEqual(["Auto", "Vector", "Keyword", "Hybrid"]);
    expect(radios().map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "false", "true", "false"]);
    expect(radios()[3]).toHaveAttribute("title", "Hybrid (vector + keyword)"); // the full name of the mode, as in the old dropdown
  });

  it("a click chooses a mode and leaves the rest of the state alone", async () => {
    const user = userEvent.setup();
    const onForm = vi.fn();
    render(<Host initial={{ ...BASE, query: "q" }} onForm={onForm} />);
    await user.click(screen.getByRole("radio", { name: "Hybrid" }));
    expect(onForm).toHaveBeenLastCalledWith({ ...BASE, query: "q", mode: "hybrid" });
    expect(screen.getByRole("radio", { name: "Hybrid" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "false");
  });

  it("the arrow keys move through the modes (wrapping) and the focus follows; only the checked one is in the tab order", async () => {
    const user = userEvent.setup();
    render(<Host />);
    expect(radios().map((r) => r.tabIndex)).toEqual([0, -1, -1, -1]);
    radios()[0]!.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Vector" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Vector" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}"); // Auto, then wraps to Hybrid
    expect(screen.getByRole("radio", { name: "Hybrid" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Hybrid" })).toHaveFocus();
    await user.keyboard("{ArrowRight}"); // wraps to Auto
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  });

  it("has the 'Hide duplicate records of one title' switch in view, on by default, and toggles the shared state", async () => {
    const user = userEvent.setup();
    const onForm = vi.fn();
    render(<Host onForm={onForm} />);
    const sw = screen.getByRole("switch", { name: "Hide duplicate records of one title" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    await user.click(sw);
    expect(onForm).toHaveBeenLastCalledWith({ ...BASE, collapse: false });
    expect(screen.getByRole("switch", { name: "Hide duplicate records of one title" })).toHaveAttribute("aria-checked", "false");
    await user.click(screen.getByText("Hide duplicate records of one title")); // the label works too
    expect(screen.getByRole("switch", { name: "Hide duplicate records of one title" })).toHaveAttribute("aria-checked", "true");
  });

  it("shows whatever query the rest of the app put into the shared state (the command bar's search lands here)", () => {
    render(<Host initial={{ ...BASE, query: "back-translation for low-resource languages", mode: "hybrid" }} />);
    expect(box()).toHaveValue("back-translation for low-resource languages");
    expect(screen.getByRole("radio", { name: "Hybrid" })).toHaveAttribute("aria-checked", "true");
  });
});
