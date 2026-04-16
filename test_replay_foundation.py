"""
test_replay_foundation.py — Correctness tests for Phase A replay primitives.

Tests:
  1. Append + hash chain integrity
  2. Resume from existing store (seq + hash continue)
  3. Byte-exact replay: record a session, replay it, verify equivalence
  4. Tamper detection: mutate an event, verify() catches it at the right seq
  5. ReplayDivergence: replay mismatch raises with full context
  6. Off mode: zero overhead (no file, no events)
  7. Deterministic LLM seed: same inputs → same seed
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Allow running from /opt/aetherlang_agents/nous directly
sys.path.insert(0, "/opt/aetherlang_agents/nous")

from replay_store import EventStore, HashChainBroken, GENESIS_HASH, _compute_hash
from replay_runtime import ReplayContext, ReplayDivergence, build_context


def test_append_and_chain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = EventStore.open(path, mode="record")
        e1 = store.append("Watcher", 1, "sense.invoke", {"tool": "stock"}, parent_id=-1)
        e2 = store.append("Watcher", 1, "sense.result", {"value": 42}, parent_id=e1.seq_id)
        e3 = store.append("Watcher", 1, "cycle.end", {"status": "ok"}, parent_id=e2.seq_id)
        assert e1.seq_id == 0 and e2.seq_id == 1 and e3.seq_id == 2
        assert e1.prev_hash == GENESIS_HASH
        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash
        store.close()
        # Verify freshly-opened replay store passes integrity check
        verify_store = EventStore.open(path, mode="replay")
        ok, bad_seq, reason = verify_store.verify()
        assert ok, f"verify failed at seq={bad_seq}: {reason}"
        verify_store.close()
    print("PASS test_append_and_chain")


def test_resume() -> None:
    """Open a store, append events, close, reopen — chain should continue."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        s1 = EventStore.open(path, mode="record")
        s1.append("A", 1, "k1", {"v": 1})
        s1.append("A", 1, "k2", {"v": 2})
        last_hash = s1.last_hash
        s1.close()
        s2 = EventStore.open(path, mode="record")
        assert s2.seq_counter == 2, f"expected seq=2, got {s2.seq_counter}"
        assert s2.last_hash == last_hash, "hash chain not resumed"
        e3 = s2.append("A", 1, "k3", {"v": 3})
        assert e3.seq_id == 2
        assert e3.prev_hash == last_hash
        s2.close()
    print("PASS test_resume")


def test_byte_exact_replay() -> None:
    """Record a session, replay it, confirm every sense returns the recorded value."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "events.jsonl")

        # ─── Record ───
        ctx_rec = build_context(mode="record", path=path)

        async def fake_binance() -> dict:
            return {"symbol": "BTC", "price": "74982.74"}

        async def fake_weather() -> str:
            return "athens: sunny 20C"

        async def record_session() -> list:
            results = []
            results.append(await ctx_rec.record_or_replay_sense(
                "Watcher", 1, "stock_price", {"symbol": "BTC"}, fake_binance,
            ))
            results.append(await ctx_rec.record_or_replay_sense(
                "Watcher", 1, "weather", {"city": "Athens"}, fake_weather,
            ))
            ctx_rec.record_memory_write("Watcher", 1, "last_price", 0.0, 74982.74)
            return results

        rec_results = asyncio.run(record_session())
        assert ctx_rec.store is not None
        ctx_rec.store.close()

        # ─── Replay ───
        ctx_rep = build_context(mode="replay", path=path)

        async def execute_must_not_be_called() -> None:
            raise AssertionError("replay should not call execute()")

        async def replay_session() -> list:
            results = []
            results.append(await ctx_rep.record_or_replay_sense(
                "Watcher", 1, "stock_price", {"symbol": "BTC"},
                execute_must_not_be_called,
            ))
            results.append(await ctx_rep.record_or_replay_sense(
                "Watcher", 1, "weather", {"city": "Athens"},
                execute_must_not_be_called,
            ))
            ctx_rep.record_memory_write("Watcher", 1, "last_price", 0.0, 74982.74)
            return results

        rep_results = asyncio.run(replay_session())
        assert rec_results == rep_results, (
            f"replay mismatch:\n  rec: {rec_results}\n  rep: {rep_results}"
        )
        assert ctx_rep.store is not None
        ctx_rep.store.close()
    print("PASS test_byte_exact_replay")


def test_tamper_detection() -> None:
    """Mutate one event's data field and ensure verify() catches it at that seq."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = EventStore.open(path, mode="record")
        store.append("A", 1, "k1", {"v": 1})
        store.append("A", 1, "k2", {"v": 2})
        store.append("A", 1, "k3", {"v": 3})
        store.close()
        # Tamper: modify middle event's `data` but leave hashes alone.
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        d = json.loads(lines[1])
        d["data"]["v"] = 999  # tampered
        lines[1] = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Verify must detect the tamper at seq=1.
        verify_store = EventStore.open(path, mode="replay")
        ok, bad_seq, reason = verify_store.verify()
        assert not ok, "verify should have detected tamper"
        assert bad_seq == 1, f"expected bad_seq=1, got {bad_seq}"
        assert "hash mismatch" in reason
        verify_store.close()
    print("PASS test_tamper_detection")


