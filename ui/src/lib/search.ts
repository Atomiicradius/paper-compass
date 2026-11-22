import type { SearchRequest } from "@/api/types";
import type { CandidateFilters } from "@/lib/opportunities";

export type SearchMode = "auto" | "vector" | "keyword" | "hybrid";

export interface SearchFormState {
  query: string;
  mode: SearchMode;
  collapse: boolean;
  years: [number, number];
}

export interface BuiltSearch {
  request: SearchRequest;
  /** things the reader must be told about this search (shown above the results) */
  notes: string[];
}

/**
 * Turn the sidebar state into an API request.
 * - the year range is only sent when it was moved off the corpus bounds
 * - hybrid search can apply the year filters only. The method, task and dataset filters are NOT sent (the API would
 *   refuse them with a 422) and the reader is told so, instead of the filters silently doing nothing.
 */
export function buildSearchRequest(form: SearchFormState, filters: CandidateFilters, yearBounds: [number, number], topK = 20): BuiltSearch {
  const request: SearchRequest = { query: form.query.trim(), top_k: topK, mode: form.mode, collapse_same_title: form.collapse };
  const notes: string[] = [];
  if (form.years[0] !== yearBounds[0]) request.year_min = form.years[0];
  if (form.years[1] !== yearBounds[1]) request.year_max = form.years[1];
  const elementFilters = filters.methods.length + filters.tasks.length + filters.datasets.length;
  if (form.mode === "hybrid") {
    if (elementFilters > 0) notes.push("Hybrid search applies only the year range, so your method, task and dataset filters were not used. Use vector or keyword mode to apply them.");
  } else {
    if (filters.methods.length) request.methods = filters.methods;
    if (filters.tasks.length) request.tasks = filters.tasks;
    if (filters.datasets.length) request.datasets = filters.datasets;
  }
  return { request, notes };
}

export const MODE_LABELS: Record<SearchMode, string> = {
  auto: "Auto (vector if available)",
  vector: "Vector (SPECTER2)",
  keyword: "Keyword (every word must match)",
  hybrid: "Hybrid (vector + keyword)",
};
