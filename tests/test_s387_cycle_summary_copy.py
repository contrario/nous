"""
S387 D387-1 (docs/ONE_PRICE_SOURCE_DESIGN.md section 24): the heartbeat
summary line prints no cost figure, because nothing meters spend.

# __s387_test_cycle_summary_copy_v1__
"""
from __future__ import annotations

import asyncio
import logging

import pytest

import runtime


def _summary_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    rt = runtime.NousRuntime(world_name="S387Summary", heartbeat_seconds=0.05, cost_ceiling=0.1)

    def found() -> bool:
        return any(" summary: " in r.getMessage() for r in caplog.records)

    async def drive() -> None:
        task = asyncio.create_task(rt._heartbeat_cost_reset())
        for _ in range(200):
            await asyncio.sleep(0.02)
            if found():
                break
        rt._shutdown.set()
        await asyncio.wait_for(task, timeout=5)

    with caplog.at_level(logging.INFO, logger="nous.runtime"):
        asyncio.run(drive())
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "nous.runtime" and " summary: " in r.getMessage()
    ]


def test_heartbeat_summary_prints_no_cost_figure(caplog: pytest.LogCaptureFixture) -> None:
    lines = _summary_lines(caplog)
    assert lines, "no heartbeat summary record captured"
    first = lines[0]
    has_cost = "cost=$" in first
    assert not has_cost, "summary prints a cost that nothing meters: " + first
    assert "spend=not-metered" in first, first
    assert "pre_check_ceiling=$0.10" in first, first
    assert first.startswith("Cycle 1 summary: "), first
