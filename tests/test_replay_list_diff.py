"""Tests for /v1/replay/list and /v1/replay/diff (Session 65 Phase A.1).
# __session65_replay_list_diff_v1__
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from replay_store import GENESIS_HASH, _compute_hash


def _craft_log(path: Path, events: list[dict[str, Any]]) -> None:
    """Write a hand-crafted but cryptographically valid JSONL replay log.

    Each entry: {soul, cycle, kind, timestamp, data, parent_id?}.
    Hash chain is computed via replay_store._compute_hash so EventStore
    iteration verifies clean.
    """
    prev = GENESIS_HASH
    with path.open("w", encoding="utf-8") as fh:
        for i, e in enumerate(events):
            content: dict[str, Any] = {
                "seq_id": i,
                "parent_id": e.get("parent_id", -1),
                "soul": e["soul"],
                "cycle": e["cycle"],
                "kind": e["kind"],
                "timestamp": e["timestamp"],
                "data": e["data"],
                "prev_hash": prev,
            }
            h = _compute_hash(prev, content)
            full = {**content, "hash": h}
            fh.write(json.dumps(full, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
            prev = h


@pytest.fixture
def replay_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "replays"
    d.mkdir()
    import nous_api_server
    monkeypatch.setattr(nous_api_server, "NOUS_REPLAY_DIR", d)
    return d


@pytest.fixture
def client() -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def test_list_empty_dir(client: TestClient, replay_dir: Path) -> None:
    r = client.get("/v1/replay/list")
    assert r.status_code == 200
    body = r.json()
    assert body["logs"] == []
    assert body["replay_dir"] == str(replay_dir.resolve())


def test_list_returns_metadata(client: TestClient, replay_dir: Path) -> None:
    _craft_log(replay_dir / "alpha.jsonl", [
        {"soul": "Watcher", "cycle": 0, "kind": "sense.invoke", "timestamp": 1.0, "data": {"x": 1}},
        {"soul": "Watcher", "cycle": 1, "kind": "sense.result", "timestamp": 2.0, "data": {"y": 2}},
    ])
    r = client.get("/v1/replay/list")
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["name"] == "alpha.jsonl"
    assert log["last_seq_id"] == 1
    assert log["last_kind"] == "sense.result"
    assert len(log["last_hash"]) == 64
    assert log["size_bytes"] > 0


def test_list_skips_non_jsonl(client: TestClient, replay_dir: Path) -> None:
    (replay_dir / "ignored.txt").write_text("noise\n")
    (replay_dir / "ignored.json").write_text("{}\n")
    _craft_log(replay_dir / "real.jsonl", [
        {"soul": "S", "cycle": 0, "kind": "sense.invoke", "timestamp": 1.0, "data": {}},
    ])
    r = client.get("/v1/replay/list")
    names = sorted(log["name"] for log in r.json()["logs"])
    assert names == ["real.jsonl"]


def test_diff_identical(client: TestClient, replay_dir: Path) -> None:
    events = [
        {"soul": "S", "cycle": i, "kind": "sense.invoke", "timestamp": float(i), "data": {"v": i}}
        for i in range(3)
    ]
    _craft_log(replay_dir / "a.jsonl", events)
    shutil.copy(replay_dir / "a.jsonl", replay_dir / "b.jsonl")
    r = client.post("/v1/replay/diff", json={"a": "a.jsonl", "b": "b.jsonl"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "identical", body
    assert body["a_total_events"] == 3
    assert body["b_total_events"] == 3
    assert body["common_prefix_length"] == 3
    assert body["divergence"] is None


def test_diff_truncated_b(client: TestClient, replay_dir: Path) -> None:
    events = [
        {"soul": "S", "cycle": i, "kind": "sense.invoke", "timestamp": float(i), "data": {"v": i}}
        for i in range(3)
    ]
    _craft_log(replay_dir / "a.jsonl", events)
    a_lines = (replay_dir / "a.jsonl").read_text().splitlines()
    (replay_dir / "b.jsonl").write_text("\n".join(a_lines[:2]) + "\n")
    r = client.post("/v1/replay/diff", json={"a": "a.jsonl", "b": "b.jsonl"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "truncated_b", body
    assert body["a_total_events"] == 3
    assert body["b_total_events"] == 2
    assert body["common_prefix_length"] == 2
    assert body["divergence"] is not None
    assert body["divergence"]["a_event"] is not None
    assert body["divergence"]["b_event"] is None


def test_diff_truncated_a(client: TestClient, replay_dir: Path) -> None:
    events = [
        {"soul": "S", "cycle": i, "kind": "sense.invoke", "timestamp": float(i), "data": {"v": i}}
        for i in range(3)
    ]
    _craft_log(replay_dir / "b.jsonl", events)
    b_lines = (replay_dir / "b.jsonl").read_text().splitlines()
    (replay_dir / "a.jsonl").write_text("\n".join(b_lines[:1]) + "\n")
    r = client.post("/v1/replay/diff", json={"a": "a.jsonl", "b": "b.jsonl"})
    body = r.json()
    assert body["status"] == "truncated_a", body
    assert body["a_total_events"] == 1
    assert body["b_total_events"] == 3
    assert body["common_prefix_length"] == 1


def test_diff_divergent(client: TestClient, replay_dir: Path) -> None:
    common_ev = {"soul": "S", "cycle": 0, "kind": "sense.invoke", "timestamp": 1.0, "data": {"v": 0}}
    _craft_log(replay_dir / "a.jsonl", [
        common_ev,
        {"soul": "S", "cycle": 1, "kind": "sense.result", "timestamp": 2.0, "data": {"v": 1}},
    ])
    _craft_log(replay_dir / "b.jsonl", [
        common_ev,
        {"soul": "S", "cycle": 1, "kind": "sense.result", "timestamp": 3.0, "data": {"v": 1}},
    ])
    r = client.post("/v1/replay/diff", json={"a": "a.jsonl", "b": "b.jsonl"})
    body = r.json()
    assert body["status"] == "divergent", body
    assert body["common_prefix_length"] == 1
    assert body["divergence"] is not None
    assert body["divergence"]["kind"] == "hash_mismatch"
    assert body["divergence"]["at_seq_id"] == 1
    assert body["divergence"]["a_event"]["timestamp"] == 2.0
    assert body["divergence"]["b_event"]["timestamp"] == 3.0


def test_diff_path_traversal_rejected(client: TestClient, replay_dir: Path) -> None:
    r = client.post("/v1/replay/diff", json={"a": "../etc/passwd", "b": "../etc/passwd"})
    assert r.status_code == 403


def test_diff_subdir_rejected(client: TestClient, replay_dir: Path) -> None:
    r = client.post("/v1/replay/diff", json={"a": "sub/x.jsonl", "b": "sub/x.jsonl"})
    assert r.status_code == 403


def test_diff_missing_file_404(client: TestClient, replay_dir: Path) -> None:
    r = client.post("/v1/replay/diff", json={"a": "nonexistent.jsonl", "b": "nope.jsonl"})
    assert r.status_code == 404


def test_diff_dotfile_rejected(client: TestClient, replay_dir: Path) -> None:
    r = client.post("/v1/replay/diff", json={"a": ".hidden", "b": ".hidden"})
    assert r.status_code == 403
