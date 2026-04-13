"""
NOUS Test — Runtime v2 + CodeGen v2
Tests event-driven codegen, topology analysis, cost tracking, sense cache.
"""
from __future__ import annotations

import asyncio
import py_compile
import sys
import tempfile
from pathlib import Path

from parser import parse_nous
from runtime import (
    NousRuntime, SoulRunner, SoulWakeStrategy,
    CostTracker, SenseCache, CircuitBreakerTripped,
    ChannelRegistry, determine_wake_strategies,
)
from codegen import NousCodeGen, generate_python


GATE_ALPHA = Path("/opt/aetherlang_agents/nous/gate_alpha.nous").read_text()


def test_topology_analysis() -> None:
    program = parse_nous(GATE_ALPHA)
    gen = NousCodeGen(program)
    assert gen._entrypoints == {"Scout"}, f"Expected Scout as entrypoint, got {gen._entrypoints}"
    assert gen._listeners == {"Quant", "Hunter", "Monitor"}, f"Expected listeners, got {gen._listeners}"
    assert gen._cost_ceiling == 0.10
    assert gen._heartbeat_seconds == 300
    print("  ✓ test_topology_analysis")


def test_determine_wake_strategies() -> None:
    souls = ["Scout", "Quant", "Hunter", "Monitor"]
    routes = [("Scout", "Quant"), ("Quant", "Hunter"), ("Scout", "Monitor")]
    strategies = determine_wake_strategies(souls, routes)
    assert strategies["Scout"] == SoulWakeStrategy.HEARTBEAT
    assert strategies["Quant"] == SoulWakeStrategy.LISTENER
    assert strategies["Hunter"] == SoulWakeStrategy.LISTENER
    assert strategies["Monitor"] == SoulWakeStrategy.LISTENER
    print("  ✓ test_determine_wake_strategies")


def test_codegen_compiles() -> None:
    program = parse_nous(GATE_ALPHA)
    code = generate_python(program)
    assert "SoulWakeStrategy.LISTENER" in code, "Missing LISTENER strategy"
    assert "SoulWakeStrategy.HEARTBEAT" in code, "Missing HEARTBEAT strategy"
    assert "ENTRYPOINT_SOULS" in code, "Missing ENTRYPOINT_SOULS"
    assert "LISTENER_SOULS" in code, "Missing LISTENER_SOULS"
    assert "build_runtime" in code, "Missing build_runtime"
    assert "NousRuntime" in code, "Missing NousRuntime"
    assert "self._runtime.channels.send" in code, "Missing channel send"
    assert "self._runtime.channels.receive" in code, "Missing channel receive"
    assert "self._sense(" in code, "Missing sense call via executor"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        f.flush()
        py_compile.compile(f.name, doraise=True)
    print("  ✓ test_codegen_compiles")


def test_codegen_wake_counts() -> None:
    program = parse_nous(GATE_ALPHA)
    code = generate_python(program)
    heartbeat_count = code.count("SoulWakeStrategy.HEARTBEAT")
    listener_count = code.count("SoulWakeStrategy.LISTENER")
    assert heartbeat_count == 1, f"Expected 1 heartbeat soul, got {heartbeat_count}"
    assert listener_count == 3, f"Expected 3 listener souls, got {listener_count}"
    print("  ✓ test_codegen_wake_counts")


def test_cost_tracker() -> None:
    async def _run() -> None:
        ct = CostTracker(ceiling=0.10)
        await ct.charge("Scout", 500, 200, "Tier1")
        assert ct.spent > 0
        assert ct.remaining < 0.10
        can = await ct.pre_check("Quant", 500, 200, "Tier1")
        assert can is True
        try:
            for _ in range(100):
                await ct.charge("Spam", 5000, 5000, "Tier3")
            assert False, "Should have tripped"
        except CircuitBreakerTripped:
            pass
        metrics = ct.reset()
        assert metrics.total_cost > 0
        assert ct.spent == 0.0

    asyncio.run(_run())
    print("  ✓ test_cost_tracker")


def test_sense_cache() -> None:
    cache = SenseCache()
    hit, val = cache.get("fetch_rsi", {"pair": "BTC/USDT"})
    assert hit is False
    cache.put("fetch_rsi", {"pair": "BTC/USDT"}, {"rsi": 45.2})
    hit, val = cache.get("fetch_rsi", {"pair": "BTC/USDT"})
    assert hit is True
    assert val["rsi"] == 45.2
    hit2, _ = cache.get("fetch_rsi", {"pair": "ETH/USDT"})
    assert hit2 is False
    hits, misses = cache.clear()
    assert hits == 1
    assert misses == 2
    print("  ✓ test_sense_cache")


def test_channel_backpressure() -> None:
    async def _run() -> None:
        registry = ChannelRegistry(default_maxsize=2)
        ch = await registry.get("test")
        await ch.send("msg1")
        await ch.send("msg2")
        assert ch.pending == 2
        msg = await ch.receive(timeout=1.0)
        assert msg == "msg1"
        assert ch.pending == 1

    asyncio.run(_run())
    print("  ✓ test_channel_backpressure")


def test_soul_runner_listener_blocks() -> None:
    async def _run() -> None:
        received: list[str] = []
        async def fake_instinct() -> None:
            received.append("woke")
        async def fake_heal(e: Exception) -> bool:
            return False

        registry = ChannelRegistry()
        shutdown = asyncio.Event()
        runner = SoulRunner(
            name="TestSoul",
            wake_strategy=SoulWakeStrategy.LISTENER,
            instinct_fn=fake_instinct,
            heal_fn=fake_heal,
            listen_channel="upstream_Signal",
            heartbeat_seconds=1.0,
        )
        runner.set_shutdown_event(shutdown)

        async def send_after_delay() -> None:
            await asyncio.sleep(0.1)
            await registry.send("upstream_Signal", {"test": True})
            await asyncio.sleep(0.1)
            shutdown.set()

        await asyncio.gather(
            runner.run(registry),
            send_after_delay(),
        )
        assert len(received) == 1, f"Expected 1 wake, got {len(received)}"

    asyncio.run(_run())
    print("  ✓ test_soul_runner_listener_blocks")


def test_generated_output_structure() -> None:
    program = parse_nous(GATE_ALPHA)
    code = generate_python(program)
    lines = code.split("\n")
    sections = [l.strip() for l in lines if l.strip().startswith("# ═══")]
    expected = ["World Laws", "Message Types", "Soul Definitions", "Runtime Builder"]
    for exp in expected:
        found = any(exp in s for s in sections)
        assert found, f"Missing section: {exp}"
    print("  ✓ test_generated_output_structure")


if __name__ == "__main__":
    print("\n═══ NOUS Runtime v2 + CodeGen v2 Tests ═══\n")
    test_topology_analysis()
    test_determine_wake_strategies()
    test_codegen_compiles()
    test_codegen_wake_counts()
    test_cost_tracker()
    test_sense_cache()
    test_channel_backpressure()
    test_soul_runner_listener_blocks()
    test_generated_output_structure()
    print(f"\n  ═══ ALL 9/9 TESTS PASS ═══\n")
