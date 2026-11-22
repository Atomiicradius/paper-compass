import { useMemo } from "react";
import { api } from "@/api/client";
import type { EvidencePaper, EvidenceRole, Opportunity, TrendItem } from "@/api/types";
import { useAsync } from "@/lib/hooks";
import { citationStatus } from "@/lib/text";

export interface StoryEvidenceItem {
  paper_id: string;
  title: string;
  year: number | null;
}

/**
 * Every figure the story shows. Each one is `null` (or an empty list) when the API call that provides it failed or
 * has no answer, and the story then shows nothing for it: no figure is ever made up, defaulted or typed in here.
 */
export interface StoryData {
  /** corpus size (GET /landscape) */
  papers: number | null;
  /** papers per publication year (GET /landscape) */
  papersPerYear: Record<string, number> | null;
  /** number of clusters (GET /clusters, else GET /landscape) */
  clusterCount: number | null;
  /** the size of each cluster (GET /clusters), used to size the decorative groups */
  clusterSizes: number[];
  /** papers that belong to no cluster (GET /clusters) */
  papersInNoCluster: number | null;
  /** the most used extracted methods and tasks, with the number of papers that use each (GET /trends) */
  topMethods: TrendItem[];
  topTasks: TrendItem[];
  /** the opportunity ranked first by stored score (GET /opportunities), the same order as the Candidates screen */
  top: Opportunity | null;
  /** the number of papers both elements of the top opportunity were extracted in (POST /opportunities/{id}/explain) */
  universeN: number | null;
  /** two or three papers from the explanation's evidence, closest existing work first (POST /opportunities/{id}/explain) */
  evidence: StoryEvidenceItem[];
  /** the number of verified citations, only when the explanation's own citation check passed in full */
  verifiedCitations: number | null;
}

const TOP_ELEMENTS = 4;
const EVIDENCE_ORDER: EvidenceRole[] = ["nearest_existing", "supports_A", "supports_B", "bridge"];

function pickEvidence(roles: Record<EvidenceRole, EvidencePaper[]>): StoryEvidenceItem[] {
  const seen = new Set<string>();
  const out: StoryEvidenceItem[] = [];
  for (const role of EVIDENCE_ORDER) {
    for (const p of roles[role] ?? []) {
      if (seen.has(p.paper_id)) continue;
      seen.add(p.paper_id);
      out.push({ paper_id: p.paper_id, title: p.title, year: p.year ?? null });
      if (out.length === 3) return out;
    }
  }
  return out;
}

/** The one data hook of the story page. It uses the existing API client functions and nothing else. */
export function useStoryData(): StoryData {
  const landscape = useAsync((s) => api.landscape(s), []);
  const clusters = useAsync((s) => api.clusters(s), []);
  const methods = useAsync((s) => api.trends("method", s), []);
  const tasks = useAsync((s) => api.trends("task", s), []);
  const opps = useAsync((s) => api.opportunities(s), []);

  // rank 1 = highest stored score, ties by id: the order of the Candidates screen
  const top = useMemo(() => {
    const items = opps.data?.items ?? [];
    return items.length ? [...items].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || a.opportunity_id - b.opportunity_id)[0] ?? null : null;
  }, [opps.data]);
  const topId = top?.opportunity_id ?? null;
  const explain = useAsync((s) => api.explain(topId as number, s), [topId], topId !== null);

  return useMemo<StoryData>(() => {
    const topN = (xs: TrendItem[] | null | undefined) => [...(xs ?? [])].sort((a, b) => b.total - a.total || a.name.localeCompare(b.name)).slice(0, TOP_ELEMENTS);
    const ex = explain.data && explain.data.opportunity_id === topId ? explain.data : null;
    let verifiedCitations: number | null = null;
    if (ex) {
      const check = ex.citation_check;
      const ids = new Set(Object.values(ex.evidence.roles).flat().map((p) => p.paper_id));
      const verified = check.cited.filter((id) => citationStatus(id, check, ids) === "verified").length;
      // the same condition under which the drawer says "N citations verified"
      if (check.ok && check.cited.length > 0 && verified === check.cited.length) verifiedCitations = verified;
    }
    return {
      papers: landscape.data?.corpus.papers ?? null,
      papersPerYear: landscape.data?.papers_per_year ?? null,
      clusterCount: clusters.data ? clusters.data.clusters.length : (landscape.data?.n_clusters ?? null),
      clusterSizes: clusters.data ? clusters.data.clusters.map((c) => c.size) : [],
      papersInNoCluster: clusters.data?.n_noise ?? null,
      topMethods: topN(methods.data),
      topTasks: topN(tasks.data),
      top,
      universeN: ex ? ex.evidence.corpus.universe_size : null,
      evidence: ex ? pickEvidence(ex.evidence.roles) : [],
      verifiedCitations,
    };
  }, [landscape.data, clusters.data, methods.data, tasks.data, top, topId, explain.data]);
}
