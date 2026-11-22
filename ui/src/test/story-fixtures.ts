import type { Clusters, Explanation, Landscape, OpportunityList, TrendItem } from "@/api/types";
import { makeExplanation, makeOpportunity } from "@/test/fixtures";

/** Shaped like the real responses from the pilot database (counts here are test values, not the pilot's). */
export function makeLandscape(overrides: Partial<Landscape> = {}): Landscape {
  return {
    corpus: { papers: 1999, cutoff_year: 2026 },
    papers_per_year: { "2019": 120, "2020": 150, "2021": 180, "2022": 210 },
    n_clusters: 7,
    emerging: [],
    declining: [],
    weakly_connected_cluster_pairs: [],
    bridge_papers: [],
    disclaimer: "Counts are papers in this corpus.",
    ...overrides,
  };
}

export function makeClusters(overrides: Partial<Clusters> = {}): Clusters {
  const sizes = [420, 398, 135, 69, 38, 37, 19];
  return {
    method: "hdbscan",
    min_cluster_size: 15,
    min_samples: 5,
    pca_dims: 20,
    n_papers: 1999,
    n_noise: 883,
    clusters: sizes.map((size, i) => ({ cluster_id: i, size, year_min: 2000, year_max: 2026, top_elements: [], paper_ids: [] })),
    ...overrides,
  };
}

export function makeTrends(kind: "method" | "task"): TrendItem[] {
  const names = kind === "method" ? ["Transformer", "Fine-tuning", "Back-translation", "Beam Search", "Byte-Pair Encoding"] : ["Machine Translation", "Language Modeling", "Question Answering", "Text Classification", "Word Alignment"];
  return names.map((name, i) => ({ element_type: kind, element_id: i + 1, name, yearly: {}, total: 300 - i * 40, recent_share: 0.3, growth: 0, label: "stable" as const }));
}

/** Three candidates; the best-scoring one (id 7) is deliberately not first in the list. */
export function makeOpportunityList(): OpportunityList {
  return {
    total: 3,
    disclaimer: "x",
    items: [
      makeOpportunity(5, { score: 50, observed_count: 4, expected_count: 6 }),
      makeOpportunity(7, { score: 73.7, observed_count: 1, expected_count: 11.86, confidence: 0.32 }),
      makeOpportunity(9, { score: 60, observed_count: 2, expected_count: 5 }),
    ],
  };
}

/** The explanation of opportunity 7, with a citation check that passes in full (every cited paper is in the evidence). */
export function makeStoryExplanation(overrides: Partial<Explanation> = {}): Explanation {
  const base = makeExplanation();
  return {
    ...base,
    opportunity_id: 7,
    citation_check: { ok: true, cited: ["WN1", "WA1"], unknown: [], uncited_markers_count: 0, has_no_citations: false },
    ...overrides,
  };
}
