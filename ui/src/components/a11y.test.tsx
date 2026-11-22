import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { useState } from "react";
import { EMPTY_FILTERS } from "@/lib/opportunities";
import type { SearchFormState } from "@/lib/search";
import { makeExplanation, makeOpportunities, makeOpportunity } from "@/test/fixtures";
import { TooltipProvider } from "@/components/ui/primitives";
import { CandidateCard } from "@/components/CandidateCard";
import { CandidatesView } from "@/components/CandidatesView";
import { Sidebar } from "@/components/Sidebar";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, explain: vi.fn(), rag: vi.fn() } };
});
import { api } from "@/api/client";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";

/**
 * Structural accessibility rules from axe-core, run on rendered components. jsdom has no layout, so colour contrast
 * cannot be checked here (it was checked in a real browser, see ui/README.md); everything else can: valid ARIA
 * roles and attributes, accessible names, labels, heading structure, duplicate ids.
 */
async function violations(container: HTMLElement) {
  const res = await axe.run(container, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false }, "page-has-heading-one": { enabled: false } },
    resultTypes: ["violations"],
  });
  return res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")} (${v.help})`);
}

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

describe("accessibility (axe-core structural rules)", () => {
  it("a candidate card has valid roles, one named button and no nested interactive roles", async () => {
    const { container } = wrap(<CandidateCard opportunity={makeOpportunity(14)} rank={1} selected={false} onOpen={() => {}} score={73.7} scoreLabel="" />);
    expect(await violations(container)).toEqual([]);
    const card = screen.getByTestId("candidate-card");
    expect(card.tagName).toBe("ARTICLE");
    expect(card).not.toHaveAttribute("role");                                  // regression: role=button on an article
    expect(within(card).getAllByRole("button")).toHaveLength(1);
    expect(within(card).getByRole("heading", { level: 3 })).toContainElement(within(card).getByRole("button"));
  });

  it("the whole card list, the what-if panel and pagination pass", async () => {
    const user = userEvent.setup();
    const { container } = wrap(<CandidatesView state={{ data: { items: makeOpportunities(), total: 13 }, error: null, loading: false, reload: () => {} }}
      filters={EMPTY_FILTERS} selectedId={null} onOpen={() => {}} onClearFilters={() => {}} />);
    await user.click(screen.getByRole("button", { name: /What-if weights/ }));
    expect(await violations(container)).toEqual([]);
  });

  it("the sidebar (search, selects, checkboxes, three sliders, switch) passes", async () => {
    const user = userEvent.setup();
    function Host() {
      const [form, setForm] = useState<SearchFormState>({ query: "", mode: "auto", collapse: true, years: [1951, 2026] });
      return <Sidebar form={form} onForm={setForm} onSearch={() => {}} searching={false} filters={EMPTY_FILTERS} onFilters={() => {}}
        options={{ methods: ["Back-translation", "Transformer"], tasks: ["Machine Translation"], datasets: ["FLORES-200"], settings: [] }} yearBounds={[1951, 2026]} />;
    }
    const { container } = wrap(<Host />);
    for (const name of [/Tasks/, /Datasets/, /Settings/, /Search options/]) await user.click(screen.getByRole("button", { name }));
    expect(await violations(container)).toEqual([]);
  });

  it("the evidence drawer is a dialog with a title and description, not an <aside>, and passes", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    wrap(<EvidenceDrawer opportunity={makeOpportunity(14)} onClose={() => {}} onOpenGraph={() => {}} />);
    await screen.findByRole("tab", { name: /Supports A/ });
    const dialog = screen.getByRole("dialog");
    expect(dialog.tagName).toBe("DIV");                                         // regression: role=dialog on <aside>
    expect(dialog).toHaveAccessibleName(/Evidence for Masked Language Modeling/);
    expect(dialog).toHaveAccessibleDescription(/Evidence chain/);
    expect(await violations(document.body)).toEqual([]);
  });
});

describe("keyboard behaviour", () => {
  it("a card is exactly one tab stop: the article itself is not focusable (motion's whileTap adds tabindex=0)", async () => {
    const user = userEvent.setup();
    wrap(<>
      <CandidateCard opportunity={makeOpportunity(14)} rank={1} selected={false} onOpen={() => {}} score={73.7} scoreLabel="" />
      <CandidateCard opportunity={makeOpportunity(15)} rank={2} selected={false} onOpen={() => {}} score={70} scoreLabel="" />
    </>);
    for (const card of screen.getAllByTestId("candidate-card")) expect(card).not.toHaveAttribute("tabindex");
    const stops: string[] = [];
    for (let i = 0; i < 2; i++) { await user.tab(); stops.push(document.activeElement?.tagName ?? "none"); }
    expect(stops).toEqual(["BUTTON", "BUTTON"]);                                   // button, button: one per card
  });

  it("opening the evidence drawer moves focus into it, Tab stays inside, Escape closes it and focus returns to the card", async () => {
    vi.mocked(api.explain).mockResolvedValue(makeExplanation());
    const user = userEvent.setup();
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>open evidence</button>
          <EvidenceDrawer opportunity={open ? makeOpportunity(14) : null} onClose={() => setOpen(false)} onOpenGraph={() => {}} />
          <button>behind the modal</button>
        </>
      );
    }
    wrap(<Host />);
    const opener = screen.getByRole("button", { name: "open evidence" });
    await user.click(opener);
    const dialog = await screen.findByRole("dialog");
    await screen.findByRole("tab", { name: /Supports A/ });
    expect(dialog.contains(document.activeElement)).toBe(true);                    // regression: focus stayed behind the modal
    for (let i = 0; i < 15; i++) {                                                  // more Tabs than there are controls
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);                  // never reaches the page behind
    }
    await user.keyboard("{Escape}");
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(opener));            // focus is returned to where it came from (deferred by Radix)
  }, 30_000);
});
