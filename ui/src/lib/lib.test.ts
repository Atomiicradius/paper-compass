import { describe, expect, it } from "vitest";
import type { Opportunity } from "@/api/types";
import { formatDetail } from "@/api/client";
import { scoreStrength } from "./colors";
import { normalizePaperId } from "./ids";
import {
  activeFilterCount, EMPTY_FILTERS, filterOpportunities, normalizeWeights, opportunityTitle, paginate, rerank, V1_WEIGHTS,
} from "./opportunities";
import { citationStatus, entityPattern, highlightSegments, parseSummary, tokenizeCitations } from "./text";

function opp(id: number, method: string, task: string, sp: number, sem: number, tmp: number, conf = 1, score = 0): Opportunity {
  return {
    opportunity_id: id,
    elements: { method, task, dataset: null, setting: null },
    corpus: { papers: 1991, cutoff_year: 2026 },
    observed_count: 1,
    expected_count: 5,
    signals: { sparsity: sp, semantic_compatibility: sem, temporal_activity: tmp, graph_bridge_strength: null, method_compatibility: null },
    confidence: conf,
    score,
    weights_version: "v1-three-signal",
    evidence: { supports_A: [], supports_B: [], bridge: [], nearest_existing: [] },
  };
}

describe("normalizePaperId", () => {
  it.each([
    ["W3028876793", "W3028876793"],
    ["Paper:W3028876793", "W3028876793"],
    ["  Paper:W3028876793  ", "W3028876793"],
    ["paper:W3028876793", "W3028876793"],
    ["https://openalex.org/W3028876793", "W3028876793"],
    ["  W3028876793\n", "W3028876793"],
    ["", ""],
    ["   ", ""],
  ])("%j -> %j", (raw, expected) => expect(normalizePaperId(raw)).toBe(expected));

  it("leaves other prefixes alone and handles null", () => {
    expect(normalizePaperId("Method:3")).toBe("Method:3");
    expect(normalizePaperId(null)).toBe("");
    expect(normalizePaperId(undefined)).toBe("");
  });
});

describe("opportunityTitle", () => {
  it("joins method, dataset, task, setting that are present", () => {
    expect(opportunityTitle({ method: "A", task: "B", dataset: null, setting: null })).toBe("A × B");
    expect(opportunityTitle({ method: "A", task: null, dataset: "D", setting: "S" })).toBe("A × D × S");
  });
});

describe("scoreStrength", () => {
  it("maps score to strength at the documented thresholds", () => {
    expect(scoreStrength(70).strength).toBe("strong");
    expect(scoreStrength(69.99).strength).toBe("moderate");
    expect(scoreStrength(50).strength).toBe("moderate");
    expect(scoreStrength(49.9).strength).toBe("weak");
    expect(scoreStrength(null).strength).toBe("weak");
  });
});

describe("filterOpportunities", () => {
  const items = [
    opp(1, "Back-translation", "Machine Translation", 0.5, 0.5, 0.5, 1.0),
    opp(2, "Transformer", "Cross-Lingual Transfer", 0.5, 0.5, 0.5, 0.32),
    opp(3, "Back-translation", "Question Answering", 0.5, 0.5, 0.5, 0.33),
  ];
  it("no selection keeps everything", () => expect(filterOpportunities(items, EMPTY_FILTERS)).toHaveLength(3));
  it("filters within a group by OR and across groups by AND", () => {
    expect(filterOpportunities(items, { ...EMPTY_FILTERS, methods: ["Back-translation"] }).map((o) => o.opportunity_id)).toEqual([1, 3]);
    expect(filterOpportunities(items, { ...EMPTY_FILTERS, methods: ["Back-translation", "Transformer"] })).toHaveLength(3);
    expect(filterOpportunities(items, { ...EMPTY_FILTERS, methods: ["Back-translation"], tasks: ["Question Answering"] }).map((o) => o.opportunity_id)).toEqual([3]);
  });
  it("min confidence is inclusive", () => {
    expect(filterOpportunities(items, { ...EMPTY_FILTERS, minConfidence: 0.33 }).map((o) => o.opportunity_id)).toEqual([1, 3]);
  });
  it("a setting filter excludes opportunities without a setting", () => {
    expect(filterOpportunities(items, { ...EMPTY_FILTERS, settings: ["Low-resource"] })).toHaveLength(0);
  });
  it("counts active filters", () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
    expect(activeFilterCount({ ...EMPTY_FILTERS, methods: ["a", "b"], minConfidence: 0.5 })).toBe(3);
  });
});

