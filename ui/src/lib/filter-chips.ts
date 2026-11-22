import { activeFilterCount, EMPTY_FILTERS, type CandidateFilters } from "@/lib/opportunities";

export type ChipGroup = "method" | "task" | "dataset" | "setting" | "confidence" | "years";

/** One active filter, shown as a removable chip under the screen title. */
export interface FilterChip {
  key: string;
  label: string;
  group: ChipGroup;
  /** the selected name, for the four checklist groups */
  value?: string;
}

type Years = [number, number];
const GROUP_LABELS = { method: "Method", task: "Task", dataset: "Dataset", setting: "Setting" } as const;

export function yearsChanged(years: Years, bounds: Years): boolean {
  return years[0] !== bounds[0] || years[1] !== bounds[1];
}

/** How many filters are active: every selected name, the minimum confidence if raised, the year range if narrowed. */
export function activeTotal(filters: CandidateFilters, years: Years, bounds: Years): number {
  return activeFilterCount(filters) + (yearsChanged(years, bounds) ? 1 : 0);
}

/** The active filters as chips, in a fixed order: years, methods, tasks, datasets, settings, confidence. One chip per count. */
export function activeFilterChips(filters: CandidateFilters, years: Years, bounds: Years): FilterChip[] {
  const chips: FilterChip[] = [];
  if (yearsChanged(years, bounds)) chips.push({ key: "years", label: `Years ${years[0]}–${years[1]}`, group: "years" });
  for (const group of ["method", "task", "dataset", "setting"] as const) {
    const names = filters[(group + "s") as "methods" | "tasks" | "datasets" | "settings"];
    for (const name of names) chips.push({ key: `${group}:${name}`, label: `${GROUP_LABELS[group]}: ${name}`, group, value: name });
  }
  if (filters.minConfidence > 0) chips.push({ key: "confidence", label: `Confidence ≥ ${filters.minConfidence.toFixed(2)}`, group: "confidence" });
  return chips;
}

/** The filter state with one chip's filter removed. The years go back to the full range, the confidence to 0. */
export function removeFilterChip(chip: FilterChip, filters: CandidateFilters, years: Years, bounds: Years): { filters: CandidateFilters; years: Years } {
  if (chip.group === "years") return { filters, years: [bounds[0], bounds[1]] };
  if (chip.group === "confidence") return { filters: { ...filters, minConfidence: 0 }, years };
  const field = (chip.group + "s") as "methods" | "tasks" | "datasets" | "settings";
  return { filters: { ...filters, [field]: filters[field].filter((n) => n !== chip.value) }, years };
}

/** Everything cleared: the same state as the app starts with. */
export function clearedFilters(bounds: Years): { filters: CandidateFilters; years: Years } {
  return { filters: EMPTY_FILTERS, years: [bounds[0], bounds[1]] };
}
