"""S465 option T: a server-side deadline answers 503 and tells the truth.

A request whose work never started answers 503 with Retry-After and
its route's BUSY code, and its work never runs; a request whose work
started and overran its budget answers 503 without Retry-After and its
route's TIMEOUT code; one code a route and cause; a worker slot is
freed when its thread ends, not when its reply is sent; the Rekor
submission does not begin unless the export's remaining budget covers
its two HTTP calls; every budget, plus the admission wait and a
margin, stays under the edge's read timeout; no deadline answers 408,
502 or 504.

Timing instrument: the module's name "asyncio" is replaced by a shim
whose wait_for scales each timeout by 0.01, so the base and the change
are timed alike without sleeping; held workers wait on a
threading.Event that teardown releases.
"""
import ast
import asyncio
import logging
import re
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

KEY = "test_key_s465_deadlines"
H = {"X-API-Key": KEY}
ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
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
        self.entered = threading.Event()
        self.exited = threading.Event()
        self.calls = 0

    def wrap(self, fn):
        def held(*a, **k):
            self.calls += 1
            self.entered.set()
            try:
                self.release.wait(10)
                return fn(*a, **k)
            finally:
                self.exited.set()
        return held


@pytest.fixture
def hold():
    h = Hold()
    yield h
    h.release.set()
    if h.calls:
        h.exited.wait(10)


@pytest.fixture
def api(monkeypatch):
    import nous_api_server as S
    monkeypatch.setattr(S, "API_KEYS", {KEY})
    monkeypatch.setattr(S.limiter, "enabled", False)
    monkeypatch.setattr(S, "_S465_ADMIT_WAIT_S", 0.1, raising=False)
    monkeypatch.setattr(S, "_s465_pool", None, raising=False)
    return S


@pytest.fixture
def client(api):
    return TestClient(api.app, raise_server_exceptions=False)


def _shim(monkeypatch, S, scale=SCALE):
    real = asyncio

    class Shim(types.ModuleType):
        def __getattr__(self, name):
            return getattr(real, name)

    sh = Shim("s465_asyncio_shim")

    async def wait_for(aw, timeout):
        return await real.wait_for(
            aw, None if timeout is None else timeout * scale)

    sh.wait_for = wait_for
    monkeypatch.setattr(S, "asyncio", sh)


def _detail(r):
    d = r.json().get("detail")
    return d if isinstance(d, dict) else {"_raw": d}


def _timeout_reply(r, code):
    assert r.status_code == 503, (r.status_code, r.text[:200])
    d = _detail(r)
    assert d.get("code") == code
    assert d.get("work_started") is True
    assert re.fullmatch(r"[0-9a-f]{32}", d.get("error_id", ""))
    assert isinstance(d.get("error"), str) and d["error"]
    assert "MarketMonitor" not in r.text
    assert "retry-after" not in {k.lower() for k in r.headers}


def test_d1_compile_overrun_is_503_timeout001(api, client, hold,
                                               monkeypatch):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))
    r = client.post("/v1/compile", headers=H, json={"source": SRC})
    assert hold.entered.is_set()
    _timeout_reply(r, "TIMEOUT001")


def test_d2_verify_overrun_is_503_timeout002(api, client, hold,
                                             monkeypatch):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "parse_nous", hold.wrap(api.parse_nous))
    r = client.post("/v1/verify", headers=H, json={"source": SRC})
    assert hold.entered.is_set()
    _timeout_reply(r, "TIMEOUT002")


def test_d3_run_overrun_is_503_timeout004(api, client, hold, monkeypatch):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))
    r = client.post("/v1/run", headers=H,
                    json={"source": SRC, "mode": "dry-run"})
    assert hold.entered.is_set()
    _timeout_reply(r, "TIMEOUT004")


def test_d4_export_overrun_is_503_timeout003(api, client, hold,
                                             monkeypatch):
    import skill_export
    _shim(monkeypatch, api)
    monkeypatch.setattr(skill_export, "export_skill",
                        hold.wrap(skill_export.export_skill))
    r = client.post("/v1/skill/export", headers=H,
                    json={"source": SRC, "description": "demo",
                          "with_dossier": False})
    assert hold.entered.is_set()
    _timeout_reply(r, "TIMEOUT003")


def test_d5_diff_overrun_is_503_timeout005_dict(api, client, hold,
                                                monkeypatch):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "parse_nous", hold.wrap(api.parse_nous))
    r = client.post("/v1/diff", headers=H,
                    json={"original": SRC, "modified": SRC})
    assert hold.entered.is_set()
    assert isinstance(r.json().get("detail"), dict)
    _timeout_reply(r, "TIMEOUT005")


