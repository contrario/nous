"""
NOUS Generated Code — GateAlpha
Auto-generated from .nous source. Do not edit manually.
Runtime: Python 3.11+ asyncio + NOUS Runtime
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field
from runtime import NousRuntime, ToolResult, BudgetExceededError, init_runtime

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "GateAlpha"
HEARTBEAT_SECONDS = 300
LAW_COSTCEILING = 0.1
LAW_MAXLATENCY = 30
LAW_NOLIVETRADING = True
BUDGET_PER_CYCLE = 0.1

# ═══ Message Types ═══

class Signal(BaseModel):
    pair: str
    score: float
    rsi: Optional[float]
    source: str

class Decision(BaseModel):
    action: str
    size: float
    risk: float
    sl_pct: float
    tp_pct: float

# ═══ Runtime + Channels ═══

runtime: NousRuntime = None  # type: ignore[assignment]

# ═══ Soul Definitions ═══

class Soul_Scout:
    """Soul: Scout"""

    def __init__(self, rt: NousRuntime) -> None:
        self.name = "Scout"
        self._runtime = rt
        self.model = "deepseek-r1"
        self.tier = "Tier1"
        self.senses = ['gate_alpha_scan', 'fetch_rsi', 'ddgs_search']
        self.cycle_count = 0
        self._alive = True
        self.signals = []
        self.rejected = []
        self.scan_count = 0
        self.dna_volume_threshold = 50000
        self.dna_rsi_ceiling = 70
        self.dna_temperature = 0.3

    async def instinct(self) -> None:
        """Instinct cycle for Scout"""
        tokens = await self._runtime.sense(self.name, "gate_alpha_scan")
        filtered = tokens.where((volume_24h > 50000))
        for token in filtered:
            rsi = await self._runtime.sense(self.name, "fetch_rsi", token.pair)
            if not ((rsi < 70)):
                return
            await self._runtime.channels.send("Scout_Signal", Signal(pair=token.pair, score=token.composite_score, rsi=rsi, source=self.name))
        self.scan_count += 1

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Scout"""
        etype = type(error).__name__.lower()
        if etype == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif etype == "api_error" or "api_error" in str(error).lower():
            await asyncio.sleep(HEARTBEAT_SECONDS * 1)
            return True
        elif etype == "hallucination" or "hallucination" in str(error).lower():
            self.dna_temperature = max(0, self.dna_temperature - 0.1)
            log.info(f'{self.name}: lowered temperature to {self.dna_temperature}')
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

    async def run(self) -> None:
        """Main loop for Scout"""
        log.info(f'{self.name}: soul alive')
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except BudgetExceededError as e:
                log.warning(f'{self.name}: {e}')
                await asyncio.sleep(HEARTBEAT_SECONDS)
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Quant:
    """Soul: Quant"""

    def __init__(self, rt: NousRuntime) -> None:
        self.name = "Quant"
        self._runtime = rt
        self.model = "claude-haiku"
        self.tier = "Tier0A"
        self.senses = ['calculate_kelly', 'backtest_pair']
        self.cycle_count = 0
        self._alive = True
        self.risk_score = 0.0

    async def instinct(self) -> None:
        """Instinct cycle for Quant"""
        signal = await self._runtime.channels.receive("Scout_Signal")
        kelly = await self._runtime.sense(self.name, "calculate_kelly", signal)
        risk = (1.0 - kelly.edge)
        await self._runtime.channels.send("Quant_Decision", Decision(action=("BUY" if (kelly.edge > 0.15) else "HOLD"), size=(kelly.fraction * 0.5), risk=risk, sl_pct=8.0, tp_pct=25.0))

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Quant"""
        etype = type(error).__name__.lower()
        if etype == "timeout" or "timeout" in str(error).lower():
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

    async def run(self) -> None:
        """Main loop for Quant"""
        log.info(f'{self.name}: soul alive')
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except BudgetExceededError as e:
                log.warning(f'{self.name}: {e}')
                await asyncio.sleep(HEARTBEAT_SECONDS)
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Hunter:
    """Soul: Hunter"""

    def __init__(self, rt: NousRuntime) -> None:
        self.name = "Hunter"
        self._runtime = rt
        self.model = "deepseek-r1"
        self.tier = "Tier1"
        self.senses = ['execute_paper_trade', 'check_balance']
        self.cycle_count = 0
        self._alive = True
        self.last_trade = ""

    async def instinct(self) -> None:
        """Instinct cycle for Hunter"""
        decision = await self._runtime.channels.receive("Quant_Decision")
        if not ((decision.action == "BUY")):
            return
        await self._runtime.sense(self.name, "execute_paper_trade", decision)

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Hunter"""
        etype = type(error).__name__.lower()
        if etype == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif etype == "budget_exceeded" or "budget_exceeded" in str(error).lower():
            log.info(f'{self.name}: hibernating until next cycle')
            await asyncio.sleep(HEARTBEAT_SECONDS)
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

    async def run(self) -> None:
        """Main loop for Hunter"""
        log.info(f'{self.name}: soul alive')
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except BudgetExceededError as e:
                log.warning(f'{self.name}: {e}')
                await asyncio.sleep(HEARTBEAT_SECONDS)
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Monitor:
    """Soul: Monitor"""

    def __init__(self, rt: NousRuntime) -> None:
        self.name = "Monitor"
        self._runtime = rt
        self.model = "gemini-flash"
        self.tier = "Tier2"
        self.senses = ['check_positions', 'send_telegram']
        self.cycle_count = 0
        self._alive = True
        self.alert_count = 0

    async def instinct(self) -> None:
        """Instinct cycle for Monitor"""
        signal = await self._runtime.channels.receive("Scout_Signal")
        await self._runtime.sense(self.name, "send_telegram", chat=runtime.laws.get("config.telegram_chat", ""), text="scout signal received")
        self.alert_count += 1

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Monitor"""
        etype = type(error).__name__.lower()
        if etype == "timeout" or "timeout" in str(error).lower():
            for _retry in range(1):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

    async def run(self) -> None:
        """Main loop for Monitor"""
        log.info(f'{self.name}: soul alive')
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except BudgetExceededError as e:
                log.warning(f'{self.name}: {e}')
                await asyncio.sleep(HEARTBEAT_SECONDS)
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

# ═══ Nervous System ═══

def build_topology() -> dict[str, list[str]]:
    """Build the execution DAG."""
    graph: dict[str, list[str]] = {}
    graph.setdefault("Scout", []).append("Quant")
    graph.setdefault("Quant", []).append("Hunter")
    graph.setdefault("Scout", []).append("Monitor")
    return graph

# ═══ World Runner ═══

async def run_world() -> None:
    """Boot and run world: GateAlpha"""
    global runtime
    runtime = init_runtime(
        world_name="GateAlpha",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        budget_per_cycle=BUDGET_PER_CYCLE,
    )

    runtime.register_soul("Scout", Soul_Scout(runtime))
    runtime.register_soul("Quant", Soul_Quant(runtime))
    runtime.register_soul("Hunter", Soul_Hunter(runtime))
    runtime.register_soul("Monitor", Soul_Monitor(runtime))

    topology = build_topology()
    log.info(f'Nervous system: {topology}')

    perception_rules = [
        {"trigger": {'kind': 'named', 'name': 'telegram', 'args': ['/scan']}, "action": {'kind': 'wake', 'target': 'Scout'}},
        {"trigger": {'kind': 'named', 'name': 'cron', 'args': ['*/5 * * * *']}, "action": {'kind': 'wake_all', 'target': None}},
        {"trigger": {'kind': 'simple', 'name': 'system_error', 'args': []}, "action": {'kind': 'alert', 'target': 'Telegram'}},
    ]
    await runtime.run(perception_rules)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    asyncio.run(run_world())