import { useId, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Search, X } from "lucide-react";
import type { ElementKind } from "@/api/types";
import { KIND_COLORS } from "@/lib/colors";
import { MODE_LABELS, type SearchFormState, type SearchMode } from "@/lib/search";
import { activeFilterCount, EMPTY_FILTERS, type CandidateFilters } from "@/lib/opportunities";
import { cn } from "@/lib/utils";
import { Badge, Button, Checkbox, Slider, Switch, Tip } from "@/components/ui/primitives";

export interface FilterOptions {
  methods: string[];
  tasks: string[];
  datasets: string[];
  settings: string[];
}


export type { SearchMode };
export type SearchForm = SearchFormState;

function Section({ title, count, defaultOpen = true, children, hint }: { title: string; count?: number; defaultOpen?: boolean; children: ReactNode; hint?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className="border-b border-border py-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full cursor-pointer items-center justify-between text-left text-xs font-semibold tracking-wide text-muted uppercase hover:text-foreground"
      >
        <span className="flex items-center gap-2">
          {title}
          {count ? <Badge className="border-primary/40 bg-primary/10 px-1.5 py-0 font-mono text-primary normal-case">{count}</Badge> : null}
        </span>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div id={id} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="pt-3">
              {hint ? <p className="mb-2 text-[11px] leading-snug text-muted">{hint}</p> : null}
              {children}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}

function CheckList({ kind, options, selected, onChange }: { kind: ElementKind; options: string[]; selected: string[]; onChange: (next: string[]) => void }) {
  const [q, setQ] = useState("");
  const shown = options.filter((o) => o.toLowerCase().includes(q.trim().toLowerCase()));
  if (options.length === 0) return <p className="text-xs text-muted italic">None available yet.</p>;
  return (
    <div className="space-y-2">
      {options.length > 10 ? (
        <input
          value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Find a ${kind}…`} aria-label={`Find a ${kind}`}
          className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs outline-none focus-visible:border-primary"
        />
      ) : null}
      <ul className="scroll-thin max-h-44 space-y-1 overflow-y-auto pr-1">
        {shown.map((name) => {
          const checked = selected.includes(name);
          const cid = `${kind}-${name}`;
          return (
            <li key={name} className="flex items-center gap-2">
              <Checkbox
                id={cid} checked={checked}
                onCheckedChange={(c) => onChange(c === true ? [...selected, name] : selected.filter((s) => s !== name))}
              />
              <label htmlFor={cid} className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 truncate text-sm">
                <span className="size-2 shrink-0 rounded-full" style={{ background: KIND_COLORS[kind] }} aria-hidden />
                <span className="truncate">{name}</span>
              </label>
            </li>
          );
        })}
        {shown.length === 0 ? <li className="text-xs text-muted italic">No match.</li> : null}
      </ul>
    </div>
  );
}

export function Sidebar({
  form, onForm, onSearch, searching, filters, onFilters, options, yearBounds, className,
}: {
  form: SearchForm; onForm: (f: SearchForm) => void; onSearch: () => void; searching: boolean;
  filters: CandidateFilters; onFilters: (f: CandidateFilters) => void; options: FilterOptions;
  yearBounds: [number, number]; className?: string;
}) {
  const yearsActive = form.years[0] !== yearBounds[0] || form.years[1] !== yearBounds[1];
  const total = activeFilterCount(filters) + (yearsActive ? 1 : 0);
  return (
    <aside aria-label="Search and filters" className={cn("flex min-h-0 flex-col border-r border-border bg-card", className)}>
      <form
        className="space-y-3 border-b border-border p-4"
        role="search"
        onSubmit={(e) => { e.preventDefault(); onSearch(); }}
      >
        <label htmlFor="q" className="text-xs font-semibold tracking-wide text-muted uppercase">Search the corpus</label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted" />
          <input
            id="q" value={form.query} onChange={(e) => onForm({ ...form, query: e.target.value })}
            placeholder="Describe a research idea…"
            className="h-9 w-full rounded-lg border border-border bg-background pr-8 pl-9 text-sm outline-none focus-visible:border-primary"
          />
          {form.query ? (
            <button type="button" aria-label="Clear search text" onClick={() => onForm({ ...form, query: "" })} className="absolute top-2 right-2 cursor-pointer text-muted hover:text-foreground">
              <X className="size-4" />
            </button>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="Search mode" value={form.mode} onChange={(e) => onForm({ ...form, mode: e.target.value as SearchMode })}
            className="h-9 min-w-0 flex-1 cursor-pointer truncate rounded-lg border border-border bg-background px-2 text-sm outline-none focus-visible:border-primary"
          >
            {(Object.keys(MODE_LABELS) as SearchMode[]).map((m) => <option key={m} value={m}>{MODE_LABELS[m]}</option>)}
          </select>
          <Button type="submit" className="shrink-0" disabled={searching || !form.query.trim()}>{searching ? "Searching…" : "Search"}</Button>
        </div>
      </form>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4">
        <div className="flex items-center justify-between py-3">
          <span className="text-xs font-semibold tracking-wide uppercase">Filters{total ? <span className="ml-1.5 font-mono text-primary">({total})</span> : null}</span>
          {total ? (
            <button
              className="cursor-pointer text-xs text-primary underline"
              onClick={() => { onFilters(EMPTY_FILTERS); onForm({ ...form, years: yearBounds }); }}
            >Reset</button>
          ) : null}
        </div>

        <Section title="Publication year" count={yearsActive ? 1 : 0} hint="Applies to paper search only; candidate opportunities are scored over one cutoff year.">
          <div className="space-y-2">
            <Slider
              min={yearBounds[0]} max={yearBounds[1]} step={1} minStepsBetweenThumbs={0} value={form.years}
              onValueChange={(v) => onForm({ ...form, years: [v[0] ?? yearBounds[0], v[1] ?? yearBounds[1]] })}
              aria-label="Publication year range"
            />
            <div className="flex justify-between font-mono text-xs text-muted"><span>{form.years[0]}</span><span>{form.years[1]}</span></div>
          </div>
        </Section>

        <Section title="Methods" count={filters.methods.length} hint="Filters candidates and paper search.">
          <CheckList kind="method" options={options.methods} selected={filters.methods} onChange={(methods) => onFilters({ ...filters, methods })} />
        </Section>
        <Section title="Tasks" count={filters.tasks.length} defaultOpen={false}>
          <CheckList kind="task" options={options.tasks} selected={filters.tasks} onChange={(tasks) => onFilters({ ...filters, tasks })} />
        </Section>
        <Section title="Datasets" count={filters.datasets.length} defaultOpen={false}>
          <CheckList kind="dataset" options={options.datasets} selected={filters.datasets} onChange={(datasets) => onFilters({ ...filters, datasets })} />
        </Section>
        <Section title="Settings" count={filters.settings.length} defaultOpen={false} hint={options.settings.length ? undefined : "Settings are listed when a stored candidate combines one. None does yet."}>
          <CheckList kind="setting" options={options.settings} selected={filters.settings} onChange={(settings) => onFilters({ ...filters, settings })} />
        </Section>

        <Section title="Confidence" count={filters.minConfidence > 0 ? 1 : 0}>
          <div className="space-y-2">
            <Slider min={0} max={1} step={0.05} value={[filters.minConfidence]} onValueChange={([v]) => onFilters({ ...filters, minConfidence: v ?? 0 })} aria-label="Minimum confidence" />
            <div className="flex justify-between text-xs text-muted">
              <Tip content="confidence = min(1, expected / 5). A low observed count means little when few papers were expected."><span className="cursor-help underline decoration-dotted">minimum confidence</span></Tip>
              <span className="font-mono text-foreground">{filters.minConfidence.toFixed(2)}</span>
            </div>
          </div>
        </Section>

        <Section title="Search options" defaultOpen={false}>
          <div className="flex items-center justify-between gap-3 text-sm">
            <label htmlFor="collapse-titles" className="cursor-pointer">Hide duplicate records of one title</label>
            <Switch id="collapse-titles" checked={form.collapse} onCheckedChange={(c) => onForm({ ...form, collapse: c })} />
          </div>
          <p className="mt-2 text-[11px] leading-snug text-muted">The pilot corpus contains duplicate OpenAlex records for some papers; this shows one per title.</p>
        </Section>
      </div>
    </aside>
  );
}