describe("paginate", () => {
  it("slices, clamps the page and reports the page count", () => {
    const xs = Array.from({ length: 13 }, (_, i) => i);
    expect(paginate(xs, 1, 6)).toEqual({ rows: [0, 1, 2, 3, 4, 5], pages: 3, page: 1 });
    expect(paginate(xs, 3, 6)).toEqual({ rows: [12], pages: 3, page: 3 });
    expect(paginate(xs, 99, 6).page).toBe(3);
    expect(paginate(xs, 0, 6).page).toBe(1);
    expect(paginate([], 1, 6)).toEqual({ rows: [], pages: 1, page: 1 });
  });
});

describe("rerank", () => {
  it("reproduces the stored v1 score of opportunity 14 on pc_pilot", () => {
    // 100 * (0.40*0.84447473 + 0.35*0.75 + 0.25*0.5480769) = 73.73091
    const o = opp(14, "Masked Language Modeling", "Machine Translation", 0.84447473, 0.75, 0.5480769, 1, 73.73091);
    expect(rerank([o], V1_WEIGHTS)[0]?.customScore).toBeCloseTo(73.73091, 4);
  });
  it("orders by custom score, normalizes weights, does not mutate input, and breaks ties on id", () => {
    const a = opp(1, "x", "y", 1, 0, 0, 1, 50), b = opp(2, "x", "z", 0, 1, 0, 1, 60);
    const r = rerank([a, b], { sparsity: 3, semantic_compatibility: 1 });
    expect(r.map((o) => o.opportunity_id)).toEqual([1, 2]);
    expect(r[0]?.customScore).toBeCloseTo(75);
    expect(r[1]?.customScore).toBeCloseTo(25);
    expect(r.map((o) => o.customRank)).toEqual([1, 2]);
    expect("customScore" in a).toBe(false);
    const ties = rerank([opp(5, "a", "b", 0.5, 0.5, 0.5), opp(3, "a", "c", 0.5, 0.5, 0.5)], { sparsity: 1 });
    expect(ties.map((o) => o.opportunity_id)).toEqual([3, 5]);
  });
  it("rejects bad weights and unavailable signals", () => {
    expect(() => normalizeWeights({ a: 0, b: 0 })).toThrow();
    expect(() => normalizeWeights({ a: -1, b: 2 })).toThrow();
    expect(() => rerank([opp(1, "x", "y", 0.5, 0.5, 0.5)], { graph_bridge_strength: 1 })).toThrow(/not available/);
  });
});

describe("highlightSegments", () => {
  it("highlights an exact name case-insensitively", () => {
    const segs = highlightSegments("We use back-translation here.", [{ name: "Back-translation", kind: "method" }]);
    expect(segs.filter((s) => s.kind).map((s) => s.text)).toEqual(["back-translation"]);
  });
  it("matches inflected forms of a multi-word name", () => {
    const segs = highlightSegments("Pretrained masked language models (MLMs) require finetuning.", [
      { name: "Masked Language Modeling", kind: "method" },
    ]);
    expect(segs.find((s) => s.kind)?.text).toBe("masked language models");
  });
  it("highlights both entities with their own kinds and reassembles to the original text", () => {
    const text = "Back-translation improves machine translation quality.";
    const segs = highlightSegments(text, [
      { name: "Back-translation", kind: "method" }, { name: "Machine Translation", kind: "task" },
    ]);
    expect(segs.map((s) => s.text).join("")).toBe(text);
    expect(segs.filter((s) => s.kind).map((s) => [s.text, s.kind])).toEqual([["Back-translation", "method"], ["machine translation", "task"]]);
  });
  it("does not match inside longer words, and returns the text when nothing matches", () => {
    expect(highlightSegments("transformations of data", [{ name: "Transformer", kind: "method" }])).toEqual([{ text: "transformations of data" }]);
    expect(highlightSegments("", [{ name: "x", kind: "task" }])).toEqual([{ text: "" }]);
  });
  it("escapes regex characters in names", () => {
    expect(entityPattern("C++ (core)")).not.toBeNull();
    expect(() => highlightSegments("a b", [{ name: "(((", kind: "task" }])).not.toThrow();
  });
});

