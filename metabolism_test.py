"""
NOUS Generated Code — BioLab
Auto-generated from .nous source. Do not edit manually.
Runtime: Python 3.11+ asyncio | Event-Driven Architecture
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = object
    def Field(**kw): return kw.get('default')

from runtime import (
    NousRuntime, SoulRunner, SoulWakeStrategy,
    CircuitBreakerTripped, CostTracker, SenseCache,
    ChannelRegistry, SenseExecutor, DistributedRuntime,
)
from metabolism_engine import MetabolismEngine, MetabolismConfig

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "BioLab"
HEARTBEAT_SECONDS = 30
COST_CEILING = 0.5
LAW_COST_CEILING = 0.5

ENTRYPOINT_SOULS = ['Worker']
LISTENER_SOULS = ['Logger', 'Supervisor']

# ═══ Message Types ═══

class ScanData(BaseModel):
    url: str

class Report(BaseModel):
    text: str


# ═══ Soul Definitions ═══

class Soul_Worker:
    """Soul: Worker | Wake: HEARTBEAT"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Worker"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0A"
        self.senses = ['http_get']
        self.cycle_count = 0
        self.tasks_done = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Worker"""
        self.tasks_done += 1
        r = await self._sense("http_get", url="https://api.github.com/zen")
        await self._runtime.channels.send("Worker_ScanData", ScanData(url="done"))

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "error" or "error" in str(error).lower():
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_Supervisor:
    """Soul: Supervisor | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Supervisor"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0B"
        self.senses = []
        self.cycle_count = 0
        self.reports = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Supervisor"""
        self.reports += 1
        await self._runtime.channels.send("Supervisor_Report", Report(text="supervised"))

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "error" or "error" in str(error).lower():
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_Logger:
    """Soul: Logger | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Logger"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0B"
        self.senses = []
        self.cycle_count = 0
        self.logs = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Logger"""
        self.logs += 1

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "error" or "error" in str(error).lower():
            for _retry in range(1):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

# ═══ Runtime Builder ═══

def build_runtime() -> NousRuntime:
    """Build event-driven runtime for BioLab"""
    rt = NousRuntime(
        world_name="BioLab",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        cost_ceiling=COST_CEILING,
    )

    _soul_worker = Soul_Worker(rt)
    rt.add_soul(SoulRunner(
        name="Worker",
        wake_strategy=SoulWakeStrategy.HEARTBEAT,
        instinct_fn=_soul_worker.instinct,
        heal_fn=_soul_worker.heal,
        listen_channel=None,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    _soul_supervisor = Soul_Supervisor(rt)
    rt.add_soul(SoulRunner(
        name="Supervisor",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_supervisor.instinct,
        heal_fn=_soul_supervisor.heal,
        listen_channel="Worker_ScanData",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0B",
    ))

    _soul_logger = Soul_Logger(rt)
    rt.add_soul(SoulRunner(
        name="Logger",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_logger.instinct,
        heal_fn=_soul_logger.heal,
        listen_channel="Supervisor_Report",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0B",
    ))

    return rt


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    rt = build_runtime()
    asyncio.run(rt.run())