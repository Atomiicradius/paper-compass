import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, type CandidateFilters } from "@/lib/opportunities";
import { activeFilterChips, activeTotal, clearedFilters, removeFilterChip, yearsChanged } from "@/lib/filter-chips";

const BOUNDS: [number, number] = [1951, 2026];
const some: CandidateFilters = { methods: ["Back-translation", "Transformer"], tasks: ["Machine Translation"], datasets: ["FLORES-200"], settings: ["Low-resource"], minConfidence: 0.5 };

describe("active filters as chips", () => {
  it("has no chips and a count of 0 when nothing is set", () => {
    expect(activeFilterChips(EMPTY_FILTERS, BOUNDS, BOUNDS)).toEqual([]);
    expect(activeTotal(EMPTY_FILTERS, BOUNDS, BOUNDS)).toBe(0);
    expect(yearsChanged(BOUNDS, BOUNDS)).toBe(false);
  });

  it("makes one chip for every selected name, the raised confidence and the narrowed years, and the count is the number of chips", () => {
    const chips = activeFilterChips(some, [1990, 2020], BOUNDS);
    expect(chips.map((c) => c.label)).toEqual([
      "Years 1990–2020", "Method: Back-translation", "Method: Transformer", "Task: Machine Translation", "Dataset: FLORES-200", "Setting: Low-resource", "Confidence ≥ 0.50",
    ]);
    expect(activeTotal(some, [1990, 2020], BOUNDS)).toBe(chips.length);
    expect(new Set(chips.map((c) => c.key)).size).toBe(chips.length); // unique keys
  });

  it("counts a changed year range once, whichever end moved", () => {
    expect(activeTotal(EMPTY_FILTERS, [1990, 2026], BOUNDS)).toBe(1);
    expect(activeTotal(EMPTY_FILTERS, [1951, 2010], BOUNDS)).toBe(1);
    expect(activeFilterChips(EMPTY_FILTERS, [1951, 2010], BOUNDS)[0]!.label).toBe("Years 1951–2010");
  });

  it("removes exactly one name from its group", () => {
    const chip = activeFilterChips(some, BOUNDS, BOUNDS).find((c) => c.label === "Method: Back-translation")!;
    const next = removeFilterChip(chip, some, BOUNDS, BOUNDS);
    expect(next.filters.methods).toEqual(["Transformer"]);
    expect(next.filters.tasks).toEqual(some.tasks); // the rest is untouched
    expect(next.filters.minConfidence).toBe(0.5);
    expect(next.years).toEqual(BOUNDS);
  });

  it("removes each of the other groups: task, dataset, setting, confidence and years", () => {
    const find = (label: string) => activeFilterChips(some, [1990, 2020], BOUNDS).find((c) => c.label === label)!;
    expect(removeFilterChip(find("Task: Machine Translation"), some, [1990, 2020], BOUNDS).filters.tasks).toEqual([]);
    expect(removeFilterChip(find("Dataset: FLORES-200"), some, [1990, 2020], BOUNDS).filters.datasets).toEqual([]);
    expect(removeFilterChip(find("Setting: Low-resource"), some, [1990, 2020], BOUNDS).filters.settings).toEqual([]);
    expect(removeFilterChip(find("Confidence ≥ 0.50"), some, [1990, 2020], BOUNDS).filters.minConfidence).toBe(0);
    const years = removeFilterChip(find("Years 1990–2020"), some, [1990, 2020], BOUNDS);
    expect(years.years).toEqual(BOUNDS);
    expect(years.filters).toEqual(some); // removing the years does not touch the other filters
  });

  it("clears everything to the state the app starts with, and does not share the bounds array", () => {
    const cleared = clearedFilters(BOUNDS);
    expect(cleared.filters).toEqual(EMPTY_FILTERS);
    expect(cleared.years).toEqual(BOUNDS);
    expect(cleared.years).not.toBe(BOUNDS);
  });
});
