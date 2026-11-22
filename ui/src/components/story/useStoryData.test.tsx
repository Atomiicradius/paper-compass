import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { ApiError } from "@/api/client";
import { makeClusters, makeLandscape, makeOpportunityList, makeStoryExplanation, makeTrends } from "@/test/story-fixtures";

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, landscape: vi.fn(), clusters: vi.fn(), trends: vi.fn(), opportunities: vi.fn(), explain: vi.fn() } };
});
import { api } from "@/api/client";
import { useStoryData } from "@/components/story/useStoryData";

function allGood() {
  vi.mocked(api.landscape).mockResolvedValue(makeLandscape());
  vi.mocked(api.clusters).mockResolvedValue(makeClusters());
  vi.mocked(api.trends).mockImplementation((kind) => Promise.resolve(makeTrends(kind === "task" ? "task" : "method")));
  vi.mocked(api.opportunities).mockResolvedValue(makeOpportunityList());
  vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation());
}
const down = () => Promise.reject(new ApiError(503, "unavailable"));

describe("useStoryData", () => {
  beforeEach(() => {
    for (const f of [api.landscape, api.clusters, api.trends, api.opportunities, api.explain]) vi.mocked(f).mockReset();
  });

  it("returns every figure the steps need, from the existing API functions only", async () => {
    allGood();
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(result.current.verifiedCitations).not.toBeNull());
    const d = result.current;
    expect(d.papers).toBe(1999);
    expect(d.papersPerYear).toEqual({ "2019": 120, "2020": 150, "2021": 180, "2022": 210 });
    expect(d.clusterCount).toBe(7);
    expect(d.clusterSizes).toEqual([420, 398, 135, 69, 38, 37, 19]);
    expect(d.papersInNoCluster).toBe(883);
    expect(d.topMethods.map((t) => t.name)).toEqual(["Transformer", "Fine-tuning", "Back-translation", "Beam Search"]); // the top 4, most used first
    expect(d.topTasks[0]).toMatchObject({ name: "Machine Translation", total: 300 });
    expect(d.universeN).toBe(399);
    expect(d.verifiedCitations).toBe(2);
    // nothing else is called: no other endpoint, and the explanation is for the top opportunity only
    expect(api.explain).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.explain).mock.calls[0]![0]).toBe(7);
  });

  it("takes the opportunity with the highest score as rank 1, not the first in the list", async () => {
    allGood();
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(result.current.top?.opportunity_id).toBe(7));
    expect(result.current.top?.score).toBe(73.7);
  });

  it("picks two or three evidence papers, closest existing work first, without repeats", async () => {
    allGood();
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(result.current.evidence.length).toBeGreaterThan(0));
    const ids = result.current.evidence.map((e) => e.paper_id);
    expect(ids.length).toBeGreaterThanOrEqual(2);
    expect(ids.length).toBeLessThanOrEqual(3);
    expect(ids.slice(0, 2)).toEqual(["WN1", "WN2"]);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("gives a verified count only when the explanation's own citation check passed in full", async () => {
    allGood();
    // one cited paper is not part of the evidence: the check is not "all verified", so no count is shown
    vi.mocked(api.explain).mockResolvedValue(makeStoryExplanation({ citation_check: { ok: true, cited: ["WN1", "WZZ"], unknown: [], uncited_markers_count: 0, has_no_citations: false } }));
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(result.current.universeN).toBe(399));
    expect(result.current.verifiedCitations).toBeNull();
  });

  it("returns nothing (null or empty), never a made-up figure, for whatever the API could not provide", async () => {
    vi.mocked(api.landscape).mockImplementation(down);
    vi.mocked(api.clusters).mockImplementation(down);
    vi.mocked(api.trends).mockImplementation(down);
    vi.mocked(api.opportunities).mockResolvedValue({ total: 0, items: [], disclaimer: "x" });
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(api.opportunities).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toEqual({
      papers: null, papersPerYear: null, clusterCount: null, clusterSizes: [], papersInNoCluster: null,
      topMethods: [], topTasks: [], top: null, universeN: null, evidence: [], verifiedCitations: null,
    });
    expect(api.explain).not.toHaveBeenCalled(); // no opportunity, so no explanation is requested
  });

  it("uses the cluster count from the landscape when the clusters endpoint is down, and still shows no per-cluster figures", async () => {
    allGood();
    vi.mocked(api.clusters).mockImplementation(down);
    const { result } = renderHook(() => useStoryData());
    await waitFor(() => expect(result.current.papers).toBe(1999));
    expect(result.current.clusterCount).toBe(7);
    expect(result.current.papersInNoCluster).toBeNull();
    expect(result.current.clusterSizes).toEqual([]);
  });
});
