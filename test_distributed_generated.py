"""
NOUS Generated Code — DistributedPipeline
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

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "DistributedPipeline"
HEARTBEAT_SECONDS = 30
COST_CEILING = 0.5
LAW_COST_CEILING = 0.5

ENTRYPOINT_SOULS = ['Scanner']
LISTENER_SOULS = ['Analyzer', 'Executor']

# ═══ Message Types ═══

class Signal(BaseModel):
    source: str
    data: str
    confidence: float = 0.0

class Analysis(BaseModel):
    result: str
    score: float = 0.0


# ═══ Soul Definitions ═══

class Soul_Scanner:
    """Soul: Scanner | Wake: HEARTBEAT"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Scanner"
        self._runtime = runtime
        self.model = "claude-sonnet"
        self.tier = "Tier0A"
        self.senses = ['http_get']
        self.cycle_count = 0
        self.scan_count = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Scanner"""
        raw = await self._sense("http_get", url="https://api.example.com/data")
        self.scan_count += 1
        await self._runtime.channels.send("Scanner_Signal", Signal(source=scanner, data=raw, confidence=0.85))

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(3):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_Analyzer:
    """Soul: Analyzer | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Analyzer"
        self._runtime = runtime
        self.model = "claude-sonnet"
        self.tier = "Tier0A"
        self.senses = []
        self.cycle_count = 0
        self.analyses = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Analyzer"""
        msg = await self._runtime.channels.receive("Scanner_Signal")
        self.analyses += 1
        await self._runtime.channels.send("Analyzer_Analysis", Analysis(result=analyzed, score=0.9))

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        log.warning(f'{self.name}: no heal rules, error: {error}')
        return False

class Soul_Executor:
    """Soul: Executor | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Executor"
        self._runtime = runtime
        self.model = "claude-sonnet"
        self.tier = "Tier0A"
        self.senses = ['http_post']
        self.cycle_count = 0
        self.executions = 0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Executor"""
        cmd = await self._runtime.channels.receive("Analyzer_Analysis")
        self.executions += 1
        await self._sense("http_post", url="https://api.example.com/execute", body=cmd)

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "api_error" or "api_error" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

# ═══ Topology ═══

TOPOLOGY = [
    {"name": "node_alpha", "host": "192.168.1.10", "port": 9100, "souls": ['Scanner']},
    {"name": "node_beta", "host": "192.168.1.20", "port": 9100, "souls": ['Analyzer', 'Executor']},
]

SPEAK_CHANNELS = {"Scanner": "Scanner_Signal", "Analyzer": "Analyzer_Analysis"}
ROUTES = [("Scanner", "Analyzer"), ("Analyzer", "Executor")]


# ═══ Runtime Builder ═══

def build_runtime(node_name: str = "") -> NousRuntime:
    """Build runtime for DistributedPipeline — auto-selects distributed if topology present."""
    if not node_name:
        import sys, os
        node_name = os.environ.get("NOUS_NODE", "")
        for arg in sys.argv:
            if arg.startswith("--node="):
                node_name = arg.split("=", 1)[1]

    node_info = None
    for n in TOPOLOGY:
        if n["name"] == node_name:
            node_info = n
            break

    if node_info:
        rt = DistributedRuntime(
            world_name="DistributedPipeline",
            heartbeat_seconds=HEARTBEAT_SECONDS,
            cost_ceiling=COST_CEILING,
            node_name=node_name,
            node_host=node_info["host"],
            node_port=node_info["port"],
            topology=TOPOLOGY,
            local_souls=node_info["souls"],
        )
        rt.set_route_map(ROUTES, SPEAK_CHANNELS)
        local_set = set(node_info["souls"])
    else:
        rt = NousRuntime(
            world_name="DistributedPipeline",
            heartbeat_seconds=HEARTBEAT_SECONDS,
            cost_ceiling=COST_CEILING,
        )
        local_set = None

    if local_set is None or "Scanner" in local_set:
        _soul_scanner = Soul_Scanner(rt)
        rt.add_soul(SoulRunner(
            name="Scanner",
            wake_strategy=SoulWakeStrategy.HEARTBEAT,
            instinct_fn=_soul_scanner.instinct,
            heal_fn=_soul_scanner.heal,
            listen_channel=None,
            heartbeat_seconds=HEARTBEAT_SECONDS,
            tier="Tier0A",
        ))

    if local_set is None or "Analyzer" in local_set:
        _soul_analyzer = Soul_Analyzer(rt)
        rt.add_soul(SoulRunner(
            name="Analyzer",
            wake_strategy=SoulWakeStrategy.LISTENER,
            instinct_fn=_soul_analyzer.instinct,
            heal_fn=_soul_analyzer.heal,
            listen_channel="Scanner_Signal",
            heartbeat_seconds=HEARTBEAT_SECONDS,
            tier="Tier0A",
        ))

    if local_set is None or "Executor" in local_set:
        _soul_executor = Soul_Executor(rt)
        rt.add_soul(SoulRunner(
            name="Executor",
            wake_strategy=SoulWakeStrategy.LISTENER,
            instinct_fn=_soul_executor.instinct,
            heal_fn=_soul_executor.heal,
            listen_channel="Analyzer_Analysis",
            heartbeat_seconds=HEARTBEAT_SECONDS,
            tier="Tier0A",
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