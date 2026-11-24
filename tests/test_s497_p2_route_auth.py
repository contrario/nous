"""S497 phase 2: routes with outbound calls or other hosts behind them
need the key; keyless chat stays live on free tiers, without superbrain.

/v1/skill/export (Rekor, TSA), /v1/superbrain/* (a tunnel to another
host) and /v1/webhook/{channel} call require_write_api_key. Chat and
chat/stream query superbrain only for a caller with a valid key. A
table holds every route's class; a route not in it fails the test."""
import ast
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("slowapi")

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KEY = "test_key_s497_p2"
H = {"X-API-Key": KEY}

PUBLIC = {"GET /v1/health", "GET /v1/templates", "GET /v1/templates/{name}",
          "POST /v1/verify-conformance", "POST /v1/verify-dossier"}
KEYED = {"PUT /v1/templates/{name}", "POST /v1/skill/export",
         "GET /v1/superbrain/health", "GET /v1/superbrain/domains",
         "POST /v1/superbrain/search", "POST /v1/webhook/{channel}"}
SOFT = {"POST /v1/chat", "POST /v1/chat/stream", "POST /v1/compile",
        "POST /v1/diff", "GET /v1/governance/interventions",
        "POST /v1/governance/lint", "GET /v1/governance/policies",
        "POST /v1/governance/policies/preview",
        "POST /v1/governance/simulate", "GET /v1/governance/stats",
        "POST /v1/replay/diff", "GET /v1/replay/events",
        "GET /v1/replay/list", "GET /v1/replay/summary",
        "GET /v1/replay/verify", "POST /v1/run", "POST /v1/verify"}


