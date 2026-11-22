import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS } from "./opportunities";
import { buildSearchRequest, type SearchFormState } from "./search";

const form: SearchFormState = { query: "  back-translation  ", mode: "auto", collapse: true, years: [1951, 2026] };
const bounds: [number, number] = [1951, 2026];

describe("buildSearchRequest", () => {
  it("trims the query and sends only what was set", () => {
    const { request, notes } = buildSearchRequest(form, EMPTY_FILTERS, bounds);
    expect(request).toEqual({ query: "back-translation", top_k: 20, mode: "auto", collapse_same_title: true });
    expect(notes).toEqual([]);
  });

  it("sends a year bound only when it was moved off the corpus bounds", () => {
    expect(buildSearchRequest({ ...form, years: [2020, 2026] }, EMPTY_FILTERS, bounds).request).toMatchObject({ year_min: 2020 });
    expect(buildSearchRequest({ ...form, years: [2020, 2026] }, EMPTY_FILTERS, bounds).request).not.toHaveProperty("year_max");
    expect(buildSearchRequest({ ...form, years: [1951, 2022] }, EMPTY_FILTERS, bounds).request).toMatchObject({ year_max: 2022 });
  });

  it("sends element filters in vector, keyword and auto mode", () => {
    const f = { ...EMPTY_FILTERS, methods: ["Back-translation"], tasks: ["Machine Translation"], datasets: ["FLORES-200"] };
    for (const mode of ["auto", "vector", "keyword"] as const) {
      const { request, notes } = buildSearchRequest({ ...form, mode }, f, bounds);
      expect(request).toMatchObject({ methods: ["Back-translation"], tasks: ["Machine Translation"], datasets: ["FLORES-200"] });
      expect(notes).toEqual([]);
    }
  });

  it("hybrid sends the year range but NOT the element filters, and says so (the API would answer 422)", () => {
    const f = { ...EMPTY_FILTERS, methods: ["Back-translation"] };
    const { request, notes } = buildSearchRequest({ ...form, mode: "hybrid", years: [2020, 2026] }, f, bounds);
    expect(request).toMatchObject({ mode: "hybrid", year_min: 2020 });
    expect(request).not.toHaveProperty("methods");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toMatch(/Hybrid search applies only the year range/);
  });

  it("hybrid without element filters has no note", () => {
    expect(buildSearchRequest({ ...form, mode: "hybrid" }, EMPTY_FILTERS, bounds).notes).toEqual([]);
  });

  it("the confidence filter is for candidates only and never goes to /search", () => {
    const { request } = buildSearchRequest(form, { ...EMPTY_FILTERS, minConfidence: 0.8 }, bounds);
    expect(JSON.stringify(request)).not.toMatch(/confidence/);
  });
});
