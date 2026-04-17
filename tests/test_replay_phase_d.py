"""
Phase D E2E — LLM replay via ReplayContext.record_or_replay_llm

Standalone test harness (no pytest required).
Exercises the full contract added in patch_37.

Run:
    python3 tests/test_replay_phase_d.py
    echo $?   # 0 on success

# __phase_d_e2e_v1__
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from replay_runtime import ReplayContext, ReplayDivergence
from replay_store import EventStore


PASS: list[str] = []
FAIL: list[str] = []


def _ok(label: str) -> None:
    PASS.append(label)
    print(f"  \u2713 {label}")


def _fail(label: str, err: str) -> None:
    FAIL.append(f"{label}: {err}")
    print(f"  \u2717 {label}: {err}")


def _tmp_log() -> str:
    fd, path = tempfile.mkstemp(prefix="nous_phase_d_", suffix=".jsonl")
    os.close(fd)
    os.unlink(path)
    return path


def _messages(user: str = "hello") -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user},
    ]


def _fake_result(text: str = "hi there", tier: str = "tier-A") -> dict[str, Any]:
    return {
        "success": True,
        "text": text,
        "cost": 0.000123,
        "tier": tier,
        "tokens_in": 10,
        "tokens_out": 5,
        "elapsed_ms": 42.0,
    }


async def test_off_passthrough() -> None:
    label = "OFF mode passthrough (no store)"
    try:
        ctx = ReplayContext(store=None, mode="off")
        calls = {"n": 0}

        async def _exec() -> dict[str, Any]:
            calls["n"] += 1
            return _fake_result("off-mode-response")

        r = await ctx.record_or_replay_llm(
            soul="S", cycle=0, provider="openai", model="gpt-x",
            messages=_messages(), temperature=0.7, execute=_exec,
        )
        assert r["text"] == "off-mode-response", r
        assert calls["n"] == 1, calls
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


async def test_record_roundtrip() -> str:
    label = "RECORD roundtrip writes llm.request + llm.response"
    path = _tmp_log()
    try:
        store = EventStore.open(path, mode="record")
        ctx = ReplayContext(store=store, mode="record", seed_base=42)

        async def _exec() -> dict[str, Any]:
            return _fake_result("recorded text")

        r = await ctx.record_or_replay_llm(
            soul="Watcher", cycle=0, provider="openai", model="gpt-x",
            messages=_messages(), temperature=0.5, execute=_exec,
        )
        store.close()

        assert r["text"] == "recorded text", r

        verify_store = EventStore.open(path, mode="replay")
        events = list(verify_store)
        verify_store.close()

        kinds = [e.kind for e in events]
        assert "llm.request" in kinds, kinds
        assert "llm.response" in kinds, kinds

        req = next(e for e in events if e.kind == "llm.request")
        resp = next(e for e in events if e.kind == "llm.response")
        assert req.data["provider"] == "openai"
        assert req.data["model"] == "gpt-x"
        assert req.data["temperature"] == 0.5
        assert isinstance(req.data["seed"], int)
        assert req.data["key"] == resp.data["key"]
        assert resp.data["text"] == "recorded text"
        assert resp.data["tier"] == "tier-A"
        assert resp.data["tokens_in"] == 10
        assert resp.data["tokens_out"] == 5

        _ok(label)
        return path
    except Exception as e:
        _fail(label, repr(e))
        return path


async def test_replay_hit(path: str) -> None:
    label = "REPLAY returns recorded response without calling execute"
    try:
        store = EventStore.open(path, mode="replay")
        ctx = ReplayContext(store=store, mode="replay", seed_base=42)

        calls = {"n": 0}

        async def _exec() -> dict[str, Any]:
            calls["n"] += 1
            return _fake_result("LIVE-SHOULD-NOT-HAPPEN")

        r = await ctx.record_or_replay_llm(
            soul="Watcher", cycle=0, provider="openai", model="gpt-x",
            messages=_messages(), temperature=0.5, execute=_exec,
        )
        store.close()

        assert calls["n"] == 0, f"execute was called: {calls}"
        assert r["text"] == "recorded text", r
        assert r["tier"] == "tier-A"
        assert r["tokens_in"] == 10
        assert r["cost"] == 0.000123
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


async def test_replay_divergence_on_prompt_change(base_path: str) -> None:
    label = "REPLAY raises on mismatched prompt_hash"
    try:
        store = EventStore.open(base_path, mode="replay")
        ctx = ReplayContext(store=store, mode="replay", seed_base=42)

        async def _exec() -> dict[str, Any]:
            return _fake_result()

        raised = False
        try:
            await ctx.record_or_replay_llm(
                soul="Watcher", cycle=0, provider="openai", model="gpt-x",
                messages=_messages(user="DIFFERENT MESSAGE"),
                temperature=0.5, execute=_exec,
            )
        except ReplayDivergence:
            raised = True
        except Exception as e:
            _fail(label, f"wrong exception: {e!r}")
            store.close()
            return
        store.close()
        assert raised, "ReplayDivergence not raised on prompt change"
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


async def test_error_record_and_replay() -> None:
    label = "RECORD+REPLAY of llm.error re-raises on replay"
    path = _tmp_log()
    try:
        store = EventStore.open(path, mode="record")
        ctx = ReplayContext(store=store, mode="record", seed_base=1)

        async def _exec_boom() -> dict[str, Any]:
            raise RuntimeError("provider exploded")

        raised_record = False
        try:
            await ctx.record_or_replay_llm(
                soul="S", cycle=0, provider="openai", model="gpt-x",
                messages=_messages(), temperature=0.0, execute=_exec_boom,
            )
        except RuntimeError:
            raised_record = True
        store.close()
        assert raised_record

        store2 = EventStore.open(path, mode="replay")
        ctx2 = ReplayContext(store=store2, mode="replay", seed_base=1)

        async def _exec_never() -> dict[str, Any]:
            raise AssertionError("execute must not run in replay")

        raised_replay = False
        try:
            await ctx2.record_or_replay_llm(
                soul="S", cycle=0, provider="openai", model="gpt-x",
                messages=_messages(), temperature=0.0, execute=_exec_never,
            )
        except RuntimeError as e:
            if "provider exploded" in str(e):
                raised_replay = True
        store2.close()
        assert raised_replay, "error not re-raised on replay"
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_llm_seed_determinism() -> None:
    label = "llm_seed is deterministic across ctx instances"
    try:
        ctx_a = ReplayContext(mode="off", seed_base=99)
        ctx_b = ReplayContext(mode="off", seed_base=99)
        s1 = ctx_a.llm_seed(soul="W", cycle=3, prompt_hash="abc123")
        s2 = ctx_b.llm_seed(soul="W", cycle=3, prompt_hash="abc123")
        s3 = ctx_a.llm_seed(soul="W", cycle=3, prompt_hash="abc124")
        assert s1 == s2, (s1, s2)
        assert s1 != s3, (s1, s3)
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


async def _amain() -> None:
    print("=" * 56)
    print("PHASE D E2E — LLM REPLAY")
    print("=" * 56)
    await test_off_passthrough()
    path = await test_record_roundtrip()
    await test_replay_hit(path)
    await test_replay_divergence_on_prompt_change(path)
    await test_error_record_and_replay()
    test_llm_seed_determinism()
    try:
        os.unlink(path)
    except OSError:
        pass


def main() -> int:
    asyncio.run(_amain())
    print("=" * 56)
    if FAIL:
        print(f"PHASE D E2E — {len(FAIL)} FAILURE(S)")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"PHASE D E2E — ALL GREEN ({len(PASS)}/{len(PASS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
