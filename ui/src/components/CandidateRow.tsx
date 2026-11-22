import type { Opportunity } from "@/api/types";
import { KIND_TEXT } from "@/lib/colors";
import { pairKinds } from "@/lib/opportunities";
import { cn } from "@/lib/utils";
import { ScoreRing } from "@/components/ScoreRing";

/**
 * One candidate as a compact row of the ranked list: its rank, its elements (each in its method / task / dataset / setting
 * colour) and a small score ring. The row is an option of the list's listbox: selecting it is up to the list (click or arrow keys).
 */
export function CandidateRow({
  opportunity: o, rank, score, selected, onSelect,
}: { opportunity: Opportunity; rank: number; score: number; selected: boolean; onSelect: (o: Opportunity) => void }) {
  const kinds = pairKinds(o.elements);
  return (
    <div
      id={`candidate-row-${o.opportunity_id}`}
      role="option"
      aria-selected={selected}
      data-testid="candidate-row"
      onClick={() => onSelect(o)}
      className={cn(
        "defer-paint group flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
        selected ? "border-primary/60 bg-primary/10 shadow-[0_0_0_1px_color-mix(in_srgb,var(--primary)_35%,transparent)]" : "border-transparent hover:bg-hover",
      )}
    >
      <span className="w-6 shrink-0 text-right font-mono text-xs text-muted">{String(rank).padStart(2, "0")}</span>
      <span className="min-w-0 flex-1 truncate font-display text-lg leading-tight">
        {kinds.map((k, i) => (
          <span key={k}>
            {i > 0 ? <span className="mx-1.5 text-muted">×</span> : null}
            <span style={{ color: KIND_TEXT[k] }}>{o.elements[k]}</span>
          </span>
        ))}
      </span>
      <ScoreRing score={score} size={38} strokeWidth={9} testId="score-ring-mini">
        <span className="font-mono text-[11px] leading-none font-semibold tabular-nums">{Math.round(score)}</span>
      </ScoreRing>
    </div>
  );
}
