import { activeTotal, clearedFilters } from "@/lib/filter-chips";
import type { CandidateFilters } from "@/lib/opportunities";
import { Badge } from "@/components/ui/primitives";
import { SlideOver } from "@/components/motion";
import { FilterSections, type FilterOptions, type SearchForm } from "@/components/Sidebar";

export interface FiltersPanelProps {
  open: boolean;
  onClose: () => void;
  form: SearchForm;
  onForm: (f: SearchForm) => void;
  filters: CandidateFilters;
  onFilters: (f: CandidateFilters) => void;
  options: FilterOptions;
  yearBounds: [number, number];
}

/**
 * All the filter controls (publication year, methods, tasks, datasets, settings, confidence, search options) in a
 * slide-over panel. Esc, the close button and a click outside close it (the dialog is the app's SlideOver). The header shows
 * how many filters are active and clears them all.
 */
export function FiltersPanel({ open, onClose, form, onForm, filters, onFilters, options, yearBounds }: FiltersPanelProps) {
  const total = activeTotal(filters, form.years, yearBounds);
  const clearAll = () => {
    const cleared = clearedFilters(yearBounds);
    onFilters(cleared.filters);
    onForm({ ...form, years: cleared.years });
  };
  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title="Filters"
      description="Narrow the candidate opportunities and the paper search by year, method, task, dataset, setting and confidence"
      widthClass="w-full max-w-md"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-border p-5 pr-16">
          <div className="flex items-center gap-2.5">
            <p aria-hidden className="display-heading display-md">Filters</p>
            {total ? <Badge data-testid="panel-filter-count" className="border-primary/40 bg-primary/10 px-1.5 py-0 font-mono text-primary">{total}</Badge> : null}
          </div>
          {total ? (
            <button type="button" onClick={clearAll} className="cursor-pointer text-xs text-primary underline">
              Clear all
            </button>
          ) : null}
        </div>
        <div data-lenis-prevent className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-6">
          <FilterSections form={form} onForm={onForm} filters={filters} onFilters={onFilters} options={options} yearBounds={yearBounds} />
        </div>
      </div>
    </SlideOver>
  );
}
