"""
NOUS -- S407-D: the webhook callback is removed.

Before, the generic webhook channels (generic, n8n, zapier, make) admitted
a caller without a key, took callback_url from the payload, and posted the
chat result to it with no check of scheme or host; the error text of that
post went back to the caller. It was the only caller-named outbound URL in
nous_api_server.py, no doc, page or test named it, and the nginx access
logs read on Server A on 2026-10-19 held no request to /v1/webhook.

Rule, as ruled in S408: a payload that carries the key callback_url, even
empty or null, answers 400 with code WH002 before any model call, with no
outbound request and no session, on all four channels and with or without
a valid key. A payload without it still answers 200 from a free tier.
The structural test fails if _handle_generic makes an outbound call again;
its engine is driven first on a source that has the shape it looks for.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "nous_api_server.py"
GOOD_KEY = "test_key_s407d_callback_removed"
CHANNELS = ("generic", "n8n", "zapier", "make")
CALLBACKS = ("http://127.0.0.1:9977/agents/run", "", None)
SENDS = ("post", "put", "patch", "delete", "request", "stream", "send")
CLIENTS = ("AsyncClient", "Client")
LIBS = ("httpx", "requests", "aiohttp", "urllib")

needs_api = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None,
    reason="needs the server extra",
)


def _outbound_calls(tree: ast.AST, name: str) -> list[str] | None:
    """What in function `name` has the shape of an outbound request: a
    sending method call, an HTTP client, or an HTTP library imported
    inside it. None when the function is absent. A dict's get is not a
    request and is not counted."""
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            found = []
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in SENDS):
                    found.append("call:" + sub.func.attr)
                elif (isinstance(sub, ast.Attribute)
                        and sub.attr in CLIENTS):
                    found.append("client:" + sub.attr)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    mods = ([a.name for a in sub.names]
                            if isinstance(sub, ast.Import)
                            else [sub.module or ""])
                    for m in mods:
                        if m.split(".")[0] in LIBS:
                            found.append("import:" + m)
            return found
    return None


def test_engine_finds_an_outbound_call() -> None:
    old = (
        "async def _handle_generic(payload):\n"
        "    callback_url = payload.get('callback_url')\n"
        "    async with httpx.AsyncClient() as client:\n"
        "        await client.post(callback_url, json={})\n"
    )
    old_import = (
        "async def _handle_generic(payload):\n"
        "    import httpx as _hx\n"
        "    async with _hx.AsyncClient() as client:\n"
        "        await client.post(payload.get('callback_url'), json={})\n"
    )
    new = (
        "async def _handle_generic(payload):\n"
        "    message = payload.get('message', '')\n"
        "    return {'reply': message}\n"
    )
    assert _outbound_calls(ast.parse(old), "_handle_generic") == [
        "client:AsyncClient", "call:post"]
    assert _outbound_calls(ast.parse(old_import), "_handle_generic") == [
        "import:httpx", "client:AsyncClient", "call:post"]
    assert _outbound_calls(ast.parse(new), "_handle_generic") == []
    assert _outbound_calls(ast.parse(new), "absent") is None


def test_handle_generic_makes_no_outbound_call() -> None:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    assert _outbound_calls(tree, "_handle_generic") == []


class FakeTier:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = name
        self.temperature = 0.0
        self.available = True
        self.is_free = True
        self.calls = 0

    async def call(self, system_prompt: str,
                   user_prompt: str) -> dict[str, Any]:
        self.calls += 1
        return {
            "success": True, "text": "reply from " + self.name,
            "cost": 0.0, "tier": self.name, "tokens_in": 1,
            "tokens_out": 1, "elapsed_ms": 1.0,
        }


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, FakeTier,
                                                       list[Any]]:
    import httpx
    import nous_runtime
    import nous_api_server as srv

    tier = FakeTier("FreeA")
    posts: list[Any] = []

    async def _no_search(_message: str) -> str:
        return ""

    async def _record_post(self: Any, url: Any, *args: Any,
                           **kwargs: Any) -> Any:
        posts.append(str(url))
        raise httpx.ConnectError("outbound request in a test")

    monkeypatch.setattr(nous_runtime, "RUNTIME_TIERS", [tier])
    monkeypatch.setattr(srv, "_superbrain_search", _no_search)
    monkeypatch.setattr(srv, "_chat_sessions", {})
    monkeypatch.setattr(httpx.AsyncClient, "post", _record_post)
    srv.limiter.reset()
    return srv, tier, posts


def _assert_refused(resp: Any, tier: FakeTier, posts: list[Any],
                    srv: Any) -> None:
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "WH002"
    assert tier.calls == 0
    assert posts == []
    assert srv._chat_sessions == {}


@needs_api
@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("callback", CALLBACKS)
def test_callback_url_is_refused_before_any_model_call(
        server: Any, channel: str, callback: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    resp = TestClient(srv.app).post(
        "/v1/webhook/" + channel,
        json={"message": "hello", "callback_url": callback},
    )
    _assert_refused(resp, tier, posts, srv)


@needs_api
def test_callback_url_without_a_message_is_refused(server: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    resp = TestClient(srv.app).post(
        "/v1/webhook/generic",
        json={"callback_url": "http://127.0.0.1:9977/agents/run"},
    )
    _assert_refused(resp, tier, posts, srv)


@needs_api
def test_callback_url_with_a_valid_key_is_still_refused(
        server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    monkeypatch.setattr(srv, "API_KEYS", {GOOD_KEY})
    resp = TestClient(srv.app).post(
        "/v1/webhook/generic",
        json={"message": "hello",
              "callback_url": "http://127.0.0.1:9977/agents/run"},
        headers={"X-API-Key": GOOD_KEY},
    )
    _assert_refused(resp, tier, posts, srv)


@needs_api
@pytest.mark.parametrize("channel", CHANNELS)
def test_without_callback_url_the_channel_answers_from_a_free_tier(
        server: Any, channel: str) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    resp = TestClient(srv.app).post("/v1/webhook/" + channel,
                                    json={"message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "reply from FreeA"
    assert "callback_sent" not in body
    assert "callback_error" not in body
    assert tier.calls >= 1
    assert posts == []
