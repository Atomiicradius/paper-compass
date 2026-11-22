import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(url, init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("builds URLs and query strings against /api", async () => {
    const f = mockFetch(() => json({ total: 0, items: [], disclaimer: "x" }));
    await api.opportunities(undefined, 50);
    expect(f.mock.calls[0]?.[0]).toBe("/api/opportunities?limit=50");
    mockFetch(() => json({}));
    const g = mockFetch(() => json({ center: "Paper:W1", nodes: [], edges: [] }));
    await api.paperGraph("W1", 300);
    expect(g.mock.calls[0]?.[0]).toBe("/api/papers/W1/graph?limit=300");
  });

  it("encodes paper ids so odd characters cannot change the route", async () => {
    const f = mockFetch(() => json({}));
    await api.paper("W1/../x?y");
    expect(f.mock.calls[0]?.[0]).toBe("/api/papers/W1%2F..%2Fx%3Fy");
  });

  it("posts JSON for search and explain", async () => {
    const f = mockFetch(() => json({ results: [] }));
    await api.search({ query: "back-translation", top_k: 5, collapse_same_title: true });
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ query: "back-translation", top_k: 5, collapse_same_title: true });
    expect((init.headers as Record<string, string>)["content-type"]).toBe("application/json");
    await api.explain(14);
    expect((f.mock.calls[1] as [string, RequestInit])[0]).toBe("/api/opportunities/14/explain");
    expect((f.mock.calls[1] as [string, RequestInit])[1].method).toBe("POST");
  });

  it("turns a 404 into ApiError with the server's reason", async () => {
    mockFetch(() => json({ detail: "paper not found" }, 404));
    await expect(api.paper("NOPE")).rejects.toMatchObject({ status: 404, detail: "paper not found" });
  });

  it("turns FastAPI validation errors (422) into one readable line", async () => {
    mockFetch(() => json({ detail: [{ loc: ["body", "query"], msg: "Value error, must not be blank" }] }, 422));
    await expect(api.search({ query: "  " })).rejects.toMatchObject({ status: 422, detail: "query: Value error, must not be blank" });
  });

  it("keeps the 503 reason (not configured / Neo4j down)", async () => {
    mockFetch(() => json({ detail: "API is not configured: set PC_PG_DSN" }, 503));
    await expect(api.landscape()).rejects.toMatchObject({ status: 503, detail: expect.stringContaining("PC_PG_DSN") });
  });

  it("maps a refused connection and the dev proxy's 502 / 504 to 'not reachable' (status 0)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.clusters()).rejects.toMatchObject({ status: 0, detail: expect.stringContaining("not reachable") });
    mockFetch(() => new Response("bad gateway", { status: 502 }));
    await expect(api.clusters()).rejects.toMatchObject({ status: 0 });
    mockFetch(() => new Response("", { status: 504 }));
    const e = await api.clusters().catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).status).toBe(0);
  });

  it("copes with a non-JSON error body", async () => {
    mockFetch(() => new Response("Internal Server Error", { status: 500, statusText: "Internal Server Error" }));
    await expect(api.landscape()).rejects.toMatchObject({ status: 500, detail: "Internal Server Error" });
  });

  it("lets an aborted request surface as AbortError, not as an API error", async () => {
    const ctrl = new AbortController();
    vi.stubGlobal("fetch", vi.fn((_u: string, init?: RequestInit) => new Promise((_res, rej) => {
      init?.signal?.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
    })));
    const p = api.opportunities(ctrl.signal);
    ctrl.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });
});
