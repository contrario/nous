"""
NOUS Mitosis Engine — Μίτωση (Mitosi)
=======================================
Self-replicating agents with formal verification gate.
Soul detects overload → spawns verified clone → nervous system rewires.
World-first: no other framework has verified self-replication.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

log = logging.getLogger("nous.mitosis")


@dataclass
class MitosisConfig:
    trigger_fn: Callable[[dict[str, Any]], bool]
    trigger_expr: str = ""
    max_clones: int = 3
    cooldown_seconds: float = 60.0
    clone_tier: Optional[str] = None
    verify: bool = True
    retire_trigger_fn: Optional[Callable[[dict[str, Any]], bool]] = None
    retire_cooldown_seconds: float = 120.0
    min_clones: int = 0


@dataclass
class CloneRecord:
    parent_name: str
    clone_name: str
    clone_index: int
    created_at: float
    tier: str
    verified: bool
    verification_result: Optional[str] = None
    retired_at: Optional[float] = None
    retirement_reason: Optional[str] = None


@dataclass
class MitosisMetrics:
    soul_name: str
    cycle_count: int = 0
    last_latency_ms: float = 0.0
    queue_depth: int = 0
    error_count: int = 0
    memory: dict[str, Any] = field(default_factory=dict)

    def to_eval_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "cycle_count": self.cycle_count,
            "latency": self.last_latency_ms / 1000.0,
            "queue_depth": self.queue_depth,
            "error_count": self.error_count,
        }
        d.update(self.memory)
        return d


class MitosisEngine:
    """Monitors souls for overload and manages verified self-replication."""

    def __init__(
        self,
        runtime: Any,
        check_interval: float = 10.0,
    ) -> None:
        self._runtime = runtime
        self._check_interval = check_interval
        self._configs: dict[str, MitosisConfig] = {}
        self._metrics: dict[str, MitosisMetrics] = {}
        self._clones: dict[str, list[CloneRecord]] = {}
        self._last_mitosis: dict[str, float] = {}
        self._clone_factories: dict[str, Callable[..., Any]] = {}
        self._soul_listen_channels: dict[str, Optional[str]] = {}
        self._alive = True
        self._total_clones = 0
        self._total_verified = 0
        self._total_rejected = 0
        self._total_retired = 0
        self._last_retirement: dict[str, float] = {}
        self._retired_records: list[CloneRecord] = []

    def register(
        self,
        soul_name: str,
        config: MitosisConfig,
        clone_factory: Callable[..., Any],
        listen_channel: Optional[str] = None,
    ) -> None:
        self._configs[soul_name] = config
        self._metrics[soul_name] = MitosisMetrics(soul_name=soul_name)
        self._clones[soul_name] = []
        self._clone_factories[soul_name] = clone_factory
        self._soul_listen_channels[soul_name] = listen_channel
        log.info(
            f"Mitosis registered: {soul_name} "
            f"(max_clones={config.max_clones}, "
            f"cooldown={config.cooldown_seconds}s, "
            f"verify={config.verify})"
        )

    def update_metrics(
        self,
        soul_name: str,
        cycle_count: int = 0,
        latency_ms: float = 0.0,
        queue_depth: int = 0,
        error_count: int = 0,
        memory: Optional[dict[str, Any]] = None,
    ) -> None:
        if soul_name not in self._metrics:
            return
        m = self._metrics[soul_name]
        m.cycle_count = cycle_count
        m.last_latency_ms = latency_ms
        m.queue_depth = queue_depth
        m.error_count = error_count
        if memory:
            m.memory.update(memory)

    async def run(self) -> None:
        log.info(f"Mitosis engine started (interval={self._check_interval}s)")
        while self._alive:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Mitosis engine error: {e}")

    async def _check_all(self) -> None:
        for soul_name, config in self._configs.items():
            try:
                await self._check_soul(soul_name, config)
            except Exception as e:
                log.error(f"Mitosis check failed for {soul_name}: {e}")
            try:
                await self._check_retirement(soul_name, config)
            except Exception as e:
                log.error(f"Retirement check failed for {soul_name}: {e}")

    async def _check_retirement(self, soul_name: str, config: MitosisConfig) -> None:
        if config.retire_trigger_fn is None:
            return

        active_clones = self._clones.get(soul_name, [])
        if len(active_clones) <= config.min_clones:
            return

        now = time.time()
        last = self._last_retirement.get(soul_name, 0.0)
        if (now - last) < config.retire_cooldown_seconds:
            return

        metrics = self._metrics.get(soul_name)
        if not metrics:
            return

        eval_dict = metrics.to_eval_dict()
        try:
            should_retire = config.retire_trigger_fn(eval_dict)
        except Exception as e:
            log.warning(f"Retirement trigger eval failed for {soul_name}: {e}")
            return

        if not should_retire:
            return

        clone_to_retire = active_clones[-1]

        log.info(
            f"═══ RETIREMENT TRIGGERED: {soul_name} ═══\n"
            f"  Retiring: {clone_to_retire.clone_name}\n"
            f"  Metrics: cycles={metrics.cycle_count}, "
            f"latency={metrics.last_latency_ms:.0f}ms, "
            f"queue={metrics.queue_depth}\n"
            f"  Reason: retire_trigger condition met"
        )

        await self._retire_clone(soul_name, clone_to_retire)
        self._last_retirement[soul_name] = now

    async def _retire_clone(self, parent_name: str, record: CloneRecord) -> None:
        runner = self._find_runner(record.clone_name)
        if runner:
            runner.stop()
            await asyncio.sleep(0.1)
            self._runtime.remove_soul(record.clone_name)
            log.info(f"  Clone runner stopped: {record.clone_name}")

        record.retired_at = time.time()
        record.retirement_reason = "retire_trigger"
        self._retired_records.append(record)

        if parent_name in self._clones:
            self._clones[parent_name] = [
                c for c in self._clones[parent_name]
                if c.clone_name != record.clone_name
            ]

        self._total_retired += 1
        remaining = len(self._clones.get(parent_name, []))
        config = self._configs.get(parent_name)
        max_c = config.max_clones if config else "?"

        log.info(
            f"  Clone RETIRED: {record.clone_name}\n"
            f"  Lifetime: {record.retired_at - record.created_at:.1f}s\n"
            f"  Active clones of {parent_name}: {remaining}/{max_c}\n"
            f"  Total retired: {self._total_retired}\n"
            f"  ═══ RETIREMENT COMPLETE ═══"
        )

    async def _check_soul(self, soul_name: str, config: MitosisConfig) -> None:
        active_clones = len(self._clones.get(soul_name, []))
        if active_clones >= config.max_clones:
            return

        now = time.time()
        last = self._last_mitosis.get(soul_name, 0.0)
        if (now - last) < config.cooldown_seconds:
            return

        metrics = self._metrics.get(soul_name)
        if not metrics:
            return

        eval_dict = metrics.to_eval_dict()
        try:
            should_split = config.trigger_fn(eval_dict)
        except Exception as e:
            log.warning(f"Mitosis trigger eval failed for {soul_name}: {e}")
            return

        if not should_split:
            return

        log.info(
            f"═══ MITOSIS TRIGGERED: {soul_name} ═══\n"
            f"  Metrics: cycles={metrics.cycle_count}, "
            f"latency={metrics.last_latency_ms:.0f}ms, "
            f"queue={metrics.queue_depth}"
        )

        clone_index = active_clones + 1
        clone_name = f"{soul_name}_clone_{clone_index}"

        if config.verify:
            verified, report = await self._verify_clone(soul_name, clone_name, config)
            if not verified:
                self._total_rejected += 1
                log.warning(
                    f"  Mitosis REJECTED: {clone_name} failed verification\n"
                    f"  {report}"
                )
                return
            self._total_verified += 1
            log.info(f"  Verification PASSED for {clone_name}")
        else:
            report = "verification_skipped"
            log.info(f"  Verification skipped for {clone_name}")

        await self._spawn_clone(soul_name, clone_name, clone_index, config, report)
        self._last_mitosis[soul_name] = now

    async def _verify_clone(
        self,
        parent_name: str,
        clone_name: str,
        config: MitosisConfig,
    ) -> tuple[bool, str]:
        try:
            from verifier import NousVerifier, VerificationResult
            from ast_nodes import (
                NousProgram, WorldNode, SoulNode, MindNode, MemoryNode,
                InstinctNode, HealNode, NervousSystemNode, RouteNode,
                MessageNode, LawNode, LawCost, Tier,
            )

            parent_runner = self._find_runner(parent_name)
            if not parent_runner:
                return False, f"parent runner {parent_name} not found"

            parent_soul = self._build_soul_node(parent_name, config)
            clone_soul = self._build_soul_node(clone_name, config, is_clone=True)

            existing_souls = []
            existing_messages = []
            existing_routes = []

            for runner in self._runtime._runners:
                s = SoulNode(name=runner.name)
                tier_str = getattr(runner, '_tier', 'Tier1')
                try:
                    tier_enum = Tier(tier_str)
                except ValueError:
                    tier_enum = Tier.TIER1
                s.mind = MindNode(model="runtime", tier=tier_enum)
                s.heal = HealNode(rules=[])
                existing_souls.append(s)

            if clone_soul.name not in {s.name for s in existing_souls}:
                existing_souls.append(clone_soul)

            cost_ceiling = getattr(self._runtime, 'cost_ceiling', 0.10)
            program = NousProgram(
                world=WorldNode(
                    name="mitosis_verification",
                    laws=[LawNode(name="cost_ceiling", expr=LawCost(amount=cost_ceiling))],
                ),
                souls=existing_souls,
                messages=existing_messages,
                nervous_system=NervousSystemNode(routes=existing_routes) if existing_routes else None,
            )

            verifier = NousVerifier(program)
            result = verifier.verify()

            if result.ok:
                return True, f"VERIFIED: {len(result.proven)} proven, 0 errors"
            else:
                error_msgs = "; ".join(str(e) for e in result.errors[:3])
                return False, f"FAILED: {len(result.errors)} errors — {error_msgs}"

        except Exception as e:
            log.error(f"Verification exception for {clone_name}: {e}")
            return False, f"verification_error: {e}"

    def _build_soul_node(
        self,
        name: str,
        config: MitosisConfig,
        is_clone: bool = False,
    ) -> Any:
        from ast_nodes import SoulNode, MindNode, HealNode, Tier

        tier_str = config.clone_tier if (is_clone and config.clone_tier) else "Tier1"
        try:
            tier_enum = Tier(tier_str)
        except ValueError:
            tier_enum = Tier.TIER1

        return SoulNode(
            name=name,
            mind=MindNode(model="cloned", tier=tier_enum),
            heal=HealNode(rules=[]),
        )

    def _find_runner(self, name: str) -> Any:
        for runner in self._runtime._runners:
            if runner.name == name:
                return runner
        return None

    async def _spawn_clone(
        self,
        parent_name: str,
        clone_name: str,
        clone_index: int,
        config: MitosisConfig,
        verification_result: str,
    ) -> None:
        from runtime import SoulRunner, SoulWakeStrategy

        factory = self._clone_factories.get(parent_name)
        if not factory:
            log.error(f"No clone factory for {parent_name}")
            return

        clone_soul = factory(clone_name, config.clone_tier)

        parent_runner = self._find_runner(parent_name)
        if not parent_runner:
            log.error(f"Parent runner {parent_name} not found")
            return

        parent_listen = self._soul_listen_channels.get(parent_name)

        clone_runner = SoulRunner(
            name=clone_name,
            wake_strategy=parent_runner.wake_strategy,
            instinct_fn=clone_soul.instinct,
            heal_fn=clone_soul.heal,
            listen_channel=parent_listen,
            heartbeat_seconds=parent_runner._heartbeat,
            tier=config.clone_tier or parent_runner._tier,
        )

        self._runtime.add_soul(clone_runner)

        record = CloneRecord(
            parent_name=parent_name,
            clone_name=clone_name,
            clone_index=clone_index,
            created_at=time.time(),
            tier=config.clone_tier or parent_runner._tier,
            verified=config.verify,
            verification_result=verification_result,
        )
        self._clones[parent_name].append(record)
        self._total_clones += 1

        asyncio.create_task(clone_runner.run(self._runtime.channels))

        log.info(
            f"  Clone DEPLOYED: {clone_name}\n"
            f"  Tier: {record.tier} | Verified: {record.verified}\n"
            f"  Active clones of {parent_name}: "
            f"{len(self._clones[parent_name])}/{config.max_clones}\n"
            f"  ═══ MITOSIS COMPLETE ═══"
        )

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_clones": self._total_clones,
            "total_verified": self._total_verified,
            "total_rejected": self._total_rejected,
            "total_retired": self._total_retired,
            "souls": {},
        }
        for soul_name, clones in self._clones.items():
            metrics = self._metrics.get(soul_name)
            result["souls"][soul_name] = {
                "active_clones": len(clones),
                "max_clones": self._configs[soul_name].max_clones,
                "clones": [
                    {
                        "name": c.clone_name,
                        "tier": c.tier,
                        "verified": c.verified,
                        "created_at": c.created_at,
                    }
                    for c in clones
                ],
                "metrics": metrics.to_eval_dict() if metrics else {},
            }
        return result

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Mitosis Status ═══")
        lines.append("")
        lines.append(f"  Total clones spawned:  {self._total_clones}")
        lines.append(f"  Verified:              {self._total_verified}")
        lines.append(f"  Rejected:              {self._total_rejected}")
        lines.append(f"  Retired:               {self._total_retired}")
        lines.append("")

        for soul_name, clones in self._clones.items():
            config = self._configs[soul_name]
            metrics = self._metrics.get(soul_name)
            lines.append(f"  ── {soul_name} ──")
            lines.append(f"  Max clones:    {config.max_clones}")
            lines.append(f"  Cooldown:      {config.cooldown_seconds}s")
            lines.append(f"  Verify:        {config.verify}")
            if metrics:
                ed = metrics.to_eval_dict()
                lines.append(f"  Cycles:        {ed.get('cycle_count', 0)}")
                lines.append(f"  Latency:       {ed.get('latency', 0):.3f}s")
                lines.append(f"  Queue depth:   {ed.get('queue_depth', 0)}")
            lines.append(f"  Min clones:    {config.min_clones}")
            has_retire = config.retire_trigger_fn is not None
            lines.append(f"  Retirement:    {'enabled' if has_retire else 'disabled'}")
            if has_retire:
                lines.append(f"  Retire CD:     {config.retire_cooldown_seconds}s")
            lines.append(f"  Active clones: {len(clones)}/{config.max_clones}")
            for c in clones:
                v_icon = "✓" if c.verified else "○"
                age = time.time() - c.created_at
                lines.append(f"    {v_icon} {c.clone_name} @ {c.tier} (age {age:.0f}s)")
            if self._retired_records:
                parent_retired = [r for r in self._retired_records if r.parent_name == soul_name]
                if parent_retired:
                    lines.append(f"  Retired clones: {len(parent_retired)}")
                    for r in parent_retired[-3:]:
                        lifetime = (r.retired_at or 0) - r.created_at
                        lines.append(f"    ✗ {r.clone_name} (lived {lifetime:.0f}s)")
            lines.append("")

        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
