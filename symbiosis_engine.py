"""
NOUS Symbiosis Engine — Συμβίωση (Symviosi)
=============================================
Bonds between souls that share memory and evolve together.
SharedMemoryPool: async-safe shared state with instant propagation.
Co-evolution: bonded souls with DNA mutate in lockstep.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger("nous.symbiosis")


@dataclass
class BondConfig:
    soul_name: str
    bond_with: list[str]
    shared_fields: list[str]
    sync_interval_seconds: float = 10.0
    evolve_together: bool = False


@dataclass
class SharedField:
    name: str
    value: Any = None
    last_writer: str = ""
    last_write_time: float = 0.0
    write_count: int = 0


class SharedMemoryPool:
    """Async-safe shared memory between bonded souls."""

    def __init__(self) -> None:
        self._fields: dict[str, SharedField] = {}
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[Callable[[str, Any], None]]] = {}

    async def write(self, field_name: str, value: Any, writer: str) -> None:
        async with self._lock:
            if field_name not in self._fields:
                self._fields[field_name] = SharedField(name=field_name)
            sf = self._fields[field_name]
            sf.value = value
            sf.last_writer = writer
            sf.last_write_time = time.time()
            sf.write_count += 1

        for cb in self._subscribers.get(field_name, []):
            try:
                cb(field_name, value)
            except Exception as e:
                log.warning(f"Shared memory subscriber error: {e}")

    async def read(self, field_name: str) -> Any:
        async with self._lock:
            sf = self._fields.get(field_name)
            return sf.value if sf else None

    async def read_all(self) -> dict[str, Any]:
        async with self._lock:
            return {name: sf.value for name, sf in self._fields.items()}

    def subscribe(self, field_name: str, callback: Callable[[str, Any], None]) -> None:
        self._subscribers.setdefault(field_name, []).append(callback)

    def status(self) -> dict[str, Any]:
        return {
            name: {
                "value": sf.value,
                "last_writer": sf.last_writer,
                "writes": sf.write_count,
            }
            for name, sf in self._fields.items()
        }


@dataclass
class BondRecord:
    soul_a: str
    soul_b: str
    shared_fields: list[str]
    pool: SharedMemoryPool
    created_at: float = 0.0
    sync_count: int = 0


class SymbiosisEngine:
    """Manages bonds between souls: shared memory + co-evolution."""

    def __init__(self, runtime: Any, sync_interval: float = 10.0) -> None:
        self._runtime = runtime
        self._sync_interval = sync_interval
        self._configs: dict[str, BondConfig] = {}
        self._pools: dict[str, SharedMemoryPool] = {}
        self._bonds: list[BondRecord] = []
        self._alive = True
        self._total_syncs = 0
        self._cluster_map: dict[str, str] = {}

    def register(self, config: BondConfig) -> None:
        self._configs[config.soul_name] = config
        cluster_id = self._find_or_create_cluster(config.soul_name, config.bond_with)
        self._cluster_map[config.soul_name] = cluster_id

        if cluster_id not in self._pools:
            self._pools[cluster_id] = SharedMemoryPool()

        pool = self._pools[cluster_id]
        for field_name in config.shared_fields:
            for bond_name in config.bond_with:
                bond_key = tuple(sorted([config.soul_name, bond_name]))
                existing = any(
                    b.soul_a == bond_key[0] and b.soul_b == bond_key[1]
                    for b in self._bonds
                )
                if not existing:
                    self._bonds.append(BondRecord(
                        soul_a=bond_key[0],
                        soul_b=bond_key[1],
                        shared_fields=list(config.shared_fields),
                        pool=pool,
                        created_at=time.time(),
                    ))

        log.info(
            f"Symbiosis registered: {config.soul_name} "
            f"bonds={config.bond_with}, "
            f"shared={config.shared_fields}, "
            f"cluster={cluster_id}"
        )

    def _find_or_create_cluster(self, soul: str, bonds: list[str]) -> str:
        for name in [soul] + bonds:
            if name in self._cluster_map:
                return self._cluster_map[name]
        return f"cluster_{len(self._pools)}"

    def get_pool(self, soul_name: str) -> Optional[SharedMemoryPool]:
        cluster_id = self._cluster_map.get(soul_name)
        if cluster_id:
            return self._pools.get(cluster_id)
        return None

    async def sync_soul_to_pool(self, soul_name: str, memory: dict[str, Any]) -> None:
        config = self._configs.get(soul_name)
        if not config:
            return
        pool = self.get_pool(soul_name)
        if not pool:
            return
        for field_name in config.shared_fields:
            if field_name in memory:
                await pool.write(field_name, memory[field_name], soul_name)

    async def sync_pool_to_soul(self, soul_name: str) -> dict[str, Any]:
        config = self._configs.get(soul_name)
        if not config:
            return {}
        pool = self.get_pool(soul_name)
        if not pool:
            return {}
        updates: dict[str, Any] = {}
        for field_name in config.shared_fields:
            val = await pool.read(field_name)
            if val is not None:
                updates[field_name] = val
        return updates

    async def run(self) -> None:
        log.info(
            f"Symbiosis engine started "
            f"({len(self._configs)} souls, "
            f"{len(self._bonds)} bonds, "
            f"{len(self._pools)} clusters)"
        )
        while self._alive:
            try:
                await asyncio.sleep(self._sync_interval)
                await self._sync_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Symbiosis engine error: {e}")

        log.info(f"Symbiosis engine stopped: {self._total_syncs} syncs")

    async def _sync_all(self) -> None:
        for soul_name, config in self._configs.items():
            runner = self._find_runner(soul_name)
            if not runner:
                continue
            memory = self._extract_memory(runner)
            await self.sync_soul_to_pool(soul_name, memory)
            updates = await self.sync_pool_to_soul(soul_name)
            self._apply_updates(runner, updates)
            self._total_syncs += 1

    def _find_runner(self, name: str) -> Any:
        for runner in self._runtime._runners:
            if runner.name == name:
                return runner
        return None

    def _extract_memory(self, runner: Any) -> dict[str, Any]:
        instinct_fn = runner._instinct
        soul_obj = getattr(instinct_fn, '__self__', None)
        if soul_obj is None:
            return {}
        result: dict[str, Any] = {}
        for config in self._configs.values():
            if config.soul_name == runner.name:
                for field_name in config.shared_fields:
                    if hasattr(soul_obj, field_name):
                        result[field_name] = getattr(soul_obj, field_name)
        return result

    def _apply_updates(self, runner: Any, updates: dict[str, Any]) -> None:
        if not updates:
            return
        instinct_fn = runner._instinct
        soul_obj = getattr(instinct_fn, '__self__', None)
        if soul_obj is None:
            return
        for field_name, value in updates.items():
            if hasattr(soul_obj, field_name):
                setattr(soul_obj, field_name, value)

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        return {
            "souls": len(self._configs),
            "bonds": len(self._bonds),
            "clusters": len(self._pools),
            "total_syncs": self._total_syncs,
            "pools": {
                cid: pool.status()
                for cid, pool in self._pools.items()
            },
        }

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Symbiosis Status ═══")
        lines.append("")
        lines.append(f"  Bonded souls:     {len(self._configs)}")
        lines.append(f"  Active bonds:     {len(self._bonds)}")
        lines.append(f"  Clusters:         {len(self._pools)}")
        lines.append(f"  Total syncs:      {self._total_syncs}")
        lines.append("")
        for bond in self._bonds:
            lines.append(f"  {bond.soul_a} ⇌ {bond.soul_b}")
            lines.append(f"    Shared: {', '.join(bond.shared_fields)}")
            lines.append(f"    Syncs: {bond.sync_count}")
        for cid, pool in self._pools.items():
            ps = pool.status()
            if ps:
                lines.append(f"  Cluster {cid}:")
                for fname, info in ps.items():
                    lines.append(f"    {fname} = {info['value']} (by {info['last_writer']}, {info['writes']} writes)")
        lines.append("")
        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
