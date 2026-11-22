import type {
  Clusters, Explanation, Landscape, Opportunity, OpportunityList, Paper, PaperGraph, RelatedResponse, SearchRequest, SearchResponse,
  TrendItem,
} from "./types";

/** Base URL of the API. In dev the Vite server proxies /api to FastAPI (see vite.config.ts). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

const START_HINT = "Start it with: powershell -File api/run-api.ps1";

/** status 0 = unreachable, otherwise the HTTP status. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** FastAPI validation errors arrive as [{loc, msg}]; turn them into one readable line. */
export function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object" && "msg" in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc) ? (d as { loc: unknown[] }).loc : [];
          const field = loc.length ? String(loc[loc.length - 1]) : "?";
          return field + ": " + String((d as { msg: unknown }).msg);
        }
        return String(d);
      })
      .join("; ");
  }
  return detail == null ? "" : JSON.stringify(detail);
}

interface CallOptions {
  body?: unknown;
  signal?: AbortSignal;
  params?: Record<string, string | number | undefined>;
}

async function call<T>(method: string, path: string, opts: CallOptions = {}): Promise<T> {
  let url = API_BASE + path;
  if (opts.params) {
    const entries = Object.entries(opts.params).filter(([, v]) => v !== undefined) as [string, string | number][];
    if (entries.length) url += "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: opts.body !== undefined ? { "content-type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "API not reachable at " + API_BASE + ". " + START_HINT);
  }
  if (!res.ok) {
    // the dev proxy answers 500/502/504 when the API process is down or the connection was refused
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: unknown };
      detail = formatDetail(j.detail ?? detail);
    } catch {
      /* body was not JSON */
    }
    if (res.status === 502 || res.status === 504) throw new ApiError(0, "API not reachable (" + res.status + "). " + START_HINT);
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  opportunities: (signal?: AbortSignal, limit = 200) => call<OpportunityList>("GET", "/opportunities", { params: { limit }, signal }),
  opportunity: (id: number, signal?: AbortSignal) => call<Opportunity>("GET", "/opportunities/" + id, { signal }),
  explain: (id: number, signal?: AbortSignal) => call<Explanation>("POST", "/opportunities/" + id + "/explain", { signal }),
  search: (body: SearchRequest, signal?: AbortSignal) => call<SearchResponse>("POST", "/search", { body, signal }),
  paper: (id: string, signal?: AbortSignal) => call<Paper>("GET", "/papers/" + encodeURIComponent(id), { signal }),
  paperGraph: (id: string, limit = 200, signal?: AbortSignal) =>
    call<PaperGraph>("GET", "/papers/" + encodeURIComponent(id) + "/graph", { params: { limit }, signal }),
  related: (id: string, topK = 8, signal?: AbortSignal) =>
    call<RelatedResponse>("GET", "/papers/" + encodeURIComponent(id) + "/related", { params: { top_k: topK }, signal }),
  trends: (elementType: "method" | "dataset" | "task" | "topic", signal?: AbortSignal) =>
    call<TrendItem[]>("GET", "/trends", { params: { element_type: elementType }, signal }),
  clusters: (signal?: AbortSignal) => call<Clusters>("GET", "/clusters", { signal }),
  landscape: (signal?: AbortSignal) => call<Landscape>("GET", "/landscape", { signal }),
  /** 501 until an LLM client is chosen (open decision O5). */
  rag: (question: string, signal?: AbortSignal) => call<unknown>("POST", "/rag/query", { body: { question }, signal }),
};
