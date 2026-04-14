"""
NOUS Consciousness Engine — Συνείδηση (Syneidisi)
===================================================
Self-reflection and goal tracking for souls.
Souls set goals, track progress, reflect on performance,
and adjust behavior via introspection cycles.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger("nous.consciousness")


@dataclass
class GoalState:
    name: str
    progress: float = 0.0
    target: float = 1.0
    achieved: bool = False
    last_evaluated: float = 0.0
    evaluations: int = 0


@dataclass
class SelfModel:
    soul_name: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    avg_cycle_time_ms: float = 0.0
    error_rate: float = 0.0
    cycles_since_reflection: int = 0
    total_reflections: int = 0
    last_reflection_time: float = 0.0
    last_insight: str = ""
    behavioral_adjustments: int = 0


@dataclass
class ConsciousnessConfig:
    soul_name: str
    goals: list[str]
    reflect_every: int = 10
    self_model_enabled: bool = True
    goal_threshold: float = 0.7
    introspection_depth: int = 3


class ConsciousnessEngine:

    def __init__(self, runtime: Any, check_interval: float = 10.0) -> None:
        self._runtime = runtime
        self._check_interval = check_interval
        self._configs: dict[str, ConsciousnessConfig] = {}
        self._goals: dict[str, list[GoalState]] = {}
        self._models: dict[str, SelfModel] = {}
        self._alive = True
        self._total_reflections = 0
        self._total_goals_achieved = 0

    def register(self, config: ConsciousnessConfig) -> None:
        self._configs[config.soul_name] = config
        self._goals[config.soul_name] = [
            GoalState(name=g) for g in config.goals
        ]
        self._models[config.soul_name] = SelfModel(soul_name=config.soul_name)
        log.info(
            f"Consciousness registered: {config.soul_name} "
            f"(goals={config.goals}, reflect_every={config.reflect_every})"
        )

    def record_cycle(self, soul_name: str, latency_ms: float, error: bool = False) -> None:
        model = self._models.get(soul_name)
        if not model:
            return
        model.cycles_since_reflection += 1
        n = model.total_reflections * model.cycles_since_reflection
        if n > 0:
            model.avg_cycle_time_ms = (
                (model.avg_cycle_time_ms * (n - 1) + latency_ms) / n
            )
        else:
            model.avg_cycle_time_ms = latency_ms
        if error:
            total_cycles = model.cycles_since_reflection + (model.total_reflections * self._configs[soul_name].reflect_every)
            model.error_rate = (model.error_rate * (total_cycles - 1) + 1.0) / total_cycles

    def evaluate_goal(self, soul_name: str, goal_name: str, progress: float) -> None:
        goals = self._goals.get(soul_name, [])
        for g in goals:
            if g.name == goal_name:
                g.progress = min(1.0, max(0.0, progress))
                g.evaluations += 1
                g.last_evaluated = time.time()
                config = self._configs.get(soul_name)
                if config and g.progress >= config.goal_threshold and not g.achieved:
                    g.achieved = True
                    self._total_goals_achieved += 1
                    log.info(f"  Goal ACHIEVED: {soul_name}/{goal_name} ({g.progress:.0%})")
                return

    def should_reflect(self, soul_name: str) -> bool:
        config = self._configs.get(soul_name)
        model = self._models.get(soul_name)
        if not config or not model:
            return False
        return model.cycles_since_reflection >= config.reflect_every

    async def reflect(self, soul_name: str) -> dict[str, Any]:
        config = self._configs.get(soul_name)
        model = self._models.get(soul_name)
        goals = self._goals.get(soul_name, [])
        if not config or not model:
            return {}

        model.total_reflections += 1
        model.cycles_since_reflection = 0
        model.last_reflection_time = time.time()
        self._total_reflections += 1

        achieved = [g for g in goals if g.achieved]
        pending = [g for g in goals if not g.achieved]
        avg_progress = sum(g.progress for g in goals) / len(goals) if goals else 0

        reflection = {
            "soul": soul_name,
            "reflection_number": model.total_reflections,
            "goals_total": len(goals),
            "goals_achieved": len(achieved),
            "goals_pending": len(pending),
            "avg_progress": round(avg_progress, 3),
            "avg_cycle_time_ms": round(model.avg_cycle_time_ms, 1),
            "error_rate": round(model.error_rate, 4),
            "strengths": list(model.strengths),
            "weaknesses": list(model.weaknesses),
        }

        if config.self_model_enabled:
            if model.error_rate < 0.05:
                if "low_error_rate" not in model.strengths:
                    model.strengths.append("low_error_rate")
            elif model.error_rate > 0.2:
                if "high_error_rate" not in model.weaknesses:
                    model.weaknesses.append("high_error_rate")

            if model.avg_cycle_time_ms < 100:
                if "fast_execution" not in model.strengths:
                    model.strengths.append("fast_execution")
            elif model.avg_cycle_time_ms > 5000:
                if "slow_execution" not in model.weaknesses:
                    model.weaknesses.append("slow_execution")

            if avg_progress < 0.3 and model.total_reflections > 2:
                if "low_goal_progress" not in model.weaknesses:
                    model.weaknesses.append("low_goal_progress")
                    model.behavioral_adjustments += 1

            model.last_insight = (
                f"Reflection #{model.total_reflections}: "
                f"{len(achieved)}/{len(goals)} goals achieved, "
                f"avg progress {avg_progress:.0%}, "
                f"error rate {model.error_rate:.1%}"
            )

        log.info(
            f"═══ REFLECTION: {soul_name} ═══\n"
            f"  Reflection #{model.total_reflections}\n"
            f"  Goals: {len(achieved)}/{len(goals)} achieved\n"
            f"  Avg progress: {avg_progress:.0%}\n"
            f"  Avg cycle: {model.avg_cycle_time_ms:.0f}ms\n"
            f"  Error rate: {model.error_rate:.1%}\n"
            f"  Strengths: {model.strengths}\n"
            f"  Weaknesses: {model.weaknesses}\n"
            f"  ═══ REFLECTION COMPLETE ═══"
        )

        return reflection

    async def run(self) -> None:
        log.info(f"Consciousness engine started ({len(self._configs)} souls)")
        while self._alive:
            try:
                await asyncio.sleep(self._check_interval)
                for soul_name in self._configs:
                    if self.should_reflect(soul_name):
                        await self.reflect(soul_name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Consciousness engine error: {e}")
        log.info(
            f"Consciousness engine stopped: "
            f"{self._total_reflections} reflections, "
            f"{self._total_goals_achieved} goals achieved"
        )

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_reflections": self._total_reflections,
            "total_goals_achieved": self._total_goals_achieved,
            "souls": {},
        }
        for soul_name in self._configs:
            model = self._models[soul_name]
            goals = self._goals[soul_name]
            result["souls"][soul_name] = {
                "reflections": model.total_reflections,
                "adjustments": model.behavioral_adjustments,
                "strengths": model.strengths,
                "weaknesses": model.weaknesses,
                "insight": model.last_insight,
                "goals": {
                    g.name: {
                        "progress": round(g.progress, 3),
                        "achieved": g.achieved,
                        "evaluations": g.evaluations,
                    }
                    for g in goals
                },
            }
        return result

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Consciousness Status ═══")
        lines.append("")
        lines.append(f"  Total reflections:    {self._total_reflections}")
        lines.append(f"  Goals achieved:       {self._total_goals_achieved}")
        lines.append("")
        for soul_name in self._configs:
            model = self._models[soul_name]
            goals = self._goals[soul_name]
            lines.append(f"  ── {soul_name} ──")
            lines.append(f"  Reflections: {model.total_reflections}")
            lines.append(f"  Self-model:  {'enabled' if self._configs[soul_name].self_model_enabled else 'disabled'}")
            if model.strengths:
                lines.append(f"  Strengths:   {', '.join(model.strengths)}")
            if model.weaknesses:
                lines.append(f"  Weaknesses:  {', '.join(model.weaknesses)}")
            if model.last_insight:
                lines.append(f"  Insight:     {model.last_insight}")
            lines.append(f"  Goals:")
            for g in goals:
                icon = "✓" if g.achieved else "○"
                bar_len = 15
                filled = int(bar_len * g.progress)
                bar = "█" * filled + "░" * (bar_len - filled)
                lines.append(f"    {icon} {g.name} [{bar}] {g.progress:.0%}")
            lines.append("")
        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
