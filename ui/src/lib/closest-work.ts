import { useEffect, useState } from "react";
import { api } from "@/api/client";

/** One paper of the "Closest existing work" block. */
export interface ClosestPaper {
  paper_id: string;
  title: string;
}

export type ClosestWork =
  | { status: "loading" }
  | { status: "loaded"; papers: ClosestPaper[] }
  | { status: "failed" };

/** At most this many titles are shown. */
export const MAX_CLOSEST = 3;

// the papers of an opportunity that were already loaded, by opportunity id (a failure is not cached, so a later selection tries again)
const cache = new Map<number, ClosestPaper[]>();

/** Forget everything that was cached (for tests). */
export function clearClosestWorkCache(): void {
  cache.clear();
}

/** The "nearest_existing" papers of an explanation, as {id, title}, at most MAX_CLOSEST. Nothing if there are none. */
export function closestPapers(roles: { nearest_existing?: { paper_id: string; title: string }[] } | undefined): ClosestPaper[] {
  return (roles?.nearest_existing ?? []).slice(0, MAX_CLOSEST).map((p) => ({ paper_id: p.paper_id, title: p.title }));
}

/**
 * The closest existing work of the selected opportunity, from the existing explain call. It is loaded when an opportunity is
 * selected (not for the whole list), cached by id, and aborted if the selection changes before it arrives.
 */
export function useClosestWork(opportunityId: number): ClosestWork {
  const [state, setState] = useState<{ id: number; value: ClosestWork } | null>(null);
  useEffect(() => {
    if (cache.has(opportunityId)) return;
    const ctrl = new AbortController();
    Promise.resolve().then(() => api.explain(opportunityId, ctrl.signal)).then(
      (res) => {
        if (ctrl.signal.aborted) return;
        const papers = closestPapers(res?.evidence?.roles);
        cache.set(opportunityId, papers);
        setState({ id: opportunityId, value: { status: "loaded", papers } });
      },
      (e: unknown) => {
        if (ctrl.signal.aborted || (e as Error)?.name === "AbortError") return;
        setState({ id: opportunityId, value: { status: "failed" } });
      },
    );
    return () => ctrl.abort();
  }, [opportunityId]);

  const cached = cache.get(opportunityId);
  if (cached) return { status: "loaded", papers: cached };
  if (state && state.id === opportunityId) return state.value;
  return { status: "loading" };
}
