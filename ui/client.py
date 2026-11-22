"""Thin HTTP client for the paper-compass API (api/main.py). The UI never queries the databases directly.

PC_API_URL sets the base URL (default http://127.0.0.1:8000).
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class Client:
    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None, timeout: float = 120):
        self.base_url = (base_url or os.environ.get("PC_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout)

    def _call(self, method: str, path: str, **kw) -> Any:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.TimeoutException as e:
            raise ApiError(-1, f"the API at {self.base_url} did not answer within {self._http.timeout.read:.0f} s "
                               "(the first vector search downloads and loads SPECTER2); try again") from e
        except httpx.HTTPError as e:
            raise ApiError(0, f"API not reachable at {self.base_url} ({e.__class__.__name__})") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except (ValueError, AttributeError):
                detail = r.text
            if isinstance(detail, list):     # FastAPI validation errors: [{loc, msg, ...}]
                detail = "; ".join(f"{(d.get('loc') or ['?'])[-1]}: {d.get('msg', d)}" if isinstance(d, dict) else str(d)
                                   for d in detail)
            raise ApiError(r.status_code, str(detail))
        return r.json()

    # --- endpoints (data-and-contracts.md section 5) ---
    def search(self, query: str, top_k: int = 10, mode: str = "auto", **filters) -> dict:
        body = {"query": query, "top_k": top_k, "mode": mode, **{k: v for k, v in filters.items() if v not in (None, [], "")}}
        return self._call("POST", "/search", json=body)

    def paper(self, paper_id: str) -> dict:
        return self._call("GET", f"/papers/{paper_id}")

    def paper_graph(self, paper_id: str, limit: int = 200) -> dict:
        return self._call("GET", f"/papers/{paper_id}/graph", params={"limit": limit})

    def related(self, paper_id: str, top_k: int = 10) -> dict:
        return self._call("GET", f"/papers/{paper_id}/related", params={"top_k": top_k})

    def landscape(self) -> dict:
        return self._call("GET", "/landscape")

    def clusters(self) -> dict:
        return self._call("GET", "/clusters")

    def trends(self, element_type: str = "method", label: str | None = None) -> list[dict]:
        params = {"element_type": element_type}
        if label:
            params["label"] = label
        return self._call("GET", "/trends", params=params)

    def opportunities(self, limit: int = 200, offset: int = 0, min_confidence: float | None = None) -> dict:
        params: dict = {"limit": limit, "offset": offset}
        if min_confidence is not None:
            params["min_confidence"] = min_confidence
        return self._call("GET", "/opportunities", params=params)

    def opportunity(self, opportunity_id: int) -> dict:
        return self._call("GET", f"/opportunities/{opportunity_id}")

    def explain(self, opportunity_id: int) -> dict:
        return self._call("POST", f"/opportunities/{opportunity_id}/explain")

    def rag_query(self, question: str) -> dict:
        return self._call("POST", "/rag/query", json={"question": question})
