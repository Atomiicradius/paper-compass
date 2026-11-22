import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { motion } from "motion/react";
import { RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Opportunity } from "@/api/types";
import type { AsyncState } from "@/lib/hooks";
import {
  activeFilterCount, filterOpportunities, rerank, SIGNAL_KEYS, SIGNAL_LABELS, V1_WEIGHTS, type CandidateFilters, type SignalKey,
} from "@/lib/opportunities";
import { Button, ErrorNote, Skeleton, Slider, Tip } from "@/components/ui/primitives";
import { Reveal } from "@/components/Reveal";
import { PageHeader } from "@/components/PageHeader";
import { CandidateRow } from "@/components/CandidateRow";
import { CandidateDetail } from "@/components/CandidateDetail";

export function CandidatesView({
  state, filters, selectedId, onSelect, onOpenEvidence, onClearFilters, filterButton, filterChips,
}: {
  state: AsyncState<{ items: Opportunity[]; total: number }>;
  /** the Filters button (it joins the actions on the right of the header) and the active filter chips (under the title) */
  filterButton?: ReactNode;
  filterChips?: ReactNode;
  filters: CandidateFilters;
  /** the selected opportunity (the ?opp= route parameter); null = the one ranked first */
  selectedId: number | null;
  onSelect: (o: Opportunity) => void;
  /** open the evidence drawer for an opportunity (the "Evidence & explanation" button) */
  onOpenEvidence?: (o: Opportunity) => void;
  onClearFilters: () => void;
}) {
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

  // the selected row: the one in the route if it is in this list, else the one ranked first
  const current = ranked.find((r) => r.o.opportunity_id === selectedId) ?? ranked[0] ?? null;
  const currentId = current?.o.opportunity_id ?? null;
  useEffect(() => {
    if (currentId !== null) document.getElementById(`candidate-row-${currentId}`)?.scrollIntoView({ block: "nearest" });
  }, [currentId]);

  // Up / Down (and Home / End) move the selection while the list has the focus
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (ranked.length === 0) return;
    const at = Math.max(0, ranked.findIndex((r) => r.o.opportunity_id === currentId));
    const next = e.key === "ArrowDown" ? Math.min(ranked.length - 1, at + 1) : e.key === "ArrowUp" ? Math.max(0, at - 1) : e.key === "Home" ? 0 : e.key === "End" ? ranked.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    if (next !== at) onSelect(ranked[next]!.o);
  };
  // a different filter set or weighting is a different list: it fades in again
  const listKey = JSON.stringify(filters) + "|" + (isDefault ? "stored" : JSON.stringify(weights));

  return (
    <section aria-label="Candidate opportunities" className="space-y-4">
      <PageHeader
        title={<>Candidate <span className="accent-word">opportunities</span></>}
        description={
          <>
            Potentially underexplored research-element combinations, ranked for human review.
            {state.data ? <> Showing <b className="text-foreground">{ranked.length}</b> of {state.data.total}.</> : null}
          </>
        }
        actions={
          <>
            {filterButton}
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
          </>
        }
      >
        {filterChips}
      </PageHeader>

      {showWeights ? (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="glass overflow-hidden rounded-2xl">
          <div className="grid gap-4 p-4 sm:grid-cols-3">
            {SIGNAL_KEYS.map((k) => (
              <label key={k} className="block text-xs">
                <span className="mb-2 flex justify-between font-medium text-muted">
                  {SIGNAL_LABELS[k]} <span className="font-mono text-foreground">{weights[k].toFixed(2)}</span>
                </span>
                <Slider min={0} max={1} step={0.05} value={[weights[k]]} onValueChange={([v]) => { setWeights((w) => ({ ...w, [k]: v ?? 0 })); }} aria-label={`${SIGNAL_LABELS[k]} weight`} />
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
          <div className="grid gap-6 lg:grid-cols-[minmax(380px,460px)_minmax(0,1fr)]" data-testid="candidates-skeleton">
            <div className="glass space-y-2 rounded-2xl p-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}</div>
            <div className="glass space-y-4 rounded-3xl p-6"><Skeleton className="h-16" /><Skeleton className="h-36" /><Skeleton className="h-20" /></div>
          </div>
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
        <div className="grid gap-6 lg:grid-cols-[minmax(380px,460px)_minmax(0,1fr)] lg:h-[calc(100dvh-15.5rem)] lg:min-h-[30rem]" data-testid="candidates-grid">
          <Reveal
            key={listKey}
            role="listbox"
            aria-label="Ranked candidates"
            aria-activedescendant={currentId !== null ? `candidate-row-${currentId}` : undefined}
            tabIndex={0}
            data-lenis-prevent
            onKeyDown={onKeyDown}
            className="scroll-thin glass max-h-[26rem] space-y-1 overflow-x-hidden overflow-y-auto rounded-2xl p-2 outline-none lg:h-full lg:max-h-none"
          >
            {ranked.map(({ o, rank, score }) => (
              <CandidateRow key={o.opportunity_id} opportunity={o} rank={rank} score={score} selected={o.opportunity_id === currentId} onSelect={onSelect} />
            ))}
          </Reveal>
          {current ? (
            <div className="lg:sticky lg:top-4 lg:h-full lg:min-h-0">
              <CandidateDetail
                key={current.o.opportunity_id}
                opportunity={current.o}
                rank={current.rank}
                score={current.score}
                scoreLabel={isDefault ? `Stored score (${current.o.weights_version ?? "unknown weights"}).` : "What-if score with your weights."}
                onOpenEvidence={onOpenEvidence ?? onSelect}
              />
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
