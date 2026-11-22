import json

import httpx
import pytest

from ui.client import ApiError, Client


def _client(handler):
    return Client("http://api.test", transport=httpx.MockTransport(handler))


def test_search_drops_empty_filters():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["path"] = req.url.path
        return httpx.Response(200, json={"results": []})

    _client(handler).search("back-translation", top_k=5, year_min=None, methods=[], tasks=["Machine Translation"])
    assert seen["path"] == "/search"
    assert seen["body"] == {"query": "back-translation", "top_k": 5, "mode": "auto", "tasks": ["Machine Translation"]}


def test_error_detail_is_raised():
    c = _client(lambda req: httpx.Response(404, json={"detail": "paper not found"}))
    with pytest.raises(ApiError) as e:
        c.paper("NOPE")
    assert e.value.status == 404 and e.value.detail == "paper not found"


def test_unreachable_api_is_status_0():
    def handler(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as e:
        _client(handler).landscape()
    assert e.value.status == 0


def test_opportunities_params():
    seen = {}

    def handler(req):
        seen["params"] = dict(req.url.params)
        return httpx.Response(200, json={"total": 0, "items": [], "disclaimer": "x"})

    _client(handler).opportunities(limit=50, min_confidence=0.5)
    assert seen["params"] == {"limit": "50", "offset": "0", "min_confidence": "0.5"}


def test_timeout_is_status_minus_1():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ApiError) as e:
        _client(handler).search("x")
    assert e.value.status == -1 and "did not answer" in e.value.detail


def test_validation_errors_are_readable():
    body = {"detail": [{"type": "value_error", "loc": ["body", "query"], "msg": "Value error, must not be blank"},
                       {"type": "int_parsing", "loc": ["query", "limit"], "msg": "Input should be a valid integer"}]}
    c = _client(lambda req: httpx.Response(422, json=body))
    with pytest.raises(ApiError) as e:
        c.search("   ")
    assert e.value.status == 422
    assert e.value.detail == "query: Value error, must not be blank; limit: Input should be a valid integer"
