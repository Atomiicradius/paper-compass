import type { Explanation, Opportunity } from "@/api/types";

/** Shaped like real API responses (values from opportunity 14 on pc_pilot, ids shortened where noted). */
export function makeOpportunity(id: number, overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    opportunity_id: id,
    elements: { method: "Masked Language Modeling", task: "Machine Translation", dataset: null, setting: null },
    corpus: { papers: 1991, cutoff_year: 2026 },
    observed_count: 1,
    expected_count: 11.859649,
    signals: { sparsity: 0.84447473, semantic_compatibility: 0.75, temporal_activity: 0.5480769, graph_bridge_strength: null, method_compatibility: null },
    confidence: 1,
    score: 73.73091,
    weights_version: "v1-three-signal",
    evidence: { supports_A: ["W1"], supports_B: ["W2"], bridge: ["W3"], nearest_existing: ["W4"] },
    ...overrides,
  };
}

export const METHODS = ["Back-translation", "Transformer", "Fine-tuning", "Data Augmentation", "Knowledge Distillation", "Byte-Pair Encoding", "Beam Search"];

/** 13 opportunities with distinct scores, like the real pilot run. */
export function makeOpportunities(n = 13): Opportunity[] {
  return Array.from({ length: n }, (_, i) =>
    makeOpportunity(14 + i, {
      elements: { method: METHODS[i % METHODS.length] ?? "Method", task: i % 2 ? "Language Modeling" : "Machine Translation", dataset: null, setting: null },
      score: 80 - i * 3,
      confidence: i % 3 === 0 ? 1 : 0.3,
    }),
  );
}

export function makeExplanation(): Explanation {
  return {
    opportunity_id: 14,
    evidence: {
      pair: { a: { kind: "method", id: 22, name: "Masked Language Modeling" }, b: { kind: "task", id: 1, name: "Machine Translation" } },
      corpus: { cutoff_year: 2026, universe_size: 399, n_a: 14, n_b: 338, observed: 1, expected: 11.86 },
      yearly: [2023, 2024, 2025, 2026].map((year, i) => ({ year, a: i, b: 40 + i, both: 0 })),
      roles: {
        supports_A: [{ paper_id: "WA1", title: "A paper using MLM", year: 2024, venue: "ACL", source_sentence: "We pretrain with masked language modeling.", extractor: "rules-v1" }],
        supports_B: [{ paper_id: "WB1", title: "A paper on translation", year: 2023, venue: null, source_sentence: "We study machine translation for low-resource languages.", extractor: "rules-v1" }],
        bridge: [],
        nearest_existing: [
          { paper_id: "WN1", title: "Exact neighbour", year: 2023, venue: "CL", source_sentence: "Masked language models help machine translation.", extractor: "rules-v1", tier: "exact", similarity: null, uses: "both" },
          { paper_id: "WN2", title: "Close neighbour", year: 2020, venue: "arXiv", source_sentence: null, extractor: "rules-v1", tier: "close", similarity: 0.964, uses: "B" },
        ],
      },
      limitations: ["Counts depend on the analyzed corpus and on extraction coverage."],
    },
    // WN1 is cited and in the evidence; WZZ is cited but is NOT in the evidence set; WN2 is evidence but never cited
    summary:
      "## What the corpus shows\n- The two are used together in 1 paper; about 11.9 expected.\n\n## Closest existing work\n- [paper:WN1] Exact neighbour (2023).\n- [paper:WZZ] An unverifiable claim.",
    summary_source: "template",
    summary_fallback_reason: null,
    citation_check: { ok: true, cited: ["WN1", "WZZ"], unknown: [], uncited_markers_count: 0, has_no_citations: false },
    disclaimer: "x",
  };
}
