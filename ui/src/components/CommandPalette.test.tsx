import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { View } from "@/lib/route";
import { CommandPalette, paletteItems } from "@/components/CommandPalette";

const VIEWS = [
  { id: "story" as View, label: "Story" },
  { id: "candidates" as View, label: "Candidates" },
  { id: "papers" as View, label: "Papers" },
  { id: "graph" as View, label: "Graph" },
  { id: "landscape" as View, label: "Landscape" },
];

function setup(over: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  const onOpenChange = vi.fn();
  const onGo = vi.fn();
  const onSearch = vi.fn();
  const view = render(<CommandPalette open onOpenChange={onOpenChange} views={VIEWS} currentView="candidates" onGo={onGo} onSearch={onSearch} {...over} />);
  return { onOpenChange, onGo, onSearch, ...view, user: userEvent.setup() };
}
const input = () => screen.getByRole("combobox", { name: "Search or jump to" });
const options = () => within(screen.getByRole("listbox", { name: "Commands" })).getAllByRole("option");
const active = () => options().find((o) => o.getAttribute("aria-selected") === "true");

describe("paletteItems", () => {
  it("lists every screen when nothing is typed, and no search action", () => {
    const { go, search } = paletteItems(VIEWS, "candidates", "");
    expect(go.map((i) => i.label)).toEqual(["Story", "Candidates", "Papers", "Graph", "Landscape"]);
    expect(search).toEqual([]);
    expect(go.find((i) => i.label === "Candidates")!.hint).toBe("current");
  });

  it("filters the screens by what is typed (any case) and always offers the search for non-blank text", () => {
    const r = paletteItems(VIEWS, "story", "  GRA ");
    expect(r.go.map((i) => i.label)).toEqual(["Graph"]);
    expect(r.search).toHaveLength(1);
    expect(r.search[0]).toMatchObject({ kind: "search", text: "GRA", label: "Search papers for “GRA”" }); // trimmed
    expect(paletteItems(VIEWS, "story", "   ").search).toEqual([]); // blank is not a query
  });
});

describe("CommandPalette", () => {
  it("is a dialog with a combobox over a listbox, the box has focus, and 'Go to' lists the five screens", () => {
    setup();
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(input()).toHaveFocus();
    expect(input()).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByRole("listbox", { name: "Commands" });
    expect(input()).toHaveAttribute("aria-controls", list.id);
    expect(within(list).getByRole("group", { name: "Go to" })).toBeInTheDocument();
    expect(options().map((o) => o.textContent?.replace(/current$/, ""))).toEqual(["Story", "Candidates", "Papers", "Graph", "Landscape"]);
    expect(within(options()[1]!).getByText("current")).toBeInTheDocument();
  });

  it("filters as you type and adds the 'Search papers' action", async () => {
    const { user } = setup();
    await user.type(input(), "gra");
    expect(options().map((o) => o.textContent)).toEqual(["Graph", "Search papers for “gra”"]);
    expect(screen.getByRole("group", { name: "Search papers" })).toBeInTheDocument();
    await user.clear(input());
    expect(options()).toHaveLength(5);
    expect(screen.queryByRole("group", { name: "Search papers" })).not.toBeInTheDocument();
  });

  it("moves with the arrow keys (wrapping), Home and End, and keeps aria-activedescendant on the highlighted option", async () => {
    const { user } = setup();
    expect(active()!.textContent).toBe("Story");
    expect(input()).toHaveAttribute("aria-activedescendant", active()!.id);
    await user.keyboard("{ArrowDown}");
    expect(active()!.textContent).toMatch(/^Candidates/);
    expect(input()).toHaveAttribute("aria-activedescendant", active()!.id);
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(active()!.textContent).toBe("Landscape");
    await user.keyboard("{ArrowDown}"); // wraps to the first
    expect(active()!.textContent).toBe("Story");
    await user.keyboard("{ArrowUp}"); // and back to the last
    expect(active()!.textContent).toBe("Landscape");
    await user.keyboard("{Home}");
    expect(active()!.textContent).toBe("Story");
    await user.keyboard("{End}");
    expect(active()!.textContent).toBe("Landscape");
    expect(options().filter((o) => o.getAttribute("aria-selected") === "true")).toHaveLength(1);
  });

  it("Enter on a screen goes there and closes", async () => {
    const { user, onGo, onOpenChange, onSearch } = setup();
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}"); // Papers
    expect(onGo).toHaveBeenCalledWith("papers");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("Enter on the search action runs the paper search with the trimmed text and closes", async () => {
    const { user, onGo, onOpenChange, onSearch } = setup();
    await user.type(input(), "  back-translation for low-resource languages ");
    expect(active()!.textContent).toBe("Search papers for “back-translation for low-resource languages”"); // no screen matches: the search is first
    await user.keyboard("{Enter}");
    expect(onSearch).toHaveBeenCalledWith("back-translation for low-resource languages");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onGo).not.toHaveBeenCalled();
  });

  it("typing a screen's name highlights that screen, and the search action is one arrow key away", async () => {
    const { user, onGo, onSearch } = setup();
    await user.type(input(), "papers");
    expect(active()!.textContent).toMatch(/^Papers/);
    await user.keyboard("{ArrowDown}");
    expect(active()!.textContent).toBe("Search papers for “papers”");
    await user.keyboard("{ArrowUp}{Enter}");
    expect(onGo).toHaveBeenCalledWith("papers");
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("Enter with blank text and no screen to pick does nothing harmful: a blank query is never searched", async () => {
    const { user, onSearch } = setup();
    await user.type(input(), "   ");
    expect(options().some((o) => /Search papers for/.test(o.textContent ?? ""))).toBe(false);
    await user.keyboard("{Enter}"); // runs the highlighted screen (the first), never a search
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("a click runs an action", async () => {
    const { user, onGo, onOpenChange } = setup();
    await user.click(options()[3]!);
    expect(onGo).toHaveBeenCalledWith("graph");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("Escape asks to close", async () => {
    const { user, onOpenChange } = setup();
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps the focus inside the dialog when Tab is pressed (focus trap)", async () => {
    const { user } = setup();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("renders nothing when closed, and starts empty each time it opens", async () => {
    const { rerender, user, onOpenChange, onGo, onSearch } = setup();
    await user.type(input(), "gra");
    rerender(<CommandPalette open={false} onOpenChange={onOpenChange} views={VIEWS} currentView="candidates" onGo={onGo} onSearch={onSearch} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<CommandPalette open onOpenChange={onOpenChange} views={VIEWS} currentView="candidates" onGo={onGo} onSearch={onSearch} />);
    expect(input()).toHaveValue("");
    expect(options()).toHaveLength(5);
  });

  it("marks the list as its own scroll area for Lenis", () => {
    setup();
    expect(screen.getByRole("listbox", { name: "Commands" })).toHaveAttribute("data-lenis-prevent");
  });
});
