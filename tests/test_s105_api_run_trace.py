"""S105 -- /v1/run opt-in dry-run signed-trace contract.

In-process TestClient. Dry-run means no LLM/network: the interpreter's
dry-run branch emits synthetic llm_call records at $0 before any httpx
or api_key access, so these tests are hermetic.

# __s105_api_run_trace_tests_v1__
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nous_trace import TraceEnvelope, verify_trace_signature

GOOD_KEY = "test_key_s105"

_PRICED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Ping }\n"
    "}\n"
    "message Ping { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)


@pytest.fixture
def with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "API_KEYS", {GOOD_KEY})


@pytest.fixture
def client() -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def _post(client: TestClient, body: dict) -> dict:
    r = client.post("/v1/run", json=body, headers={"X-API-Key": GOOD_KEY})
    assert r.status_code == 200, r.text
    return r.json()


def test_emit_trace_returns_signed_verifying_trace(
    client: TestClient, with_keys: None
) -> None:
    data = _post(client, {"source": _PRICED, "mode": "dry-run", "emit_trace": True})
    assert data["ok"] is True
    assert data["execution_kind"] == "dry-run"
    assert data["trace"] is not None
    env = TraceEnvelope(**data["trace"])
    assert verify_trace_signature(env) is True
    assert env.world_name == "W"


def test_emit_trace_default_off_shape_unchanged(
    client: TestClient, with_keys: None
) -> None:
    data = _post(client, {"source": _PRICED, "mode": "dry-run"})
    assert data["ok"] is True
    assert data["mode"] == "dry-run"
    assert data["execution_kind"] == "dry-run"
    assert data["trace"] is None


def test_execute_mode_refused_discriminator(
    client: TestClient, with_keys: None
) -> None:
    data = _post(client, {"source": _PRICED, "mode": "execute"})
    assert data["mode"] == "execute"
    assert data["execution_kind"] == "refused"
    assert "trace" not in data


def test_trace_action_labels_bound(
    client: TestClient, with_keys: None
) -> None:
    data = _post(client, {"source": _PRICED, "mode": "dry-run", "emit_trace": True})
    env = TraceEnvelope(**data["trace"])
    actions = [(e.kind, e.action) for e in env.events]
    assert ("message", "Ping") in actions
    assert ("llm_call", None) in actions
