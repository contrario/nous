"""
NOUS Generated Code — Command
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

try:
    from runtime import init_runtime, NousRuntime
except ImportError:
    init_runtime = None
    NousRuntime = None

# ═══ World Laws ═══

WORLD_NAME = "Command"
HEARTBEAT_SECONDS = 300
LAW_COSTCEILING = 0.1  # USD per cycle

import os
WORLD_CONFIG = {
    "telegram_chat": os.environ.get("TELEGRAM_CHAT_ID", ""),
    "telegram_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
}

# ═══ Message Types ═══

class Alert(BaseModel):
    level: str
    detail: str
    source: str

class Response(BaseModel):
    action: str
    target: str

Alert.model_rebuild()
Response.model_rebuild()

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

channels = None  # Set by run_world() from runtime
cross_bus = None  # Set by MultiWorldRunner

# ═══ Soul Definitions ═══

class Soul_Dispatcher:
    """Soul: Dispatcher"""

    def __init__(self) -> None:
        self.name = "Dispatcher"
        self.model = "deepseek-r1"
        self.tier = "Tier1"
        self.senses = ['send_telegram']
        self.cycle_count = 0
        self._alive = True
        self.handled = 0
        self._runtime = None

    async def _sense_send_telegram(self, *args, **kwargs) -> Any:
        return await self._runtime.sense(self.name, "send_telegram", *args, **kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Dispatcher"""
        if (alert.level == "critical"):
            await channels.send("Dispatcher_Response", Response(action="escalate", target=alert.source))
            self.handled += 1

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Dispatcher"""
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
        """Main loop for Dispatcher"""
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

class Soul_Logger:
    """Soul: Logger"""

    def __init__(self) -> None:
        self.name = "Logger"
        self.model = "deepseek-r1"
        self.tier = "Tier2"
        self.senses = ['write_log']
        self.cycle_count = 0
        self._alive = True
        self._runtime = None

    async def _sense_write_log(self, *args, **kwargs) -> Any:
        return await self._runtime.sense(self.name, "write_log", *args, **kwargs)

    async def instinct(self) -> None:
        """Instinct cycle for Logger"""
        await self._sense_write_log(entry=resp.action)

    async def heal(self, error: Exception) -> bool:
        """Error recovery for Logger"""
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
        log.warning(f'{self.name}: unhandled error: {error}')
        return False

    async def run(self) -> None:
        """Main loop for Logger"""
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
    graph.setdefault("Dispatcher", []).append("Logger")
    return graph

# ═══ World Runner ═══

async def run_world() -> None:
    """Boot and run world: Command"""
    log.info('Booting world: Command')

    # Initialize runtime
    global channels
    runtime = init_runtime(
        world_name="Command",
        heartbeat_seconds=HEARTBEAT_SECONDS,
        budget_per_cycle=0.1,
    )
    channels = runtime.channels

    # Spawn souls
    souls = {}
    souls["Dispatcher"] = Soul_Dispatcher()
    runtime.register_soul("Dispatcher", souls["Dispatcher"])
    souls["Logger"] = Soul_Logger()
    runtime.register_soul("Logger", souls["Logger"])

    topology = build_topology()
    log.info(f'Nervous system: {topology}')

    # Run via runtime
    await runtime.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )
    asyncio.run(run_world())