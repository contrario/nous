"""S466: one client, one share of option T's pool.

A client key (slowapi's get_remote_address, an IPv4-mapped address
folded to IPv4, other IPv6 keyed by its /64, loopback exempt) holds at
most its cap of the budget pool's slots at once. A key at its cap
answers 429 CAPn before it waits, with Retry-After 5 and the
RateLimit-Policy and RateLimit fields of an Internet-Draft, and its
work never runs. A key's count is given back where the slot is: when
its worker's thread ends, on the cancel path, on a submit failure and
on a BUSY reply. A loopback key that carries X-Forwarded-For trips one
warning a minute at most. NOUS_CLIENT_CAP sets the cap; 0 turns it off.

Timing instrument: S465's asyncio shim scales each wait_for timeout by
0.01; held workers wait on an Event that teardown releases; thread
ends are read through a Condition, not by sleeping.
"""
import ast
import asyncio
import concurrent.futures
import logging
import re
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

KEY = "test_key_s466_client_cap"
H = {"X-API-Key": KEY}
ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
A = "198.51.100.9"
B = "203.0.113.5"
SRC = (
    "world MarketMonitor {" + NL
    + "    law cost_ceiling = $3.00 per cycle" + NL
    + "    heartbeat = 20s" + NL
    + "}" + NL
    + "soul Scanner {" + NL
    + "    mind: claude-sonnet-4-6 @ Tier1" + NL
    + "    senses: [http_get]" + NL
    + "    memory { count: int = 0 }" + NL
    + "}" + NL
)
SCALE = 0.01


class Hold:
    def __init__(self):
        self.release = threading.Event()
        self.cv = threading.Condition()
        self.entered = 0
        self.exited = 0

    def wrap(self, fn):
        def held(*a, **k):
            with self.cv:
                self.entered += 1
                self.cv.notify_all()
            try:
                self.release.wait(10)
                return fn(*a, **k)
            finally:
                with self.cv:
                    self.exited += 1
                    self.cv.notify_all()
        return held

    def reach(self, attr, n, t=10.0):
        with self.cv:
            return self.cv.wait_for(lambda: getattr(self, attr) >= n, t)


@pytest.fixture
def hold():
    h = Hold()
    yield h
    h.release.set()
    h.reach("exited", h.entered)


@pytest.fixture
def api(monkeypatch):
    import nous_api_server as S
    monkeypatch.setattr(S, "API_KEYS", {KEY})
    monkeypatch.setattr(S.limiter, "enabled", False)
    monkeypatch.setattr(S, "_S465_ADMIT_WAIT_S", 0.1, raising=False)
    monkeypatch.setattr(S, "_S465_POOL_SIZE", 4, raising=False)
    monkeypatch.setattr(S, "_s465_pool", None, raising=False)
    monkeypatch.setattr(S, "_S466_CLIENT_CAP", 2, raising=False)
    monkeypatch.setattr(S, "_s466_table", {}, raising=False)
    return S


def _client(api, host):
    return TestClient(api.app, raise_server_exceptions=False,
                      client=(host, 50000))


def _shim(monkeypatch, S, scale=SCALE):
    real = asyncio

    class Shim(types.ModuleType):
        def __getattr__(self, name):
            return getattr(real, name)

    sh = Shim("s466_asyncio_shim")

    async def wait_for(aw, timeout):
        return await real.wait_for(
            aw, None if timeout is None else timeout * scale)

    sh.wait_for = wait_for
    monkeypatch.setattr(S, "asyncio", sh)


def _detail(r):
    d = r.json().get("detail")
    return d if isinstance(d, dict) else {"_raw": d}


def _table(api):
    return dict(getattr(api, "_s466_table", {}))


def _settles(api, want, t=5.0):
    end = time.monotonic() + t
    while time.monotonic() < end:
        if _table(api) == want:
            return True
        time.sleep(0.01)
    return False


def _held_compile(api, monkeypatch, hold):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))


def _post(c, route="/v1/compile"):
    if route == "/v1/run":
        return c.post(route, headers=H, json={"source": SRC, "mode": "dry-run"})
    return c.post(route, headers=H, json={"source": SRC})


def _is_cap(r, code):
    assert r.status_code == 429, (r.status_code, r.text[:200])
    d = _detail(r)
    assert d.get("code") == code
    assert d.get("work_started") is False
    assert d.get("scope") == "client"
    assert re.fullmatch(r"[0-9a-f]{32}", d.get("error_id", ""))
    assert r.headers.get("retry-after") == "5"


def _req(host, headers=()):
    return Request({"type": "http", "client": (host, 1),
                    "headers": list(headers), "method": "GET", "path": "/"})


def test_c1_key_at_cap_gets_429_cap001_and_never_runs(api, hold,
                                                      monkeypatch):
    _held_compile(api, monkeypatch, hold)
    c = _client(api, A)
    r1, r2 = _post(c), _post(c)
    assert r1.status_code == r2.status_code == 503
    assert hold.reach("entered", 2)
    r3 = _post(c)
    _is_cap(r3, "CAP001")
    assert hold.entered == 2