class FakeTier:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = name
        self.temperature = 0.0
        self.available = True
        self.is_free = True
        self.calls = 0

    def _done(self) -> dict[str, Any]:
        return {"success": True, "text": "reply from " + self.name,
                "cost": 0.0, "tier": self.name, "tokens_in": 1,
                "tokens_out": 1, "elapsed_ms": 1.0}

    async def call(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        self.calls += 1
        return self._done()

    async def stream_call(self, system_prompt: str, user_prompt: str):
        self.calls += 1
        yield ("token", "reply from " + self.name)
        yield ("done", self._done())


@pytest.fixture
def srv(monkeypatch):
    import httpx
    import nous_runtime
    import nous_api_server as s
    tier = FakeTier("FreeA")
    searches: list[str] = []
    out: list[str] = []

    async def _search(message: str, *a: Any, **k: Any) -> str:
        searches.append(message)
        return ""

    async def _get(self: Any, url: Any, *a: Any, **k: Any) -> Any:
        out.append("GET " + str(url))
        raise httpx.ConnectError("outbound request in a test")

    async def _post(self: Any, url: Any, *a: Any, **k: Any) -> Any:
        out.append("POST " + str(url))
        raise httpx.ConnectError("outbound request in a test")

    monkeypatch.setattr(nous_runtime, "RUNTIME_TIERS", [tier])
    monkeypatch.setattr(s, "_superbrain_search", _search)
    monkeypatch.setattr(s, "_chat_sessions", {})
    monkeypatch.setattr(s, "API_KEYS", {KEY})
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    monkeypatch.setattr(s.limiter, "enabled", False)

    def _force_sense() -> None:
        monkeypatch.setattr(s, "_has_superbrain_sense", lambda cfg: True)
    monkeypatch.setattr(s, "_s497_force_sense", _force_sense, raising=False)
    for k, v in (("_s497_tier", tier), ("_s497_searches", searches), ("_s497_out", out)):
        monkeypatch.setattr(s, k, v, raising=False)
    return s


def _client(s: Any) -> TestClient:
    return TestClient(s.app, raise_server_exceptions=False)


def _code(r: Any) -> str:
    return r.json()["detail"]["code"]


def test_t1_skill_export_keyless_refused(srv):
    r = _client(srv).post("/v1/skill/export", json={
        "source": "x", "description": "d", "with_dossier": False})
    assert r.status_code == 401 and _code(r) == "AUTH003"


def test_t2_skill_export_no_keys_configured(srv, monkeypatch):
    monkeypatch.setattr(srv, "API_KEYS", set())
    r = _client(srv).post("/v1/skill/export", json={
        "source": "x", "description": "d", "with_dossier": False})
    assert r.status_code == 403 and _code(r) == "AUTH002"


def test_t3_superbrain_health_keyless_refused(srv):
    r = _client(srv).get("/v1/superbrain/health")
    assert r.status_code == 401 and _code(r) == "AUTH003"
    assert srv._s497_out == []


def test_t4_superbrain_search_keyless_refused(srv):
    r = _client(srv).post("/v1/superbrain/search", json={"query": "q"})
    assert r.status_code == 401 and _code(r) == "AUTH003"
    assert srv._s497_out == []


def test_t5_webhook_keyless_refused(srv):
    r = _client(srv).post("/v1/webhook/generic", json={"message": "hello"})
    assert r.status_code == 401 and _code(r) == "AUTH003"
    assert srv._s497_tier.calls == 0


def _chat(s: Any, path: str, mode: str, headers: Any = None) -> Any:
    s._s497_force_sense()
    return _client(s).post(path, headers=headers or {}, json={
        "message": "S497_SB_PROBE", "world": "customer_service",
        "soul": "Triage", "mode": mode})


def test_t6_chat_keyless_no_superbrain(srv):
    r = _chat(srv, "/v1/chat", "dry-run")
    assert r.status_code == 200
    assert srv._s497_searches == []


def test_t7_chat_stream_keyless_no_superbrain(srv):
    r = _chat(srv, "/v1/chat/stream", "dry-run")
    assert r.status_code == 200
    assert srv._s497_searches == []


def test_t8_chat_with_key_queries_superbrain(srv):
    r = _chat(srv, "/v1/chat", "dry-run", headers=H)
    assert r.status_code == 200
    assert srv._s497_searches == ["S497_SB_PROBE"]


def test_t9_every_route_has_a_class():
    import nous_api_server as s
    src = (ROOT / "nous_api_server.py").read_text(encoding="utf-8")
    fns = {n.name: n for n in ast.walk(ast.parse(src))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    have = {}
    for r in s.app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods:
                have["%s %s" % (m, r.path)] = r.endpoint.__name__
    table = {**{k: "public" for k in PUBLIC}, **{k: "key" for k in KEYED},
             **{k: "soft" for k in SOFT}}
    assert len(table) == len(PUBLIC) + len(KEYED) + len(SOFT) == 28
    assert set(have) == set(table)

    def calls(node, name):
        return [c for c in ast.walk(node) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name) and c.func.id == name]

    def top(fn, name):
        return [st for st in fn.body if isinstance(st, ast.Expr)
                and isinstance(st.value, ast.Call)
                and isinstance(st.value.func, ast.Name)
                and st.value.func.id == name]

    bad = []
    for k, fname in sorted(have.items()):
        fn = fns[fname]
        cls = table[k]
        if cls == "key":
            ok = bool(top(fn, "require_write_api_key")) and not calls(fn, "require_api_key")
        elif cls == "soft":
            ok = bool(top(fn, "require_api_key"))
        else:
            ok = not calls(fn, "require_api_key") and not calls(fn, "require_write_api_key")
        if not ok:
            bad.append(k)
    assert bad == []


def test_t10_keyless_live_chat_answers_from_a_free_tier(srv):
    r = _chat(srv, "/v1/chat", "live")
    assert r.status_code == 200
    assert "reply from FreeA" in r.text
    assert srv._s497_tier.calls >= 1


def test_t11_no_keys_junk_header_no_superbrain(srv, monkeypatch):
    monkeypatch.setattr(srv, "API_KEYS", set())
    r = _chat(srv, "/v1/chat", "dry-run", headers={"X-API-Key": "junk"})
    assert r.status_code == 200
    assert srv._s497_searches == []
