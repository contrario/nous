"""
NOUS Metabolism Engine — Μεταβολισμός (Metavolismos)
=====================================================
Energy and fatigue system for souls.
Energy depletes per cycle, recovers during idle.
Low energy → downgrade tier, extend heartbeat, skip optional work.
Critical energy → hibernate until recovered.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("nous.metabolism")


@dataclass
class MetabolismConfig:
    soul_name: str
    max_energy: int = 100
    energy_per_cycle: float = 5.0
    recovery_rate: float = 2.0
    fatigue_tier: Optional[str] = None
    hibernate_threshold: int = 10
    recovery_idle_sec: int = 30
    primary_tier: str = "Tier1"
    primary_heartbeat: float = 300.0


class EnergyState:
    ACTIVE = "active"
    FATIGUED = "fatigued"
    HIBERNATING = "hibernating"
    RECOVERING = "recovering"


@dataclass
class SoulEnergy:
    soul_name: str
    energy: float = 100.0
    max_energy: int = 100
    state: str = EnergyState.ACTIVE
    cycles_run: int = 0
    hibernation_count: int = 0
    fatigue_count: int = 0
    last_cycle_time: float = 0.0
    last_recovery_time: float = 0.0


class MetabolismEngine:

    def __init__(self, runtime: Any, check_interval: float = 5.0) -> None:
        self._runtime = runtime
        self._check_interval = check_interval
        self._configs: dict[str, MetabolismConfig] = {}
        self._energies: dict[str, SoulEnergy] = {}
        self._alive = True
        self._total_hibernations = 0
        self._total_fatigues = 0

    def register(self, config: MetabolismConfig) -> None:
        self._configs[config.soul_name] = config
        self._energies[config.soul_name] = SoulEnergy(
            soul_name=config.soul_name,
            energy=float(config.max_energy),
            max_energy=config.max_energy,
        )
        log.info(
            f"Metabolism registered: {config.soul_name} "
            f"(energy={config.max_energy}, drain={config.energy_per_cycle}/cycle, "
            f"recovery={config.recovery_rate}/s, hibernate<{config.hibernate_threshold})"
        )

    def drain(self, soul_name: str) -> None:
        config = self._configs.get(soul_name)
        energy = self._energies.get(soul_name)
        if not config or not energy:
            return
        energy.energy = max(0, energy.energy - config.energy_per_cycle)
        energy.cycles_run += 1
        energy.last_cycle_time = time.time()

    def get_energy(self, soul_name: str) -> float:
        e = self._energies.get(soul_name)
        return e.energy if e else 100.0

    def get_state(self, soul_name: str) -> str:
        e = self._energies.get(soul_name)
        return e.state if e else EnergyState.ACTIVE

    def should_skip_cycle(self, soul_name: str) -> bool:
        e = self._energies.get(soul_name)
        if not e:
            return False
        return e.state == EnergyState.HIBERNATING

    def get_effective_tier(self, soul_name: str) -> Optional[str]:
        config = self._configs.get(soul_name)
        energy = self._energies.get(soul_name)
        if not config or not energy:
            return None
        if energy.state == EnergyState.FATIGUED and config.fatigue_tier:
            return config.fatigue_tier
        return None

    def get_effective_heartbeat(self, soul_name: str) -> Optional[float]:
        energy = self._energies.get(soul_name)
        config = self._configs.get(soul_name)
        if not energy or not config:
            return None
        if energy.state == EnergyState.FATIGUED:
            return config.primary_heartbeat * 2.0
        return None

    async def run(self) -> None:
        log.info(f"Metabolism engine started ({len(self._configs)} souls)")
        while self._alive:
            try:
                await asyncio.sleep(self._check_interval)
                self._recover_all()
                self._update_states()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Metabolism engine error: {e}")
        log.info(
            f"Metabolism engine stopped: "
            f"{self._total_hibernations} hibernations, "
            f"{self._total_fatigues} fatigues"
        )

    def _recover_all(self) -> None:
        now = time.time()
        for soul_name, config in self._configs.items():
            energy = self._energies[soul_name]
            if energy.energy >= config.max_energy:
                continue
            idle_time = now - energy.last_cycle_time if energy.last_cycle_time > 0 else 0
            if idle_time >= config.recovery_idle_sec or energy.state == EnergyState.HIBERNATING:
                recovery = config.recovery_rate * self._check_interval
                old_energy = energy.energy
                energy.energy = min(config.max_energy, energy.energy + recovery)
                if energy.energy > old_energy:
                    energy.last_recovery_time = now

    def _update_states(self) -> None:
        for soul_name, config in self._configs.items():
            energy = self._energies[soul_name]
            old_state = energy.state
            pct = (energy.energy / config.max_energy) * 100

            if energy.energy <= config.hibernate_threshold:
                energy.state = EnergyState.HIBERNATING
            elif pct <= 30:
                energy.state = EnergyState.FATIGUED
            elif pct <= 60:
                energy.state = EnergyState.RECOVERING
            else:
                energy.state = EnergyState.ACTIVE

            if old_state != energy.state:
                if energy.state == EnergyState.HIBERNATING:
                    self._total_hibernations += 1
                    energy.hibernation_count += 1
                    log.warning(
                        f"═══ HIBERNATE: {soul_name} ═══ "
                        f"energy={energy.energy:.1f}/{config.max_energy}"
                    )
                elif energy.state == EnergyState.FATIGUED:
                    self._total_fatigues += 1
                    energy.fatigue_count += 1
                    tier_info = f" → {config.fatigue_tier}" if config.fatigue_tier else ""
                    log.info(
                        f"  Fatigue: {soul_name} energy={energy.energy:.1f}{tier_info}"
                    )
                elif energy.state == EnergyState.ACTIVE and old_state != EnergyState.ACTIVE:
                    log.info(
                        f"  Recovered: {soul_name} energy={energy.energy:.1f}/{config.max_energy}"
                    )

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_hibernations": self._total_hibernations,
            "total_fatigues": self._total_fatigues,
            "souls": {},
        }
        for soul_name, energy in self._energies.items():
            config = self._configs[soul_name]
            result["souls"][soul_name] = {
                "energy": round(energy.energy, 1),
                "max_energy": config.max_energy,
                "pct": round((energy.energy / config.max_energy) * 100, 1),
                "state": energy.state,
                "cycles": energy.cycles_run,
                "hibernations": energy.hibernation_count,
                "fatigues": energy.fatigue_count,
            }
        return result

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Metabolism Status ═══")
        lines.append("")
        lines.append(f"  Total hibernations: {self._total_hibernations}")
        lines.append(f"  Total fatigues:     {self._total_fatigues}")
        lines.append("")
        for soul_name, energy in self._energies.items():
            config = self._configs[soul_name]
            pct = (energy.energy / config.max_energy) * 100
            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            state_icon = {"active": "●", "fatigued": "◐", "hibernating": "○", "recovering": "◑"}.get(energy.state, "?")
            lines.append(f"  {state_icon} {soul_name}")
            lines.append(f"    [{bar}] {energy.energy:.0f}/{config.max_energy} ({pct:.0f}%)")
            lines.append(f"    State: {energy.state} | Cycles: {energy.cycles_run}")
            if config.fatigue_tier:
                lines.append(f"    Fatigue tier: {config.fatigue_tier}")
            lines.append("")
        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
