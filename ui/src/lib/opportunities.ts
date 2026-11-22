import type { ElementKind, Elements, Opportunity } from "@/api/types";

export const SIGNAL_KEYS = ["sparsity", "semantic_compatibility", "temporal_activity"] as const;
export type SignalKey = (typeof SIGNAL_KEYS)[number];

export const SIGNAL_LABELS: Record<SignalKey, string> = {
  sparsity: "Sparsity",
  semantic_compatibility: "Semantic",
  temporal_activity: "Temporal",
};

/** The documented v1-three-signal weights (scoring/score.py). The stored score always uses the stored version. */
export const V1_WEIGHTS: Record<SignalKey, number> = { sparsity: 0.4, semantic_compatibility: 0.35, temporal_activity: 0.25 };

/** "Method × Task" (or "Method × Setting", "Method × Dataset"), in the order method, dataset, task, setting. */
export function opportunityTitle(el: Elements): string {
  return [el.method, el.dataset, el.task, el.setting].filter((x): x is string => !!x).join(" × ");
}

/** The two element kinds a stored opportunity combines, in A, B order (method first). */
export function pairKinds(el: Elements): ElementKind[] {
  return (["method", "dataset", "task", "setting"] as const).filter((k) => !!el[k]);
}

export interface CandidateFilters {
  methods: string[];
  tasks: string[];
  datasets: string[];
  settings: string[];
  minConfidence: number;
}

export const EMPTY_FILTERS: CandidateFilters = { methods: [], tasks: [], datasets: [], settings: [], minConfidence: 0 };

export function activeFilterCount(f: CandidateFilters): number {
  return f.methods.length + f.tasks.length + f.datasets.length + f.settings.length + (f.minConfidence > 0 ? 1 : 0);
}

/**
 * An opportunity passes when, for every filter group that has a selection, its element of that kind is one of
 * the selected names (a group with no selection does not filter), and its confidence is at least minConfidence.
 */
export function filterOpportunities(items: readonly Opportunity[], f: CandidateFilters): Opportunity[] {
  const groups: [ElementKind, string[]][] = [
    ["method", f.methods], ["task", f.tasks], ["dataset", f.datasets], ["setting", f.settings],
  ];
  return items.filter((o) => {
    if (f.minConfidence > 0 && (o.confidence ?? 0) < f.minConfidence) return false;
    return groups.every(([kind, names]) => names.length === 0 || (o.elements[kind] != null && names.includes(o.elements[kind] as string)));
  });
}

export function paginate<T>(items: readonly T[], page: number, size: number): { rows: T[]; pages: number; page: number } {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const p = Math.min(Math.max(1, page), pages);
  return { rows: items.slice((p - 1) * size, p * size), pages, page: p };
}

export function normalizeWeights(w: Record<string, number>): Record<string, number> {
  if (Object.values(w).some((x) => x < 0)) throw new Error("weights must be non-negative");
  const total = Object.values(w).reduce((a, b) => a + b, 0);
  if (total <= 0) throw new Error("at least one weight must be positive");
  return Object.fromEntries(Object.entries(w).map(([k, v]) => [k, v / total]));
}

export type Reranked = Opportunity & { customScore: number; customRank: number };

/**
 * View-only what-if ranking: 100 * sum(w_i * s_i) over the normalized signals, the same formula as
 * scoring/score.py. Ties break on opportunity_id. The stored score and weights_version are never changed.
 */
export function rerank(items: readonly Opportunity[], weights: Record<string, number>): Reranked[] {
  const w = normalizeWeights(weights);
  const out = items.map((o) => {
    let total = 0;
    for (const [name, wi] of Object.entries(w)) {
      if (wi === 0) continue;
      const s = (o.signals as unknown as Record<string, number | null>)[name];
      if (s == null) throw new Error("signal " + name + " is not available for opportunity " + o.opportunity_id);
      total += wi * s;
    }
    return { ...o, customScore: 100 * total, customRank: 0 };
  });
  out.sort((a, b) => b.customScore - a.customScore || a.opportunity_id - b.opportunity_id);
  out.forEach((o, i) => { o.customRank = i + 1; });
  return out;
}

/** The API prefixes its disclaimers with "MOCK DATA" when it serves mock data (PC_API_MOCK=1). */
export function isMockData(disclaimer: string | null | undefined): boolean {
  return !!disclaimer && /\bMOCK DATA\b/.test(disclaimer);
}