def test_c2_another_key_is_admitted(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    ca, cb = _client(api, A), _client(api, B)
    _post(ca), _post(ca)
    r = _post(cb)
    assert r.status_code == 503, (r.status_code, r.text[:200])
    assert _detail(r).get("code") == "TIMEOUT001"
    assert hold.reach("entered", 3)


def test_c3_count_returns_only_when_the_thread_ends(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    c = _client(api, A)
    _post(c), _post(c)
    assert hold.reach("entered", 2)
    _is_cap(_post(c), "CAP001")
    hold.release.set()
    assert hold.reach("exited", 2)
    assert _settles(api, {})
    r = _post(c)
    assert r.status_code == 200, (r.status_code, r.text[:200])


def test_c4_the_cap_counts_across_routes(api, hold, monkeypatch):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))
    monkeypatch.setattr(api, "parse_nous", hold.wrap(api.parse_nous))
    c = _client(api, A)
    r1 = _post(c, "/v1/compile")
    r2 = _post(c, "/v1/verify")
    assert _detail(r1).get("code") == "TIMEOUT001"
    assert _detail(r2).get("code") == "TIMEOUT002"
    _is_cap(_post(c, "/v1/run"), "CAP004")


def test_c5_the_key():
    import nous_api_server as S
    k = S._s466_client_key
    assert k(_req("2001:db8:1:2::5")) == "2001:db8:1:2::/64"
    assert k(_req("2001:db8:1:2::5")) == k(_req("2001:db8:1:2:ffff::9"))
    assert k(_req("2001:db8:1:2::5")) != k(_req("2001:db8:1:3::5"))
    assert k(_req("::ffff:1.2.3.4")) == k(_req("1.2.3.4")) == "1.2.3.4"
    assert k(_req("testclient")) == "testclient"
    assert k(_req("127.0.0.1")) is None
    assert k(_req("::1")) is None


class _NeverStarts:
    def __init__(self, api, raise_on_submit=False):
        self.api = api
        self.raise_on_submit = raise_on_submit
        self.seen = []

    def submit(self, fn):
        self.seen.append(_table(self.api))
        if self.raise_on_submit:
            raise RuntimeError("s466 probe: submit refused")
        return concurrent.futures.Future()


