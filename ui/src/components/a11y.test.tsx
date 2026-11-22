import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { useState } from "react";
import { EMPTY_FILTERS } from "@/lib/opportunities";
import type { SearchFormState } from "@/lib/search";
import { makeExplanation, makeOpportunities, makeOpportunity } from "@/test/fixtures";
import { TooltipProvider } from "@/components/ui/primitives";
import { CandidateDetail } from "@/components/CandidateDetail";
import { CandidateRow } from "@/components/CandidateRow";
import { CandidatesView } from "@/components/CandidatesView";
import { FiltersPanel } from "@/components/FiltersPanel";

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
  it("a candidate detail has valid roles and one named evidence button", async () => {
    const { container } = wrap(<CandidateDetail opportunity={makeOpportunity(14)} rank={1} score={73.7} scoreLabel="" onOpenEvidence={() => {}} />);
    expect(await violations(container)).toEqual([]);
    const detail = screen.getByTestId("candidate-detail");
    expect(within(detail).getAllByRole("button")).toHaveLength(1);
    expect(within(detail).getByRole("button", { name: /Evidence & explanation/ })).toBeInTheDocument();
  });

  it("the ranked list (a listbox of options), the detail and the what-if panel pass", async () => {
    const user = userEvent.setup();
    const { container } = wrap(<CandidatesView state={{ data: { items: makeOpportunities(), total: 13 }, error: null, loading: false, reload: () => {} }}
      filters={EMPTY_FILTERS} selectedId={null} onSelect={() => {}} onClearFilters={() => {}} />);
    await user.click(screen.getByRole("button", { name: /What-if weights/ }));
    expect(await violations(container)).toEqual([]);
  });

  it("the filters panel (checkboxes, three sliders, switch; it replaced the sidebar) passes", async () => {
    const user = userEvent.setup();
    function Host() {
      const [form, setForm] = useState<SearchFormState>({ query: "", mode: "auto", collapse: true, years: [1951, 2026] });
      return <FiltersPanel open onClose={() => {}} form={form} onForm={setForm} filters={EMPTY_FILTERS} onFilters={() => {}}
        options={{ methods: ["Back-translation", "Transformer"], tasks: ["Machine Translation"], datasets: ["FLORES-200"], settings: [] }} yearBounds={[1951, 2026]} />;
    }
    wrap(<Host />);
    for (const name of [/Tasks/, /Datasets/, /Settings/, /Search options/]) await user.click(screen.getByRole("button", { name }));
    expect(await violations(document.body)).toEqual([]);
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
  it("the ranked list is exactly one tab stop: the rows are options, not tab stops", async () => {
    const user = userEvent.setup();
    wrap(<>
      <div role="listbox" aria-label="list" tabIndex={0}>
        <CandidateRow opportunity={makeOpportunity(14)} rank={1} selected score={73.7} onSelect={() => {}} />
        <CandidateRow opportunity={makeOpportunity(15)} rank={2} selected={false} score={70} onSelect={() => {}} />
      </div>
    </>);
    for (const row of screen.getAllByTestId("candidate-row")) expect(row).not.toHaveAttribute("tabindex");
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("listbox"));
    await user.tab();
    expect(document.activeElement).toBe(document.body);
  });

  it("opening the evidence drawer moves focus into it, Tab stays inside, Escape closes it and focus returns to where it came from", async () => {
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
