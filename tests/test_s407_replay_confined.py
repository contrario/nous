"""
NOUS Session 407 -- a replay log name from a caller stays inside
NOUS_REPLAY_DIR.

Before S407, /v1/replay/summary, /v1/replay/events, /v1/replay/verify,
/v1/governance/interventions and /v1/governance/stats opened the log
path a caller passed, wherever it pointed, and /v1/chat passed its
replay_log to EventStore.open, which in record mode creates the parent
directories and appends. Only /v1/replay/diff resolved its names through
_resolve_replay_log.

Rule: every route that takes a log name resolves it through
_resolve_replay_log (to read) or _resolve_replay_log_for_write (to
record), and a chat replay mode needs a valid key.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "nous_api_server.py"
GOOD_KEY = "test_key_s407_replay"
READ_ROUTES = [
    "/v1/replay/summary",
    "/v1/replay/events",
    "/v1/replay/verify",
    "/v1/governance/interventions",
    "/v1/governance/stats",
]

needs_api = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None,
    reason="needs the server extra",
)


def _tree() -> ast.Module:
    return ast.parse(SERVER.read_text(encoding="utf-8"))


def _called_names(node: ast.AST) -> set[str]:
    return {
        n.func.id for n in ast.walk(node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def test_every_route_with_a_log_parameter_resolves_it() -> None:
    fns = [
        n for n in ast.walk(_tree())
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(a.arg == "log" for a in n.args.args)
    ]
    assert len(fns) == 5
    for fn in fns:
        names = _called_names(fn)
        assert "_resolve_replay_log" in names, fn.name
        assert "_P" not in names, fn.name


def test_chat_resolves_its_replay_log_and_needs_a_write_key() -> None:
    chats = [
        n for n in ast.walk(_tree())
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "chat"
    ]
    assert len(chats) == 1
    names = _called_names(chats[0])
    assert {"_resolve_replay_log", "_resolve_replay_log_for_write",
            "require_write_api_key"} <= names
    opens = [
        n for n in ast.walk(chats[0])
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "open" and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "EventStore"
    ]
    assert len(opens) == 1
    first = opens[0].args[0]
    assert isinstance(first, ast.Name) and first.id == "_replay_path"


def _write_log(path: Path) -> None:
    from replay_store import EventStore
    store = EventStore.open(path, mode="record")
    store.append(soul="A", cycle=0, kind="note", data={"x": 1})
    store.close()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    import nous_api_server as srv
    replays = tmp_path / "replays"
    replays.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(srv, "NOUS_REPLAY_DIR", replays)
    monkeypatch.setattr(srv, "_chat_sessions", {})
    srv.limiter.reset()
    _write_log(replays / "inside.jsonl")
    _write_log(tmp_path / "outside.jsonl")
    _write_log(replays / ".hidden.jsonl")
    (replays / "link.jsonl").symlink_to(tmp_path / "outside.jsonl")
    return srv, replays, tmp_path


def _client(srv: Any) -> Any:
    from fastapi.testclient import TestClient
    return TestClient(srv.app)


@needs_api
@pytest.mark.parametrize("route", READ_ROUTES)
def test_read_route_serves_a_log_inside_the_dir(env: Any,
                                                route: str) -> None:
    srv, _replays, _tmp = env
    resp = _client(srv).get(route, params={"log": "inside.jsonl"})
    assert resp.status_code == 200, resp.text


@needs_api
@pytest.mark.parametrize("route", READ_ROUTES)
@pytest.mark.parametrize("kind", ["absolute", "parent", "subdir", "dot",
                                  "symlink"])
def test_read_route_refuses_a_log_outside_the_dir(env: Any, route: str,
                                                  kind: str) -> None:
    srv, _replays, tmp = env
    name = {
        "absolute": str(tmp / "outside.jsonl"),
        "parent": "../outside.jsonl",
        "subdir": "sub/inside.jsonl",
        "dot": ".hidden.jsonl",
        "symlink": "link.jsonl",
    }[kind]
    resp = _client(srv).get(route, params={"log": name})
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "REP006"


class FreeTier:
    name = "FreeOK"
    model = "free-ok"
    temperature = 0.0
    available = True
    is_free = True

    async def call(self, system_prompt: str,
                   user_prompt: str) -> dict[str, Any]:
        return {
            "success": True, "text": "ok", "cost": 0.0, "tier": self.name,
            "tokens_in": 1, "tokens_out": 1, "elapsed_ms": 1.0,
        }


def _chat_setup(env: Any, monkeypatch: pytest.MonkeyPatch,
                keys: set[str]) -> Any:
    import nous_runtime
    srv = env[0]

    async def _no_search(_message: str) -> str:
        return ""

    monkeypatch.setattr(nous_runtime, "RUNTIME_TIERS", [FreeTier()])
    monkeypatch.setattr(srv, "_superbrain_search", _no_search)
    monkeypatch.setattr(srv, "API_KEYS", set(keys))
    return _client(srv)


def _record(client: Any, name: str, key: str | None = None) -> Any:
    headers = {"X-API-Key": key} if key else {}
    return client.post("/v1/chat", headers=headers, json={
        "message": "hello", "replay_mode": "record", "replay_log": name,
    })


@needs_api
def test_chat_replay_is_refused_without_configured_keys(
        env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _chat_setup(env, monkeypatch, set())
    resp = _record(client, "r.jsonl")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "AUTH002"
    assert not (env[1] / "r.jsonl").exists()
    assert not (Path.cwd() / "r.jsonl").exists()


@needs_api
def test_chat_replay_is_refused_without_a_key(
        env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _chat_setup(env, monkeypatch, {GOOD_KEY})
    resp = _record(client, "r.jsonl")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "AUTH003"
    assert not (env[1] / "r.jsonl").exists()
    assert not (Path.cwd() / "r.jsonl").exists()


@needs_api
@pytest.mark.parametrize("kind", ["absolute", "parent", "subdir", "dot",
                                  "not_jsonl"])
def test_chat_record_refuses_a_name_outside_the_dir(
        env: Any, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    _srv, _replays, tmp = env
    client = _chat_setup(env, monkeypatch, {GOOD_KEY})
    name = {
        "absolute": str(tmp / "escape.jsonl"),
        "parent": "../escape.jsonl",
        "subdir": "sub/escape.jsonl",
        "dot": ".escape.jsonl",
        "not_jsonl": "escape.txt",
    }[kind]
    resp = _record(client, name, GOOD_KEY)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "REP006"
    written = [p for p in tmp.rglob("*escape*")]
    assert written == []


@needs_api
def test_chat_records_inside_the_dir_with_a_key(
        env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _chat_setup(env, monkeypatch, {GOOD_KEY})
    resp = _record(client, "ok.jsonl", GOOD_KEY)
    assert resp.status_code == 200, resp.text
    target = env[1] / "ok.jsonl"
    assert target.is_file() and target.stat().st_size > 0
    assert not (Path.cwd() / "ok.jsonl").exists()