def test_c6_busy_cancel_and_submit_failure_give_the_count_back(
        api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    monkeypatch.setattr(api, "_S465_POOL_SIZE", 1, raising=False)
    c = _client(api, A)
    _post(c)
    assert hold.reach("entered", 1)
    assert _table(api) == {A: 1}
    r = _post(c)
    assert r.status_code == 503 and _detail(r).get("code") == "BUSY001"
    assert _table(api) == {A: 1}
    hold.release.set()
    assert hold.reach("exited", 1)
    assert _settles(api, {})
    for raising in (False, True):
        fake = _NeverStarts(api, raising)
        monkeypatch.setattr(api, "_s465_pool",
                            (fake, threading.BoundedSemaphore(4)))
        r = _post(c)
        assert fake.seen == [{A: 1}]
        assert _table(api) == {}
        if raising:
            assert r.status_code == 422
            assert _detail(r).get("code") == "COMPILE001"
            assert "s466 probe: submit refused" in _detail(r).get("error", "")
        else:
            assert r.status_code == 503
            assert _detail(r).get("code") == "BUSY001"


def test_c7_the_table_ends_empty(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    ca, cb = _client(api, A), _client(api, B)
    _post(ca), _post(ca)
    _is_cap(_post(ca), "CAP001")
    _post(cb)
    assert hold.reach("entered", 3)
    assert _table(api) == {A: 2, B: 1}
    hold.release.set()
    assert hold.reach("exited", 3)
    assert _settles(api, {})


def test_c8_a_key_under_its_cap_still_meets_busy(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    monkeypatch.setattr(api, "_S465_POOL_SIZE", 1, raising=False)
    _post(_client(api, B))
    assert hold.reach("entered", 1)
    r = _post(_client(api, A))
    assert r.status_code == 503, (r.status_code, r.text[:200])
    assert _detail(r).get("code") == "BUSY001"
    assert r.headers.get("retry-after") == "5"


def test_c9_every_call_site_passes_the_request():
    tree = ast.parse((ROOT / "nous_api_server.py").read_text("utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == "_s465_run_budgeted"]
    assert len(calls) == 5
    for n in calls:
        kws = {kw.arg: kw.value for kw in n.keywords}
        assert "request" in kws, n.lineno
        assert isinstance(kws["request"], ast.Name), n.lineno
        assert kws["request"].id == "request", n.lineno


def test_c10_the_cap_warning_names_no_address(api, hold, monkeypatch,
                                              caplog):
    caplog.set_level(logging.INFO)
    _held_compile(api, monkeypatch, hold)
    c = _client(api, A)
    _post(c), _post(c)
    r = _post(c)
    d = _detail(r)
    lines = [x.getMessage() for x in caplog.records
             if x.levelno == logging.WARNING and "CAP001" in x.getMessage()]
    assert len(lines) == 1
    assert d.get("error_id", "@") in lines[0]
    assert A not in lines[0] and "198.51.100" not in lines[0]
    assert NL not in lines[0]


def test_c11_a_loopback_key_is_not_capped(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    monkeypatch.setattr(api, "_S465_POOL_SIZE", 2, raising=False)
    monkeypatch.setattr(api, "_S466_CLIENT_CAP", 1, raising=False)
    c = _client(api, "127.0.0.1")
    r1, r2 = _post(c), _post(c)
    assert _detail(r1).get("code") == "TIMEOUT001"
    assert _detail(r2).get("code") == "TIMEOUT001"
    r3 = _post(c)
    assert r3.status_code == 503 and _detail(r3).get("code") == "BUSY001"


def test_c12_the_tripwire_once_a_minute_without_an_address(api, monkeypatch,
                                                           caplog):
    caplog.set_level(logging.INFO)
    c = _client(api, "127.0.0.1")
    xff = {"X-Forwarded-For": "203.0.113.7", **H}

    def trips():
        return [x.getMessage() for x in caplog.records
                if x.levelno == logging.WARNING
                and "tripwire" in x.getMessage()]

    monkeypatch.setattr(api, "_s466_trip_last",
                        time.monotonic() - 61.0, raising=False)
    assert c.post("/v1/compile", headers=xff,
                  json={"source": SRC}).status_code == 200
    assert len(trips()) == 1
    monkeypatch.setattr(api, "_s466_trip_last",
                        time.monotonic() - 59.0, raising=False)
    c.post("/v1/compile", headers=xff, json={"source": SRC})
    assert len(trips()) == 1
    monkeypatch.setattr(api, "_s466_trip_last",
                        time.monotonic() - 61.0, raising=False)
    c.post("/v1/compile", headers=xff, json={"source": SRC})
    assert len(trips()) == 2
    for m in trips():
        assert "203.0.113.7" not in m and "127.0.0.1" not in m
    c.post("/v1/compile", headers=H, json={"source": SRC})
    assert len(trips()) == 2


def test_c13_the_kill_switch(api, hold, monkeypatch):
    p = api._s466_parse_cap
    assert p(None, 12) == (3, False)
    assert p("0", 12) == (0, False)
    assert p("1", 12) == (1, False)
    assert p("x", 12) == (3, True)
    assert p("-2", 12) == (3, True)
    assert p(None, 4) == (2, False)
    _held_compile(api, monkeypatch, hold)
    monkeypatch.setattr(api, "_S466_CLIENT_CAP", 0, raising=False)
    c = _client(api, A)
    rs = [_post(c) for _ in range(3)]
    assert [_detail(r).get("code") for r in rs] == ["TIMEOUT001"] * 3


def test_c14_the_429_carries_the_quota_fields(api, hold, monkeypatch):
    _held_compile(api, monkeypatch, hold)
    c = _client(api, A)
    _post(c), _post(c)
    r = _post(c)
    _is_cap(r, "CAP001")
    assert (r.headers.get("ratelimit-policy")
            == '"client";q=2;qu="concurrent-requests"')
    assert r.headers.get("ratelimit") == '"client";r=0'


def test_c15_the_doc_names_the_cap():
    t = (ROOT / "docs" / "API_CLIENT_CAP.md").read_text("utf-8")
    for token in ("429", "CAP001", "CAP002", "CAP003", "CAP004", "CAP005",
                  "Retry-After", "RateLimit-Policy", "NOUS_CLIENT_CAP",
                  "Internet-Draft", "/64", "loopback"):
        assert token in t, token


def test_c16_a_cancelled_wait_gives_the_count_back(api, hold, monkeypatch):
    monkeypatch.setattr(api, "_S465_POOL_SIZE", 1, raising=False)
    monkeypatch.setattr(api, "_S465_ADMIT_WAIT_S", 30.0, raising=False)
    held = hold.wrap(lambda _d: None)

    async def main():
        t1 = asyncio.ensure_future(api._s465_run_budgeted(
            "compile", held, request=_req(B)))
        while hold.entered < 1:
            await asyncio.sleep(0.01)
        t2 = asyncio.ensure_future(api._s465_run_budgeted(
            "compile", lambda _d: None, request=_req(A)))
        await asyncio.sleep(0.1)
        snap = _table(api)
        t2.cancel()
        cancelled = False
        try:
            await t2
        except asyncio.CancelledError:
            cancelled = True
        after = _table(api)
        hold.release.set()
        await t1
        return snap, cancelled, after

    snap, cancelled, after = asyncio.run(main())
    assert snap == {A: 1, B: 1}
    assert cancelled
    assert after == {B: 1}
