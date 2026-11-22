import type { Opportunity } from "@/api/types";
import { formatNumber } from "@/lib/utils";
import type { SignalKey } from "@/lib/opportunities";
import { Mono } from "@/components/ui/primitives";

/** The colour of each signal's bar: all three use the accent gradient (the label tells them apart). */
const ACCENT_BAR = "linear-gradient(90deg, var(--ring-a), var(--ring-b))";
export const SIGNAL_COLORS: Record<SignalKey, string> = {
  sparsity: ACCENT_BAR,
  semantic_compatibility: ACCENT_BAR,
  temporal_activity: ACCENT_BAR,
};

/** The tooltip that explains how a signal is computed (unchanged from the candidate card). */
export function signalTip(key: SignalKey, o: Opportunity) {
  const exp = formatNumber(o.expected_count);
  switch (key) {
    case "sparsity":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Sparsity: how much rarer than expected</p>
          <p>
            <Mono>1 − (observed + 1) / (expected + 1)</Mono>, clipped to 0..1. Here observed = <Mono>{o.observed_count}</Mono>, expected = <Mono>{exp}</Mono>.
          </p>
          <p>
            Expected = n<sub>A</sub> × n<sub>B</sub> / N, with every count taken over the <b>same universe</b> of N papers in which both kinds of
            element were extracted, and only papers up to {o.corpus.cutoff_year}. Counts are distinct papers, never experiment rows.
          </p>
        </div>
      );
    case "semantic_compatibility":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Semantic compatibility</p>
          <p>Percentile rank, across the candidates, of the cosine similarity between the SPECTER2 embedding centroids of the papers using each element. Higher = the two elements live in related areas.</p>
        </div>
      );
    case "temporal_activity":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Temporal activity</p>
          <p>Percentile rank of how active both elements are recently: their share of papers in the last 3 years and their 5-year trend slope.</p>
        </div>
      );
  }
}
