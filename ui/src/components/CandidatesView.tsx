import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { ChevronLeft, ChevronRight, RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Opportunity } from "@/api/types";
import type { AsyncState } from "@/lib/hooks";
import {
  activeFilterCount, filterOpportunities, paginate, rerank, SIGNAL_KEYS, SIGNAL_LABELS, V1_WEIGHTS, type CandidateFilters, type SignalKey,
} from "@/lib/opportunities";
import { Button, ErrorNote, Skeleton, Slider, Tip } from "@/components/ui/primitives";
import { Reveal } from "@/components/Reveal";
import { CandidateCard } from "@/components/CandidateCard";

const PAGE_SIZE = 6;

export function CandidatesView({
  state, filters, selectedId, onOpen, onClearFilters,
}: {
  state: AsyncState<{ items: Opportunity[]; total: number }>;
  filters: CandidateFilters;
  selectedId: number | null;
  onOpen: (o: Opportunity) => void;
  onClearFilters: () => void;
}) {
  const [page, setPage] = useState(1);
  const [weights, setWeights] = useState<Record<SignalKey, number>>({ ...V1_WEIGHTS });
  const [showWeights, setShowWeights] = useState(false);
  const isDefault = SIGNAL_KEYS.every((k) => weights[k] === V1_WEIGHTS[k]);

  const filtered = useMemo(() => filterOpportunities(state.data?.items ?? [], filters), [state.data, filters]);
  const ranked = useMemo(() => {
    if (isDefault) {
      // stored ranking: by the stored score, ties by id
      return [...filtered].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || a.opportunity_id - b.opportunity_id).map((o, i) => ({ o, rank: i + 1, score: o.score ?? 0 }));
    }
    try {
      return rerank(filtered, weights).map((r) => ({ o: r, rank: r.customRank, score: r.customScore }));
    } catch {
      // all weights at 0 (or a missing signal): keep the stored ranking instead of crashing
      return [...filtered].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || a.opportunity_id - b.opportunity_id).map((o, i) => ({ o, rank: i + 1, score: o.score ?? 0 }));
    }
  }, [filtered, weights, isDefault]);

  // a different filter set or weighting is a different list: start again from page 1
  const resetKey = JSON.stringify(filters) + "|" + JSON.stringify(weights);
  const [pageResetKey, setPageResetKey] = useState(resetKey);
  if (pageResetKey !== resetKey) {
    setPageResetKey(resetKey);
    setPage(1);
  }

  const { rows, pages, page: cur } = paginate(ranked, page, PAGE_SIZE);
  // a key that changes with the filters/weights/page restarts the staggered fade-in
  const listKey = `${cur}|${JSON.stringify(filters)}|${isDefault ? "stored" : JSON.stringify(weights)}`;

  return (
    <section aria-label="Candidate opportunities" className="space-y-4">
      <Reveal as="header" self trigger="mount" className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="display-heading mb-1">Candidate <span className="accent-word">opportunities</span></h2>
          <p className="text-sm text-muted">
            Potentially underexplored research-element combinations, ranked for human review.
            {state.data ? <> Showing <b className="text-foreground">{ranked.length}</b> of {state.data.total}.</> : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeFilterCount(filters) > 0 ? (
            <Button variant="outline" size="sm" onClick={onClearFilters}>
              <RotateCcw className="size-3.5" /> Clear filters
            </Button>
          ) : null}
          <Tip content="Re-rank with your own weights. View only: the stored score and weights version do not change.">
            <Button variant={isDefault ? "outline" : "default"} size="sm" onClick={() => setShowWeights((s) => !s)} aria-expanded={showWeights}>
              <SlidersHorizontal className="size-3.5" /> What-if weights
            </Button>
          </Tip>
        </div>
      </Reveal>

      {showWeights ? (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="glass overflow-hidden rounded-2xl">
          <div className="grid gap-4 p-4 sm:grid-cols-3">
            {SIGNAL_KEYS.map((k) => (
              <label key={k} className="block text-xs">
                <span className="mb-2 flex justify-between font-medium text-muted">
                  {SIGNAL_LABELS[k]} <span className="font-mono text-foreground">{weights[k].toFixed(2)}</span>
                </span>
                <Slider min={0} max={1} step={0.05} value={[weights[k]]} onValueChange={([v]) => { setWeights((w) => ({ ...w, [k]: v ?? 0 })); setPage(1); }} aria-label={`${SIGNAL_LABELS[k]} weight`} />
              </label>
            ))}
          </div>
          <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted">
            <span>{SIGNAL_KEYS.every((k) => weights[k] === 0) ? "Set at least one weight above 0." : "Weights are normalized to sum to 1. Scores shown are what-if scores."}</span>
            <Button variant="ghost" size="sm" onClick={() => setWeights({ ...V1_WEIGHTS })} disabled={isDefault}>
              Reset to v1
            </Button>
          </div>
        </motion.div>
      ) : null}

      {state.error ? (
        <ErrorNote
          title="Could not load candidate opportunities"
          message={state.error.message.replace(/^\d+: /, "")}
          action={<Button variant="outline" size="sm" onClick={state.reload}>Try again</Button>}
        />
      ) : state.loading && !state.data ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading candidates">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-48" />)}
        </div>
      ) : state.data && state.data.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted">
          No opportunities are stored yet. Run <code className="font-mono">python -m scoring.pipeline</code> (see scoring/README.md).
        </div>
      ) : ranked.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted">
          No candidate matches these filters.{" "}
          <button className="cursor-pointer text-primary underline" onClick={onClearFilters}>Clear filters</button>
        </div>
      ) : (
        <>
          <Reveal key={listKey} className="space-y-4">
            {rows.map(({ o, rank, score }) => (
              <CandidateCard
                key={o.opportunity_id}
                opportunity={o}
                rank={rank}
                score={score}
                scoreLabel={isDefault ? `Stored score (${o.weights_version ?? "unknown weights"}).` : "What-if score with your weights."}
                selected={selectedId === o.opportunity_id}
                onOpen={onOpen}
              />
            ))}
          </Reveal>
          {pages > 1 ? (
            <nav aria-label="Pagination" className="flex items-center justify-center gap-3 pt-2">
              <Button variant="outline" size="sm" disabled={cur <= 1} onClick={() => setPage(cur - 1)} aria-label="Previous page">
                <ChevronLeft className="size-4" /> Prev
              </Button>
              <span className="font-mono text-sm text-muted" aria-live="polite">Page {cur} / {pages}</span>
              <Button variant="outline" size="sm" disabled={cur >= pages} onClick={() => setPage(cur + 1)} aria-label="Next page">
                Next <ChevronRight className="size-4" />
              </Button>
            </nav>
          ) : null}
        </>
      )}
    </section>
  );
}
