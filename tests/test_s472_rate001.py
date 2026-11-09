"""S472: RATE001 tells the truth about when to come back.

A route's per-minute limit refused the request. The 429 keeps "error"
and "code" at the top level as they were and adds error_id,
retry_after, limit, scope and work_started. Retry-After is the seconds
until the limiter's window for that key resets, rounded up and clamped
to [1, the limit's window]; the whole window when the window cannot
be read. RateLimit-Policy and RateLimit are the fields of
draft-ietf-httpapi-ratelimit-headers-11, an Internet-Draft. One
warning line per scope per 60 s at most, the client key hashed. A
limit is keyed by its route, not its URL (key_style "endpoint").

Clock instrument: limits.storage.memory's time is replaced by an
offset clock to move the limiter's window; the log's clock is the
module's _s472_clock. No test sleeps.
"""
import ast
import asyncio
import logging
import re
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

ROOT = Path(__file__).resolve().parent.parent
HEALTH = "/v1/health"


@pytest.fixture
def api(monkeypatch):
    import nous_api_server as S
    monkeypatch.setattr(S.limiter, "enabled", True)
    monkeypatch.setattr(S, "_s472_log_state", {}, raising=False)
    S.limiter.reset()
    yield S
    S.limiter.reset()


@pytest.fixture
def client(api):
    return TestClient(api.app, raise_server_exceptions=False)


def _clock(monkeypatch, offset):
    import limits.storage.memory as mem
    real = time.time
    monkeypatch.setattr(mem, "time", types.SimpleNamespace(
        time=lambda: real() + offset, monotonic=time.monotonic,
        sleep=time.sleep, perf_counter=time.perf_counter))


def _refuse(client, path=HEALTH, n=200):
    for _ in range(n):
        assert client.get(path).status_code != 429
    return client.get(path)


def _ra(r):
    v = r.headers.get("retry-after")
    assert v is not None and re.fullmatch(r"[0-9]+", v), v
    return int(v)


def test_x1_under_the_limit_no_fields(client):
    r = client.get(HEALTH)
    assert r.status_code == 200
    for h in ("retry-after", "ratelimit-policy", "ratelimit"):
        assert h not in r.headers


def test_x2_error_and_code_kept_at_top_level(client):
    r = _refuse(client)
    assert r.status_code == 429
    j = r.json()
    assert j["error"] == "Rate limit exceeded"
    assert j["code"] == "RATE001"


def test_x3_content_type_json(client):
    r = _refuse(client)
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/json")


def test_r1_body_members(client):
    r = _refuse(client)
    assert r.status_code == 429
    j = r.json()
    assert re.fullmatch(r"[0-9a-f]{32}", j["error_id"])
    assert isinstance(j["retry_after"], int)
    assert j["limit"] == "200 per 1 minute"
    assert j["scope"] == "route"
    assert j["work_started"] is False


def test_r2_retry_after_header_equals_body(client):
    r = _refuse(client)
    n = _ra(r)
    assert 1 <= n <= 60
    assert r.json()["retry_after"] == n


def test_r3_ratelimit_fields(client):
    r = _refuse(client)
    n = _ra(r)
    assert r.headers["ratelimit-policy"] == '"route";q=200;w=60'
    assert r.headers["ratelimit"] == '"route";r=0;t=%d' % n


def test_r4_retry_after_is_sufficient(client, monkeypatch):
    n = _ra(_refuse(client))
    _clock(monkeypatch, n)
    assert client.get(HEALTH).status_code == 200


def test_r5_retry_after_is_tight(client, monkeypatch):
    n = _ra(_refuse(client))
    assert n >= 3
    _clock(monkeypatch, n - 2)
    assert client.get(HEALTH).status_code == 429


def _exc(item):
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import Limit
    return RateLimitExceeded(Limit(item, lambda: "k", None, False, None,
                                   None, None, 1, False))


def _req():
    return Request({"type": "http", "method": "GET", "path": "/x",
                    "headers": [], "query_string": b""})


