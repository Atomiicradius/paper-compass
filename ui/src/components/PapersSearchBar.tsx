import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { Search, X } from "lucide-react";
import { MODE_LABELS, type SearchMode } from "@/lib/search";
import type { SearchForm } from "@/components/Sidebar";
import { cn } from "@/lib/utils";
import { Button, Switch } from "@/components/ui/primitives";

/** The four search modes in the order of the segmented control, with their short names. */
export const MODE_SEGMENTS: { mode: SearchMode; label: string }[] = [
  { mode: "auto", label: "Auto" },
  { mode: "vector", label: "Vector" },
  { mode: "keyword", label: "Keyword" },
  { mode: "hybrid", label: "Hybrid" },
];

export interface PapersSearchBarProps {
  /** the same search state the rest of the app uses (query, mode, the duplicate switch) */
  form: SearchForm;
  onForm: (f: SearchForm) => void;
  /** run the existing paper search with what is in `form` */
  onSearch: () => void;
  searching: boolean;
  /** shown under the controls (the filter button and the active filter chips) */
  children?: ReactNode;
}

/**
 * The search bar at the top of the Papers screen: a large search box, a segmented control for the search mode
 * (Auto / Vector / Keyword / Hybrid) and the switch that hides duplicate records of one title. It edits the same state as
 * every other search control and starts the same search, so the command bar's "Search papers" lands in this box.
 */
export function PapersSearchBar({ form, onForm, onSearch, searching, children }: PapersSearchBarProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const moveMode = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + MODE_SEGMENTS.length) % MODE_SEGMENTS.length;
    onForm({ ...form, mode: MODE_SEGMENTS[next]!.mode });
    refs.current[next]?.focus();
  };

  return (
    <section aria-label="Paper search" className="glass space-y-4 rounded-2xl p-5">
      <form
        role="search"
        className="flex flex-wrap items-center gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onSearch();
        }}
      >
        <div className="relative min-w-0 flex-1 basis-80">
          <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted" aria-hidden />
          <input
            id="papers-q"
            aria-label="Search the corpus"
            value={form.query}
            onChange={(e) => onForm({ ...form, query: e.target.value })}
            placeholder="Describe a research idea…"
            className="h-14 w-full rounded-xl border border-border bg-background/60 pr-11 pl-12 text-lg outline-none transition-shadow focus-visible:border-primary focus-visible:shadow-[0_0_0_4px_color-mix(in_srgb,var(--primary)_18%,transparent)]"
          />
          {form.query ? (
            <button type="button" aria-label="Clear search text" onClick={() => onForm({ ...form, query: "" })} className="absolute top-1/2 right-4 -translate-y-1/2 cursor-pointer text-muted hover:text-foreground">
              <X className="size-5" />
            </button>
          ) : null}
        </div>
        <Button type="submit" className="h-14 shrink-0 px-7 text-base" disabled={searching || !form.query.trim()}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div role="radiogroup" aria-label="Search mode" className="glass inline-flex gap-1 rounded-xl p-1">
          {MODE_SEGMENTS.map((seg, i) => {
            const checked = form.mode === seg.mode;
            return (
              <button
                key={seg.mode}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                type="button"
                role="radio"
                aria-checked={checked}
                tabIndex={checked ? 0 : -1}
                title={MODE_LABELS[seg.mode]}
                onClick={() => onForm({ ...form, mode: seg.mode })}
                onKeyDown={(e) => moveMode(e, i)}
                className={cn(
                  "cursor-pointer rounded-lg px-4 py-1.5 font-mono text-[11px] font-medium tracking-[0.14em] uppercase transition-colors",
                  checked ? "bg-primary text-primary-foreground" : "text-muted hover:text-foreground",
                )}
              >
                {seg.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Switch id="papers-collapse" checked={form.collapse} onCheckedChange={(c) => onForm({ ...form, collapse: c })} />
          <label htmlFor="papers-collapse" className="cursor-pointer">Hide duplicate records of one title</label>
        </div>
      </div>
      {children}
    </section>
  );
}
