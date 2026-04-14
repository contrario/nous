"""
NOUS Generated Code — Colony
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
from symbiosis_engine import SymbiosisEngine, BondConfig

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "Colony"
HEARTBEAT_SECONDS = 30
COST_CEILING = 0.5
LAW_COST_CEILING = 0.5

ENTRYPOINT_SOULS = ['Scout']
LISTENER_SOULS = ['Analyst', 'Reporter']

# ═══ Message Types ═══

class ScanData(BaseModel):
    url: str
    score: float

class Summary(BaseModel):
    text: str


# ═══ Soul Definitions ═══

class Soul_Scout:
    """Soul: Scout | Wake: HEARTBEAT"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Scout"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0A"
        self.senses = ['http_get']
        self.cycle_count = 0
        self.discovered = 0
        self.shared_score = 0.0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Scout"""
        self.discovered += 1
        data = await self._sense("http_get", url="https://api.github.com/zen")
        await self._runtime.channels.send("Scout_ScanData", ScanData(url="test", score=0.95))

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

class Soul_Analyst:
    """Soul: Analyst | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Analyst"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0A"
        self.senses = []
        self.cycle_count = 0
        self.analyzed = 0
        self.shared_score = 0.0
        self.consensus = 0.0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Analyst"""
        self.analyzed += 1
        await self._runtime.channels.send("Analyst_Summary", Summary(text="done"))

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

class Soul_Reporter:
    """Soul: Reporter | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Reporter"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier0B"
        self.senses = []
        self.cycle_count = 0
        self.reports = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Reporter"""
        self.reports += 1

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
    """Build event-driven runtime for Colony"""
    rt = NousRuntime(
        world_name="Colony",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        cost_ceiling=COST_CEILING,
    )

    _soul_scout = Soul_Scout(rt)
    rt.add_soul(SoulRunner(
        name="Scout",
        wake_strategy=SoulWakeStrategy.HEARTBEAT,
        instinct_fn=_soul_scout.instinct,
        heal_fn=_soul_scout.heal,
        listen_channel=None,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    _soul_analyst = Soul_Analyst(rt)
    rt.add_soul(SoulRunner(
        name="Analyst",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_analyst.instinct,
        heal_fn=_soul_analyst.heal,
        listen_channel="Scout_ScanData",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    _soul_reporter = Soul_Reporter(rt)
    rt.add_soul(SoulRunner(
        name="Reporter",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_reporter.instinct,
        heal_fn=_soul_reporter.heal,
        listen_channel="Analyst_Summary",
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