describe("summary parsing and citations", () => {
  it("tokenizes citation markers", () => {
    expect(tokenizeCitations("see [paper:W1] and [paper:W2].")).toEqual([
      { type: "text", text: "see " }, { type: "citation", paperId: "W1" },
      { type: "text", text: " and " }, { type: "citation", paperId: "W2" }, { type: "text", text: "." },
    ]);
  });
  it("parses headings, bullets and paragraphs", () => {
    const blocks = parseSummary("## What the corpus shows\n- one [paper:W1]\n\nplain line");
    expect(blocks.map((b) => b.type)).toEqual(["heading", "bullet", "paragraph"]);
  });
  it("verifies a citation only when cited, not unknown, and shown as evidence", () => {
    const check = { cited: ["W1", "W2"], unknown: ["W9"] };
    const ev = new Set(["W1", "W9"]);
    expect(citationStatus("W1", check, ev)).toBe("verified");
    expect(citationStatus("W2", check, ev)).toBe("unknown");   // cited but not among the shown evidence
    expect(citationStatus("W9", check, ev)).toBe("unknown");   // flagged unknown by the API
    expect(citationStatus("W5", check, ev)).toBe("unknown");   // never cited
  });
});

describe("formatDetail", () => {
  it("passes strings through and joins FastAPI validation errors", () => {
    expect(formatDetail("paper not found")).toBe("paper not found");
    expect(formatDetail([{ loc: ["body", "query"], msg: "must not be blank" }, { loc: ["query", "limit"], msg: "too big" }])).toBe(
      "query: must not be blank; limit: too big",
    );
    expect(formatDetail(null)).toBe("");
  });
});

describe("isMockData", () => {
  it("detects the API's mock marker in a disclaimer, and nothing else", async () => {
    const { isMockData } = await import("./opportunities");
    expect(isMockData("MOCK DATA - not real results. Candidate research opportunities are combinations ...")).toBe(true);
    expect(isMockData("Candidate research opportunities are combinations weakly represented in the analyzed corpus.")).toBe(false);
    expect(isMockData(undefined)).toBe(false);
    expect(isMockData(null)).toBe(false);
  });
});

describe("plainText (abstracts that carry markup)", () => {
  it("removes tags, decodes the common entities and tidies spaces, leaving ordinary text alone", async () => {
    const { plainText } = await import("./text");
    expect(plainText("We study <i>Back-translation</i> for <jats:p>low-resource</jats:p> MT.")).toBe("We study Back-translation for low-resource MT.");
    expect(plainText("Tom &amp; Jerry &lt;3 &quot;quotes&quot; &#39;x&#39; a&nbsp;b")).toBe("Tom & Jerry <3 \"quotes\" 'x' a b");
    expect(plainText("line one\n\nline   two")).toBe("line one line two");
    expect(plainText("x < y and y > z")).toBe("x < y and y > z");         // not a tag: no letter follows the <
    expect(plainText("")).toBe("");
  });
});

describe("graphNote", () => {
  it("says how much of the neighbourhood is shown, and what to do about it", async () => {
    const { graphNote } = await import("./graph");
    expect(graphNote({ truncated: false, neighbors_total: 16 }, 17)).toBeNull();
    expect(graphNote(undefined, 17)).toBeNull();
    expect(graphNote({ truncated: true, neighbors_total: 343 }, 60)).toBe(
      "Showing 59 of 343 neighbours: the paper's own authors, venue and extracted elements first, then its most recent citations. Raise “Max nodes” to see more.",
    );
    expect(graphNote({ truncated: true, neighbors_total: 2500 }, 1000)).toMatch(/more than the 1,000 nodes the API can return/);
    expect(graphNote({ truncated: true, neighbors_total: 2500 }, 1000)).not.toMatch(/Raise/);     // nothing left to raise
    expect(graphNote({ truncated: true, neighbors_total: 2500 }, 1000)).toContain("2,500");
  });
});
