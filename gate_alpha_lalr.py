"""
NOUS Generated Code — GateAlpha
Auto-generated from .nous source. Do not edit manually.
Runtime: Python 3.11+ asyncio
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = object  # fallback
    def Field(**kw): return kw.get('default')

log = logging.getLogger('nous.runtime')

# ═══ World Laws ═══

WORLD_NAME = "GateAlpha"
HEARTBEAT_SECONDS = 300
LAW_COSTCEILING = 0.1  # USD per cycle
LAW_MAXLATENCY = 30  # s
LAW_NOLIVETRADING = True

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

# ═══ Channel Registry ═══

class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: dict[str, asyncio.Queue] = {}

    def get(self, key: str) -> asyncio.Queue:
        if key not in self._channels:
            self._channels[key] = asyncio.Queue(maxsize=100)
        return self._channels[key]

    async def send(self, key: str, message: Any) -> None:
        await self.get(key).put(message)
        log.debug(f'Channel {key}: message sent')

    async def receive(self, key: str, timeout: float = 30.0) -> Any:
        try:
            return await asyncio.wait_for(self.get(key).get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f'Channel {key}: receive timeout after {timeout}s')

channels = ChannelRegistry()

# ═══ Soul Definitions ═══

class Soul_Scout:
    """Soul: Scout"""

    def __init__(self) -> None:
        self.name = "Scout"
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
        tokens = await self._sense_gate_alpha_scan()
        filtered = tokens.where((volume_24h > 50000))
        for token in filtered:
            rsi = await self._sense_fetch_rsi(token.pair)
            if not ((rsi < 70)):
                return  # guard failed
            await channels.send("Scout_Signal", Signal(pair=token.pair, score=token.composite_score, rsi=rsi, source=self))
        self.scan_count += 1

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Scout"""
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "api_error" or "api_error" in str(error).lower():
            await asyncio.sleep(HEARTBEAT_SECONDS * 1)
            return True
        elif error_type == "hallucination" or "hallucination" in str(error).lower():
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
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Quant:
    """Soul: Quant"""

    def __init__(self) -> None:
        self.name = "Quant"
        self.model = "claude-haiku"
        self.tier = "Tier0A"
        self.senses = ['calculate_kelly', 'backtest_pair']
        self.cycle_count = 0
        self._alive = True
        self.risk_score = 0.0

    async def instinct(self) -> None:
        """Instinct cycle for Quant"""
        signal = await channels.receive("Scout_Signal")
        kelly = await self._sense_calculate_kelly(signal)
        risk = 1.0
        await channels.send("Quant_Decision", Decision(action=("BUY" if (kelly.edge > 0.15) else "HOLD"), size=(kelly.fraction * 0.5), risk=risk, sl_pct=8.0, tp_pct=25.0))

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Quant"""
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

    async def run(self) -> None:
        """Main loop for Quant"""
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Hunter:
    """Soul: Hunter"""

    def __init__(self) -> None:
        self.name = "Hunter"
        self.model = "deepseek-r1"
        self.tier = "Tier1"
        self.senses = ['execute_paper_trade', 'check_balance']
        self.cycle_count = 0
        self._alive = True
        self.last_trade = ""

    async def instinct(self) -> None:
        """Instinct cycle for Hunter"""
        decision = await channels.receive("Quant_Decision")
        if not ((decision.action == "BUY")):
            return  # guard failed
        await self._sense_execute_paper_trade(decision)

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Hunter"""
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
            for _retry in range(2):
                await asyncio.sleep(2 ** _retry)
                try:
                    await self.instinct()
                    break
                except Exception:
                    continue
            return True
        elif error_type == "budget_exceeded" or "budget_exceeded" in str(error).lower():
            log.info(f'{self.name}: hibernating until next cycle')
            await asyncio.sleep(HEARTBEAT_SECONDS)
            return True
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

    async def run(self) -> None:
        """Main loop for Hunter"""
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

class Soul_Monitor:
    """Soul: Monitor"""

    def __init__(self) -> None:
        self.name = "Monitor"
        self.model = "gemini-flash"
        self.tier = "Tier2"
        self.senses = ['check_positions', 'send_telegram']
        self.cycle_count = 0
        self._alive = True
        self.alert_count = 0

    async def instinct(self) -> None:
        """Instinct cycle for Monitor"""
        signal = await channels.receive("Scout_Signal")
        await self._sense_send_telegram(chat=world_config.config.telegram_chat, text="scout signal received")
        self.alert_count += 1

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Monitor"""
        error_type = type(error).__name__.lower()
        if error_type == "timeout" or "timeout" in str(error).lower():
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
        while self._alive:
            try:
                await self.instinct()
                self.cycle_count += 1
                log.info(f'{self.name}: cycle {self.cycle_count} complete')
            except Exception as e:
                log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')
                recovered = await self.heal(e)
                if not recovered:
                    log.critical(f'{self.name}: unrecoverable error, stopping')
                    self._alive = False
            await asyncio.sleep(HEARTBEAT_SECONDS)

# ═══ Nervous System ═══

def build_topology() -> dict[str, list[str]]:
    """Build the execution DAG from nervous_system declaration."""
    graph: dict[str, list[str]] = {}
    graph.setdefault("Scout", []).append("Quant")
    graph.setdefault("Quant", []).append("Hunter")
    graph.setdefault("Scout", []).append("Monitor")
    return graph

# ═══ World Runner ═══

async def run_world() -> None:
    """Boot and run world: GateAlpha"""
    log.info(f'Booting world: GateAlpha')

    # Spawn souls
    souls = {}
    souls["Scout"] = Soul_Scout()
    log.info(f'Spawned soul: Scout')
    souls["Quant"] = Soul_Quant()
    log.info(f'Spawned soul: Quant')
    souls["Hunter"] = Soul_Hunter()
    log.info(f'Spawned soul: Hunter')
    souls["Monitor"] = Soul_Monitor()
    log.info(f'Spawned soul: Monitor')

    topology = build_topology()
    log.info(f'Nervous system: {topology}')

    # Run all souls concurrently
    async with asyncio.TaskGroup() as tg:
        tg.create_task(souls["Scout"].run())
        tg.create_task(souls["Quant"].run())
        tg.create_task(souls["Hunter"].run())
        tg.create_task(souls["Monitor"].run())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    asyncio.run(run_world())