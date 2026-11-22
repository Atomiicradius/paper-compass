import { SlidersHorizontal, X } from "lucide-react";
import type { FilterChip } from "@/lib/filter-chips";
import { Badge, Button } from "@/components/ui/primitives";

export interface FilterToolbarProps {
  /** how many filters are active */
  count: number;
  chips: FilterChip[];
  onOpen: () => void;
  onRemove: (chip: FilterChip) => void;
  onClearAll: () => void;
}

/** The "Filters" button (with the number of active filters), the active filters as removable chips, and "Clear all". */
export function FilterToolbar({ count, chips, onOpen, onRemove, onClearAll }: FilterToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="filter-toolbar">
      <Button variant="outline" size="sm" aria-haspopup="dialog" aria-label={count ? `Filters, ${count} active` : "Filters"} onClick={onOpen}>
        <SlidersHorizontal className="size-3.5" aria-hidden /> Filters
        {count ? <Badge data-testid="filter-count" className="border-primary/40 bg-primary/10 px-1.5 py-0 font-mono text-primary">{count}</Badge> : null}
      </Button>
      {chips.length ? (
        <ul aria-label="Active filters" className="m-0 flex list-none flex-wrap items-center gap-2 p-0">
          {chips.map((chip) => (
            <li key={chip.key}>
              <button
                type="button"
                aria-label={`Remove filter: ${chip.label}`}
                onClick={() => onRemove(chip)}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 py-0.5 pr-1.5 pl-3 text-xs text-foreground transition-colors hover:bg-primary/20"
              >
                {chip.label}
                <X className="size-3 text-muted" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {count ? (
        <button type="button" onClick={onClearAll} className="cursor-pointer text-xs text-primary underline">
          Clear all
        </button>
      ) : null}
    </div>
  );
}
