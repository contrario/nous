"""
NOUS Generated Code — TradingFloor
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
from mitosis_engine import MitosisEngine, MitosisConfig
from immune_engine import ImmuneEngine, ImmuneConfig
from telemetry_engine import TelemetryEngine, TelemetryConfig, SpanKind, SpanStatus
from consciousness_engine import ConsciousnessEngine, ConsciousnessConfig
from metabolism_engine import MetabolismEngine, MetabolismConfig
from symbiosis_engine import SymbiosisEngine, BondConfig
from dream_engine import DreamEngine, DreamConfig

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "TradingFloor"
HEARTBEAT_SECONDS = 15
COST_CEILING = 5.0
LAW_COST_CEILING = 5.0

ENTRYPOINT_SOULS = ['Watcher']
LISTENER_SOULS = ['Executor', 'RiskGuard', 'Strategist']

# ═══ Message Types ═══

class PriceSnapshot(BaseModel):
    symbol: str
    price: float
    volume: float
    change_pct: float
    timestamp: str

class TradeSignal(BaseModel):
    symbol: str
    action: str
    confidence: float
    reason: str

class TradeOrder(BaseModel):
    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str

class RiskAlert(BaseModel):
    level: str
    message: str
    exposure: float
    drawdown: float


# ═══ Soul Definitions ═══

class Soul_Watcher:
    """Soul: Watcher | Wake: HEARTBEAT"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Watcher"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier1"
        self.senses = ['http_get']
        self.cycle_count = 0
        self.ticks_collected = 0
        self.last_price = 0.0
        self.price_history = ""
        self.dna_poll_interval = 15
        self.dna_batch_size = 3

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Watcher"""
        data = await self._sense("http_get", url="https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
        self.last_price = 0.0
        self.ticks_collected = (ticks_collected + 1)
        await self._runtime.channels.send("Watcher_PriceSnapshot", PriceSnapshot(symbol="BTCUSDT", price=last_price, volume=0.0, change_pct=0.0, timestamp="now"))

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "api_error" or "api_error" in str(error).lower():
            for _retry in range(3):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

    def _mitosis_check(self, _metrics=None) -> bool:
        metrics = {
            "cycle_count": self.cycle_count,
            "queue_depth": getattr(self, "_queue_depth", 0),
            "latency": getattr(self, "_last_latency", 0.0),
            "error_count": getattr(self, "_error_count", 0),
            "ticks_collected": self.ticks_collected,
            "last_price": self.last_price,
            "price_history": self.price_history,
        }
        return (metrics.get("queue_depth", 0) > 10)

    def _retire_check(self, _metrics=None) -> bool:
        metrics = {
            "cycle_count": self.cycle_count,
            "queue_depth": getattr(self, "_queue_depth", 0),
            "latency": getattr(self, "_last_latency", 0.0),
            "error_count": getattr(self, "_error_count", 0),
            "ticks_collected": self.ticks_collected,
            "last_price": self.last_price,
            "price_history": self.price_history,
        }
        return (metrics.get("queue_depth", 0) < 3)

    @classmethod
    def clone_factory(cls, clone_name: str, clone_tier: str | None, runtime: NousRuntime) -> 'Soul_Watcher':
        clone = cls(runtime)
        clone.name = clone_name
        clone.tier = clone_tier or "Tier1"
        return clone

class Soul_Strategist:
    """Soul: Strategist | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Strategist"
        self._runtime = runtime
        self.model = "claude-3-haiku"
        self.tier = "Tier0A"
        self.senses = ['http_get']
        self.cycle_count = 0
        self.signals_generated = 0
        self.win_rate = 0.0
        self.shared_exposure = 0.0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Strategist"""
        snapshot = await self._runtime.channels.receive("Watcher_PriceSnapshot")
        if not ((snapshot != null)):
            return
        await asyncio.sleep(HEARTBEAT_SECONDS * 5)
        await self._runtime.channels.send("Strategist_TradeSignal", TradeSignal(symbol=snapshot.symbol, action="HOLD", confidence=0.65, reason="awaiting confirmation"))
        self.signals_generated = (signals_generated + 1)

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_Executor:
    """Soul: Executor | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "Executor"
        self._runtime = runtime
        self.model = "deepseek-chat"
        self.tier = "Tier1"
        self.senses = []
        self.cycle_count = 0
        self.orders_placed = 0
        self.total_volume = 0.0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Executor"""
        signal = await self._runtime.channels.receive("Strategist_TradeSignal")
        if not ((signal.confidence > 0.7)):
            return
        await asyncio.sleep(HEARTBEAT_SECONDS * 10)
        await self._runtime.channels.send("Executor_TradeOrder", TradeOrder(symbol=signal.symbol, side=signal.action, quantity=0.001, price=0.0, order_type="LIMIT"))
        self.orders_placed = (orders_placed + 1)

    async def heal(self, error: Exception) -> bool:
        error_type = type(error).__name__.lower()
        if error_type == "api_error" or "api_error" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(1)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

class Soul_RiskGuard:
    """Soul: RiskGuard | Wake: LISTENER"""

    def __init__(self, runtime: NousRuntime) -> None:
        self.name = "RiskGuard"
        self._runtime = runtime
        self.model = "claude-3-haiku"
        self.tier = "Tier0A"
        self.senses = []
        self.cycle_count = 0
        self.alerts_fired = 0
        self.max_drawdown = 0.0
        self.shared_exposure = 0.0

    async def _sense(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._runtime.sense_executor.call(tool_name, kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for RiskGuard"""
        order = await self._runtime.channels.receive("Executor_TradeOrder")
        if not ((order != null)):
            return
        await asyncio.sleep(HEARTBEAT_SECONDS * 15)
        self.shared_exposure = (shared_exposure + order.quantity)
        if not ((shared_exposure < 1.0)):
            return
        await self._runtime.channels.send("RiskGuard_RiskAlert", RiskAlert(level="HIGH", message="exposure limit", exposure=shared_exposure, drawdown=max_drawdown))
        self.alerts_fired = (alerts_fired + 1)

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
    """Build event-driven runtime for TradingFloor"""
    rt = NousRuntime(
        world_name="TradingFloor",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        cost_ceiling=COST_CEILING,
    )

    # ═══ Telemetry Engine ═══
    _telemetry = TelemetryEngine(TelemetryConfig(
        enabled=True,
        exporter="jsonl",
        endpoint=None,
        sample_rate=1.0,
        trace_senses=True,
        trace_llm=True,
        buffer_size=2000,
    ))
    rt._telemetry_engine = _telemetry

    _soul_watcher = Soul_Watcher(rt)
    rt.add_soul(SoulRunner(
        name="Watcher",
        wake_strategy=SoulWakeStrategy.HEARTBEAT,
        instinct_fn=_soul_watcher.instinct,
        heal_fn=_soul_watcher.heal,
        listen_channel=None,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier1",
    ))

    _soul_strategist = Soul_Strategist(rt)
    rt.add_soul(SoulRunner(
        name="Strategist",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_strategist.instinct,
        heal_fn=_soul_strategist.heal,
        listen_channel="Watcher_PriceSnapshot",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))

    _soul_executor = Soul_Executor(rt)
    rt.add_soul(SoulRunner(
        name="Executor",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_executor.instinct,
        heal_fn=_soul_executor.heal,
        listen_channel="Strategist_TradeSignal",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier1",
    ))

    _soul_riskguard = Soul_RiskGuard(rt)
    rt.add_soul(SoulRunner(
        name="RiskGuard",
        wake_strategy=SoulWakeStrategy.LISTENER,
        instinct_fn=_soul_riskguard.instinct,
        heal_fn=_soul_riskguard.heal,
        listen_channel="Executor_TradeOrder",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        tier="Tier0A",
    ))


    # ═══ Mitosis Engine ═══
    mitosis = MitosisEngine(rt, check_interval=HEARTBEAT_SECONDS / 3)
    mitosis.register(
        "Watcher",
        MitosisConfig(
            trigger_fn=_soul_watcher._mitosis_check,
            trigger_expr="",
            max_clones=3,
            cooldown_seconds=60,
            clone_tier="Cerebras",
            verify=True,
        ),
        clone_factory=lambda name, tier, rt=rt: Soul_Watcher.clone_factory(name, tier, rt),
    )
    mitosis._configs["Watcher"].retire_trigger_fn = _soul_watcher._retire_check
    mitosis._configs["Watcher"].retire_cooldown_seconds = 120
    mitosis._configs["Watcher"].min_clones = 1
    rt._mitosis_engine = mitosis


    # ═══ Dream Engine ═══
    dream = DreamEngine(rt)
    dream.register(
        "Watcher",
        DreamConfig(
            enabled=True,
            trigger_idle_sec=45,
            dream_mind_model="deepseek-chat",
            dream_mind_tier="Cerebras",
            max_cache=50,
            speculation_depth=3,
        ),
    )
    rt._dream_engine = dream

    async def dream_cache_sense(**kwargs):
        soul_name = kwargs.get('soul', '')
        query = kwargs.get('query', '')
        if not dream or not soul_name:
            return None
        insight = dream.check_cache(soul_name, query)
        if insight:
            return insight.precomputed_result
        return None
    rt.sense_executor.register_tool('dream_cache', dream_cache_sense)


    # ═══ Immune Engine ═══
    immune = ImmuneEngine(rt)
    immune.register(
        "Watcher",
        ImmuneConfig(
            adaptive_recovery=True,
            share_with_clones=True,
            antibody_lifespan_seconds=1800,
        ),
    )
    immune.register(
        "RiskGuard",
        ImmuneConfig(
            adaptive_recovery=True,
            share_with_clones=False,
            antibody_lifespan_seconds=3600,
        ),
    )
    rt._immune_engine = immune

    return rt


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    rt = build_runtime()
    asyncio.run(rt.run())