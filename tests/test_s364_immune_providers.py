"""
NOUS Session 364 -- E5: immune_engine's default LLM caller no longer
tries claude-3-haiku-20240307, which Anthropic retired on 2026-04-20
(docs/ONE_PRICE_SOURCE_DESIGN.md sections 15.5 and 16.3).

Before S364 the caller's third provider posted the retired id to
Anthropic. The response carried no text, so the caller logged a warning
and returned an empty string. RUNTIME_TIERS dropped the same id in 5.81.0
(K2); the engine kept it. mistral-small-latest has no pricing entry and
no pin (K3 open) and is the one disclosed exception.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

import immune_engine
from pricing import lifecycle_status, load_pricing

DISCLOSED_UNPRICED = {"mistral-small-latest"}
PROVIDER_KEYS = ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "ANTHROPIC_API_KEY")


class _Response:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


def _recording_client(body: dict[str, Any]) -> tuple[type, list[tuple[str, dict[str, Any]]]]:
    posts: list[tuple[str, dict[str, Any]]] = []

    class _Client:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _Response:
            posts.append((url, json))
            return _Response(body)

    return _Client, posts


def _call() -> str:
    engine = immune_engine.ImmuneEngine(object())
    return asyncio.run(engine._default_llm_caller("Soul", "prompt"))


@pytest.fixture
def no_keys(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_anthropic_key_alone_makes_no_call(no_keys: pytest.MonkeyPatch) -> None:
    client, posts = _recording_client({"content": [{"text": "antibody code"}]})
    no_keys.setattr(httpx, "AsyncClient", client)
    no_keys.setenv("ANTHROPIC_API_KEY", "test-key")
    out = _call()
    assert posts == [], "the caller posted to " + repr([u for u, _ in posts])
    assert out == ""


def test_provider_models_are_priceable_or_disclosed() -> None:
    providers = getattr(immune_engine, "IMMUNE_DEFAULT_PROVIDERS", None)
    assert providers, "immune_engine.IMMUNE_DEFAULT_PROVIDERS is missing or empty"
    table = load_pricing()
    bad: list[tuple[str, str]] = []
    for _env_key, url, model in providers:
        assert "anthropic" not in url, "provider list still names Anthropic: " + url
        if model in DISCLOSED_UNPRICED:
            continue
        try:
            _canonical, entry = table.resolve(model)
        except KeyError as exc:
            bad.append((model, str(exc)))
            continue
        state, message = lifecycle_status(entry)
        if state != "ok":
            bad.append((model, message))
    assert bad == [], "unpriceable or removed provider models: " + repr(bad)


def test_deepseek_leg_is_unchanged(no_keys: pytest.MonkeyPatch) -> None:
    client, posts = _recording_client({"choices": [{"message": {"content": "fallback code"}}]})
    no_keys.setattr(httpx, "AsyncClient", client)
    no_keys.setenv("DEEPSEEK_API_KEY", "test-key")
    out = _call()
    assert out == "fallback code"
    assert len(posts) == 1
    url, payload = posts[0]
    assert url == "https://api.deepseek.com/v1/chat/completions"
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["max_tokens"] == 300
    assert payload["thinking"] == {"type": "disabled"}