def test_replay_divergence() -> None:
    """Replay code path that differs from recording → ReplayDivergence."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "events.jsonl")

        # Record: call sense A then sense B
        ctx_rec = build_context(mode="record", path=path)

        async def fake() -> int:
            return 42

        async def rec() -> None:
            await ctx_rec.record_or_replay_sense("S", 1, "A", {}, fake)
            await ctx_rec.record_or_replay_sense("S", 1, "B", {}, fake)

        asyncio.run(rec())
        assert ctx_rec.store is not None
        ctx_rec.store.close()

        # Replay but call sense A then sense C (divergence at second call)
        ctx_rep = build_context(mode="replay", path=path)

        async def rep() -> None:
            await ctx_rep.record_or_replay_sense("S", 1, "A", {}, fake)
            await ctx_rep.record_or_replay_sense("S", 1, "C", {}, fake)

        try:
            asyncio.run(rep())
            raise AssertionError("expected ReplayDivergence but call succeeded")
        except ReplayDivergence as div:
            # The key for A and C differ, so divergence key check fires.
            assert div.expected_kind == "sense.invoke"
            assert ctx_rep.store is not None
            ctx_rep.store.close()
    print("PASS test_replay_divergence")


def test_off_mode_zero_overhead() -> None:
    """ReplayContext(mode='off') creates no store, wraps pass-through."""
    ctx = build_context(mode="off")
    assert ctx.store is None
    assert ctx.mode == "off"

    async def fake() -> int:
        return 7

    async def run() -> int:
        return await ctx.record_or_replay_sense("X", 0, "tool", {}, fake)

    result = asyncio.run(run())
    assert result == 7
    # clock + random should pass through to real implementations
    t = ctx.now()
    r = ctx.rand()
    assert t > 0 and 0 <= r <= 1
    print("PASS test_off_mode_zero_overhead")


def test_llm_seed_deterministic() -> None:
    ctx1 = build_context(mode="off", seed_base=1234)
    ctx2 = build_context(mode="off", seed_base=1234)
    s1 = ctx1.llm_seed("Watcher", 5, "prompt_hash_xyz")
    s2 = ctx2.llm_seed("Watcher", 5, "prompt_hash_xyz")
    assert s1 == s2, "identical inputs must yield identical seed"
    # Different inputs → different seed
    s3 = ctx1.llm_seed("Watcher", 6, "prompt_hash_xyz")
    assert s1 != s3
    print("PASS test_llm_seed_deterministic")


def main() -> int:
    test_append_and_chain()
    test_resume()
    test_byte_exact_replay()
    test_tamper_detection()
    test_replay_divergence()
    test_off_mode_zero_overhead()
    test_llm_seed_deterministic()
    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
