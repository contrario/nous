"""
NOUS Session 407 -- FG-S406-B: a route of the API server never calls a
paid tier.

Before S407, /v1/chat, /v1/chat/stream and the webhook chat path admitted
a caller without a key, and each walked the runtime's tier list,
skipping only the tiers without a key. When the free tiers failed, the
walk reached the paid tier, and no spend check ran on that path.

Rule: every tier the server calls comes from _public_tiers(), which keeps
the tiers that are available and free. The structural test fails if any
other code in the module names the tier list. The route tests stub the
tiers, make the free ones fail, and require that the paid one is never
called, with and without a valid key.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "nous_api_server.py"
HELPER = "_public_tiers"
NAME = "RUNTIME_TIERS"
GOOD_KEY = "test_key_s407_public_tiers"

needs_api = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None,
    reason="needs the server extra",
)


def _refs(tree: ast.AST) -> tuple[list[int], list[int]]:
    """Line numbers naming the tier list, outside and inside the helper."""
    outside: list[int] = []
    inside: list[int] = []

    class _V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _hit(self, lineno: int) -> None:
            (inside if HELPER in self.stack else outside).append(lineno)

        def visit_FunctionDef(self, node: Any) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == NAME:
                self._hit(node.lineno)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == NAME:
                self._hit(node.lineno)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for alias in node.names:
                if alias.name == NAME:
                    self._hit(node.lineno)

        def visit_Constant(self, node: ast.Constant) -> None:
            if node.value == NAME:
                self._hit(node.lineno)

    _V().visit(tree)
    return outside, inside


def test_engine_sees_a_reference_outside_the_helper() -> None:
    src = (
        "from nous_runtime import RUNTIME_TIERS\n"
        "import nous_runtime\n"
        "def f():\n"
        "    for t in RUNTIME_TIERS:\n"
        "        pass\n"
        "    return getattr(nous_runtime, 'RUNTIME_TIERS'),"
        " nous_runtime.RUNTIME_TIERS\n"
    )
    outside, inside = _refs(ast.parse(src))
    assert outside == [1, 4, 6, 6]
    assert inside == []


def test_engine_files_the_helper_as_inside() -> None:
    src = (
        "def _public_tiers():\n"
        "    from nous_runtime import RUNTIME_TIERS\n"
        "    return [t for t in RUNTIME_TIERS if t.available]\n"
    )
    outside, inside = _refs(ast.parse(src))
    assert outside == []
    assert inside == [2, 3]


def test_server_names_the_tier_list_only_in_the_helper() -> None:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    helpers = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == HELPER
    ]
    assert len(helpers) == 1
    outside, inside = _refs(tree)
    assert outside == []
    assert len(inside) >= 1


class FakeTier:
    def __init__(self, name: str, free: bool, ok: bool,
                 available: bool = True) -> None:
        self.name = name
        self.model = name
        self.temperature = 0.0
        self.available = available
        self.is_free = free
        self.ok = ok
        self.calls = 0

    def _done(self) -> dict[str, Any]:
        return {
            "success": True, "text": "reply from " + self.name,
            "cost": 0.0, "tier": self.name, "tokens_in": 1,
            "tokens_out": 1, "elapsed_ms": 1.0,
        }

    async def call(self, system_prompt: str,
                   user_prompt: str) -> dict[str, Any]:
        self.calls += 1
        if self.ok:
            return self._done()
        return {"success": False, "error": "stub failure"}

    async def stream_call(self, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.ok:
            yield ("token", "reply from " + self.name)
            yield ("done", self._done())
        else:
            yield ("error", {"error": "stub failure"})


def _install(monkeypatch: pytest.MonkeyPatch,
             tiers: list[FakeTier]) -> Any:
    import nous_runtime
    import nous_api_server as srv

    async def _no_search(_message: str) -> str:
        return ""

    monkeypatch.setattr(nous_runtime, NAME, tiers)
    monkeypatch.setattr(srv, "_superbrain_search", _no_search)
    monkeypatch.setattr(srv, "_chat_sessions", {})
    srv.limiter.reset()
    return srv


@pytest.fixture
def failing(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[FakeTier]]:
    tiers = [
        FakeTier("FreeA", free=True, ok=False),
        FakeTier("FreeB", free=True, ok=False),
        FakeTier("Paid", free=False, ok=True),
    ]
    return _install(monkeypatch, tiers), tiers


@needs_api
def test_public_tiers_keeps_only_available_free(
        monkeypatch: pytest.MonkeyPatch) -> None:
    tiers = [
        FakeTier("FreeA", free=True, ok=True),
        FakeTier("FreeNoKey", free=True, ok=True, available=False),
        FakeTier("Paid", free=False, ok=True),
    ]
    srv = _install(monkeypatch, tiers)
    assert [t.name for t in srv._public_tiers()] == ["FreeA"]


@needs_api
def test_chat_never_reaches_the_paid_tier(failing: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tiers = failing
    resp = TestClient(srv.app).post("/v1/chat", json={"message": "hello"})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "CHAT003"
    assert tiers[0].calls >= 1 and tiers[1].calls >= 1
    assert tiers[2].calls == 0


@needs_api
def test_chat_with_a_valid_key_never_reaches_the_paid_tier(
        failing: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    srv, tiers = failing
    monkeypatch.setattr(srv, "API_KEYS", {GOOD_KEY})
    resp = TestClient(srv.app).post(
        "/v1/chat", json={"message": "hello"},
        headers={"X-API-Key": GOOD_KEY},
    )
    assert resp.status_code == 503
    assert tiers[2].calls == 0


@needs_api
def test_chat_stream_never_reaches_the_paid_tier(failing: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tiers = failing
    resp = TestClient(srv.app).post(
        "/v1/chat/stream", json={"message": "hello"},
    )
    assert resp.status_code == 200
    assert "CHAT003" in resp.text
    assert tiers[0].calls >= 1 and tiers[1].calls >= 1
    assert tiers[2].calls == 0


@needs_api
def test_webhook_chat_never_reaches_the_paid_tier(failing: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tiers = failing
    resp = TestClient(srv.app).post(
        "/v1/webhook/generic", json={"message": "hello"},
    )
    assert resp.status_code == 200
    assert resp.json().get("error") == "All LLM tiers failed"
    assert tiers[0].calls >= 1 and tiers[1].calls >= 1
    assert tiers[2].calls == 0


@needs_api
def test_chat_still_answers_from_a_free_tier(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    tiers = [
        FakeTier("FreeA", free=True, ok=True),
        FakeTier("Paid", free=False, ok=True),
    ]
    srv = _install(monkeypatch, tiers)
    resp = TestClient(srv.app).post("/v1/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "reply from FreeA"
    assert tiers[1].calls == 0