def test_r6_reply_for_another_limit(api):
    from limits import parse
    item = parse("30/minute")
    args = ["k6", "scope6"]
    for _ in range(31):
        api.limiter.limiter.hit(item, *args)
    req = _req()
    req.state.view_rate_limit = (item, args)
    r = asyncio.run(api.rate_limit_handler(req, _exc(item)))
    assert r.status_code == 429
    n = int(r.headers["retry-after"])
    assert 1 <= n <= 60
    assert r.headers["ratelimit-policy"] == '"route";q=30;w=60'
    assert r.headers["ratelimit"] == '"route";r=0;t=%d' % n


def test_r7_window_unreadable_gives_the_whole_window(api, monkeypatch):
    from limits import parse
    item = parse("30/minute")

    def boom(*a, **k):
        raise RuntimeError("storage down")
    monkeypatch.setattr(api.limiter.limiter, "get_window_stats", boom)
    req = _req()
    req.state.view_rate_limit = (item, ["k7", "scope7"])
    r = asyncio.run(api.rate_limit_handler(req, _exc(item)))
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert b'"retry_after":60' in r.body
    assert r.headers["ratelimit-policy"] == '"route";q=30;w=60'


def test_r8_no_view_rate_limit_uses_the_exception(api):
    from limits import parse
    item = parse("30/minute")
    r = asyncio.run(api.rate_limit_handler(_req(), _exc(item)))
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert b'"limit":"30 per 1 minute"' in r.body


def test_r9_one_line_per_scope_per_minute(api, client, monkeypatch,
                                          caplog):
    t = [1000.0]
    monkeypatch.setattr(api, "_s472_clock", lambda: t[0], raising=False)
    caplog.set_level(logging.WARNING, logger="nous_api")
    for _ in range(200):
        client.get(HEALTH)
    for _ in range(50):
        assert client.get(HEALTH).status_code == 429
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("rate_limit ")]
    assert len(lines) == 1
    assert "code=RATE001" in lines[0] and "refused=1 " in lines[0]
    assert re.search(r"client=[0-9a-f]{8} ", lines[0])
    t[0] += 61.0
    assert client.get(HEALTH).status_code == 429
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("rate_limit ")]
    assert len(lines) == 2 and "refused=50 " in lines[1]
    assert not any("testclient" in x for x in lines)


def test_r10_moving_window_is_sufficient(api, client, monkeypatch):
    from limits.strategies import MovingWindowRateLimiter
    monkeypatch.setattr(api.limiter, "_limiter",
                        MovingWindowRateLimiter(api.limiter._storage))
    api.limiter.reset()
    n = _ra(_refuse(client))
    assert 1 <= n <= 60
    _clock(monkeypatch, n)
    assert client.get(HEALTH).status_code == 200


def test_r12_a_route_not_a_url(client):
    codes = [client.get("/v1/templates/n%d" % i).status_code
             for i in range(1, 202)]
    assert 429 not in codes[:200]
    assert codes[200] == 429


def test_r13_limiter_call_by_ast():
    tree = ast.parse((ROOT / "nous_api_server.py").read_text(
        encoding="utf-8"))
    calls = [n.value for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "limiter"
                     for t in n.targets)
             and isinstance(n.value, ast.Call)]
    assert len(calls) == 1
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(kw.get("key_style"), ast.Constant)
    assert kw["key_style"].value == "endpoint"
    assert "headers_enabled" not in kw


def test_r14_clamp(api, monkeypatch):
    from limits import parse
    item = parse("30/minute")
    req = _req()
    req.state.view_rate_limit = (item, ["k14", "scope14"])
    lim = api.limiter.limiter
    monkeypatch.setattr(lim, "get_window_stats",
                        lambda *a, **k: (time.time() + 1000.0, 0))
    r = asyncio.run(api.rate_limit_handler(req, _exc(item)))
    assert r.headers["retry-after"] == "60"
    monkeypatch.setattr(lim, "get_window_stats",
                        lambda *a, **k: (time.time() - 5.0, 0))
    r = asyncio.run(api.rate_limit_handler(req, _exc(item)))
    assert r.headers["retry-after"] == "1"