def test_d6_no_deadline_answers_408_502_or_504():
    tree = ast.parse((ROOT / "nous_api_server.py").read_text("utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
        if name != "HTTPException":
            continue
        for kw in node.keywords:
            if (kw.arg == "status_code" and isinstance(kw.value, ast.Constant)
                    and kw.value.value in (408, 502, 504)):
                found.append((node.lineno, kw.value.value))
    assert found == []


def _busy_setup(api, monkeypatch, hold, client):
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_S465_POOL_SIZE", 1, raising=False)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))
    calls = []
    real_parse = api.parse_nous

    def counted(src):
        calls.append(threading.current_thread().name)
        return real_parse(src)

    monkeypatch.setattr(api, "parse_nous", counted)
    r1 = client.post("/v1/compile", headers=H, json={"source": SRC})
    assert hold.entered.is_set()
    return r1, calls


def test_d7_busy_is_503_with_retry_after_and_never_runs(api, client, hold,
                                                         monkeypatch):
    r1, calls = _busy_setup(api, monkeypatch, hold, client)
    assert r1.status_code == 503
    b = dict(getattr(api, "_S465_BUDGET_S", {}))
    b["verify"] = 300.0
    monkeypatch.setattr(api, "_S465_BUDGET_S", b, raising=False)
    t0 = time.monotonic()
    r2 = client.post("/v1/verify", headers=H, json={"source": SRC})
    elapsed = time.monotonic() - t0
    assert r2.status_code == 503, (r2.status_code, r2.text[:200])
    assert elapsed < 1.5, elapsed
    d = _detail(r2)
    assert d.get("code") == "BUSY002"
    assert d.get("work_started") is False
    assert re.fullmatch(r"[0-9a-f]{32}", d.get("error_id", ""))
    assert r2.headers.get("retry-after") == "5"
    assert calls == []


def test_d8_slot_freed_when_thread_ends(api, client, hold, monkeypatch):
    r1, calls = _busy_setup(api, monkeypatch, hold, client)
    monkeypatch.setattr(api, "_S465_ADMIT_WAIT_S", 2.0, raising=False)
    hold.release.set()
    assert hold.exited.wait(10)
    r2 = client.post("/v1/verify", headers=H, json={"source": SRC})
    assert r2.status_code == 200, (r2.status_code, r2.text[:200])


def _anchor_counted(monkeypatch):
    import rekor_anchor
    seen = []

    def fake(*a, **k):
        seen.append(1)
        raise rekor_anchor.RekorUnavailable("s465 probe: no network")

    monkeypatch.setattr(rekor_anchor, "anchor_manifest_to_rekor", fake)
    return seen


def _export_budget(api, monkeypatch, seconds):
    b = dict(getattr(api, "_S465_BUDGET_S", {}))
    b["skill_export"] = seconds
    monkeypatch.setattr(api, "_S465_BUDGET_S", b, raising=False)


def test_d10_rekor_gate_refuses_before_network(api, client, monkeypatch):
    seen = _anchor_counted(monkeypatch)
    _export_budget(api, monkeypatch, 30.0)
    r = client.post("/v1/skill/export", headers=H,
                    json={"source": SRC, "description": "demo",
                          "with_dossier": True, "anchor": "rekor"})
    assert seen == []
    assert r.status_code == 503, (r.status_code, r.text[:200])
    d = _detail(r)
    assert d.get("code") == "REKOR_DEADLINE"
    assert d.get("work_started") is True
    assert re.fullmatch(r"[0-9a-f]{32}", d.get("error_id", ""))


def test_d11_rekor_gate_control_calls_the_anchor(api, client, monkeypatch):
    seen = _anchor_counted(monkeypatch)
    _export_budget(api, monkeypatch, 50.0)
    r = client.post("/v1/skill/export", headers=H,
                    json={"source": SRC, "description": "demo",
                          "with_dossier": True, "anchor": "rekor"})
    assert seen == [1]
    assert r.status_code == 503
    assert _detail(r).get("code") == "REKOR_UNAVAILABLE"


def test_d12_the_gate_alone():
    import dossier_spec
    gate = dossier_spec._s465_rekor_gate
    with pytest.raises(dossier_spec.AnchorDeadlineError):
        gate(time.monotonic() + 39.0)
    gate(time.monotonic() + 41.0)
    gate(None)
    assert issubclass(dossier_spec.AnchorDeadlineError,
                      dossier_spec.DossierSpecError)


def test_d13_budgets_stay_under_the_edge():
    import nous_api_server as S
    b = S._S465_BUDGET_S
    assert b["run"] == b["skill_export"] == 50.0
    assert b["compile"] == b["verify"] == b["diff"] == 30.0
    for route, seconds in b.items():
        assert (seconds + S._S465_ADMIT_WAIT_S + 5.0
                < S._S465_EDGE_READ_TIMEOUT_S), route


def test_d14_one_warning_line_no_traceback(api, client, hold, monkeypatch,
                                           caplog):
    caplog.set_level(logging.INFO)
    _shim(monkeypatch, api)
    monkeypatch.setattr(api, "_compile_pipeline",
                        hold.wrap(api._compile_pipeline))
    r = client.post("/v1/compile", headers=H, json={"source": SRC})
    d = _detail(r)
    errs = [x for x in caplog.records if x.levelno >= logging.ERROR]
    warns = [x for x in caplog.records if x.levelno == logging.WARNING]
    assert errs == []
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "TIMEOUT001" in msg and d.get("error_id", "@") in msg
    assert NL not in msg and "Traceback" not in msg
    assert "MarketMonitor" not in msg and warns[0].exc_info is None


def test_d17_the_export_doc_names_503():
    t = (ROOT / "docs" / "SKILL_EXPORT.md").read_text("utf-8")
    assert "408" not in t
    for token in ("503 Service Unavailable", "TIMEOUT003", "BUSY003",
                  "REKOR_DEADLINE", "Retry-After"):
        assert token in t, token
