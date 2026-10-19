"""
NOUS -- S407-C: the telegram channel of /v1/webhook is retired.

Before, /v1/webhook/telegram skipped the key check, kept a session named
tg_<chat id> in the one session store that /v1/chat also serves, called
the model, and sent the reply through the Bot API with the token
TELEGRAM_BOT_TOKEN. In the logs read on Server A on 2026-10-19 no request
reached that route; Telegram updates go to nous-bot, which polls on its
own token and calls no NOUS route.

Rule: no webhook channel skips require_api_key, and telegram answers as an
unknown channel, with no model call, no outbound request and no session.
The structural tests fail if the server names the handler, its world map,
the token or the Bot API again, or if the key check in the webhook route
sits under a condition; each engine is driven first on a source that has
the shape it looks for. The route tests send a Telegram update with the
token set, so that the old handler would have called the model and sent.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "nous_api_server.py"
GOOD_KEY = "test_key_s407c_telegram_retired"
FORBIDDEN = (
    "_handle_telegram",
    "_tg_worlds",
    "TELEGRAM_BOT_TOKEN",
    "api.telegram.org",
)

needs_api = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None,
    reason="needs the server extra",
)


def _named(text: str) -> list[str]:
    return [name for name in FORBIDDEN if name in text]


def _key_check_is_unconditional(tree: ast.AST) -> bool:
    """True when the webhook route calls require_api_key as a statement
    of its own body, not under an if, a loop or a try."""
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "webhook"):
            for stmt in node.body:
                if (isinstance(stmt, ast.Expr)
                        and isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Name)
                        and stmt.value.func.id == "require_api_key"):
                    return True
            return False
    return False


def test_engine_finds_every_forbidden_name() -> None:
    src = (
        "_tg_worlds = {}\n"
        "async def _handle_telegram(payload):\n"
        "    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')\n"
        "    url = f'https://api.telegram.org/bot{token}/sendMessage'\n"
    )
    assert _named(src) == list(FORBIDDEN)


def test_engine_tells_a_conditional_key_check_apart() -> None:
    old = (
        "async def webhook(request, channel, x_api_key=None):\n"
        "    if channel not in ('telegram',):\n"
        "        require_api_key(x_api_key)\n"
    )
    new = (
        "async def webhook(request, channel, x_api_key=None):\n"
        "    require_api_key(x_api_key)\n"
    )
    assert _key_check_is_unconditional(ast.parse(old)) is False
    assert _key_check_is_unconditional(ast.parse(new)) is True
    assert _key_check_is_unconditional(ast.parse("def other():\n"
                                                 "    pass\n")) is False


def test_server_names_no_telegram_handler_token_or_bot_api() -> None:
    assert _named(SERVER.read_text(encoding="utf-8")) == []


def test_server_webhook_checks_the_key_for_every_channel() -> None:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    assert _key_check_is_unconditional(tree) is True


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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token-s407c")
    srv.limiter.reset()
    return srv, tier, posts


def _update(text: str) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 4242, "type": "private"},
            "from": {"id": 4242, "first_name": "Test"},
            "text": text,
        },
    }


def _assert_unknown(body: dict[str, Any]) -> None:
    assert body["received"] is True
    assert body["channel"] == "telegram"
    assert body["note"].startswith("Unknown channel.")
    assert "telegram" not in body["note"]


@needs_api
@pytest.mark.parametrize("text", [
    "hello", "/start", "/help", "/status", "/clear",
    "/world customer_service",
])
def test_telegram_update_answers_as_an_unknown_channel(
        server: Any, text: str) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    resp = TestClient(srv.app).post("/v1/webhook/telegram",
                                    json=_update(text))
    assert resp.status_code == 200
    _assert_unknown(resp.json())
    assert tier.calls == 0
    assert posts == []
    assert srv._chat_sessions == {}


@needs_api
def test_telegram_with_an_invalid_key_is_refused(
        server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    monkeypatch.setattr(srv, "API_KEYS", {GOOD_KEY})
    resp = TestClient(srv.app).post(
        "/v1/webhook/telegram", json=_update("hello"),
        headers={"X-API-Key": "not-the-key"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "AUTH001"
    assert tier.calls == 0
    assert posts == []


@needs_api
def test_telegram_with_a_valid_key_still_answers_as_unknown(
        server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    monkeypatch.setattr(srv, "API_KEYS", {GOOD_KEY})
    resp = TestClient(srv.app).post(
        "/v1/webhook/telegram", json=_update("hello"),
        headers={"X-API-Key": GOOD_KEY},
    )
    assert resp.status_code == 200
    _assert_unknown(resp.json())
    assert tier.calls == 0
    assert posts == []
    assert srv._chat_sessions == {}


@needs_api
def test_generic_channel_still_answers_from_a_free_tier(
        server: Any) -> None:
    from fastapi.testclient import TestClient
    srv, tier, posts = server
    resp = TestClient(srv.app).post("/v1/webhook/generic",
                                    json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "reply from FreeA"
    assert tier.calls >= 1
    assert posts == []
