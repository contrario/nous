"""
NOUS Cost Oracle — Μαντείο Κόστους
=====================================
Predictive cost analysis + automatic optimization suggestions.
Tells you exactly what your agent system will cost before you run it.

Usage:
    python cli.py cost file.nous
    python cli.py cost file.nous --json
    python cli.py cost file.nous --period 30  (days)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, SoulNode, Tier


TIER_COSTS: dict[str, dict[str, float]] = {
    "Tier0A":    {"input_per_1k": 0.00025, "output_per_1k": 0.00125, "label": "Anthropic (Claude)"},
    "Tier0B":    {"input_per_1k": 0.0005,  "output_per_1k": 0.0025,  "label": "OpenAI (GPT-4o)"},
    "Tier1":     {"input_per_1k": 0.003,   "output_per_1k": 0.015,   "label": "OpenRouter (DeepSeek)"},
    "Tier2":     {"input_per_1k": 0.005,   "output_per_1k": 0.025,   "label": "Free tier (Gemini)"},
    "Tier3":     {"input_per_1k": 0.015,   "output_per_1k": 0.075,   "label": "Local (Ollama)"},
    "Groq":      {"input_per_1k": 0.0003,  "output_per_1k": 0.001,   "label": "Groq (ultra-fast)"},
    "Together":  {"input_per_1k": 0.0005,  "output_per_1k": 0.002,   "label": "Together AI"},
    "Fireworks": {"input_per_1k": 0.0002,  "output_per_1k": 0.0008,  "label": "Fireworks AI"},
    "Cerebras":  {"input_per_1k": 0.0001,  "output_per_1k": 0.0004,  "label": "Cerebras (fastest)"},
}

AVG_INPUT_TOKENS: float = 0.5
AVG_OUTPUT_TOKENS: float = 0.2

TIER_RANK: list[str] = ["Cerebras", "Fireworks", "Groq", "Tier0A", "Together", "Tier0B", "Tier1", "Tier2", "Tier3"]


@dataclass
class SoulCost:
    name: str
    tier: str
    model: str
    cost_per_cycle: float
    wake_strategy: str
    cycles_per_day: float
    cost_per_day: float
    cost_per_month: float
    pct_of_total: float = 0.0


@dataclass
class Optimization:
    soul: str
    action: str
    current: str
    suggested: str
    savings_per_day: float
    savings_per_month: float
    risk: str


@dataclass
class CostOracleResult:
    world_name: str
    heartbeat_seconds: int
    cost_ceiling: Optional[float]
    soul_costs: list[SoulCost] = field(default_factory=list)
    optimizations: list[Optimization] = field(default_factory=list)
    total_per_cycle: float = 0.0
    total_per_day: float = 0.0
    total_per_month: float = 0.0
    ceiling_headroom_pct: float = 0.0
    cycles_until_ceiling: int = 0
    saveable_per_day: float = 0.0
    saveable_per_month: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "world": self.world_name,
            "heartbeat_seconds": self.heartbeat_seconds,
            "cost_ceiling": self.cost_ceiling,
            "total": {
                "per_cycle": self.total_per_cycle,
                "per_day": self.total_per_day,
                "per_month": self.total_per_month,
            },
            "souls": [
                {
                    "name": s.name, "tier": s.tier, "model": s.model,
                    "cost_per_cycle": s.cost_per_cycle, "wake_strategy": s.wake_strategy,
                    "cycles_per_day": s.cycles_per_day,
                    "cost_per_day": s.cost_per_day, "cost_per_month": s.cost_per_month,
                    "pct_of_total": s.pct_of_total,
                }
                for s in self.soul_costs
            ],
            "optimizations": [
                {
                    "soul": o.soul, "action": o.action,
                    "current": o.current, "suggested": o.suggested,
                    "savings_per_day": o.savings_per_day,
                    "savings_per_month": o.savings_per_month,
                    "risk": o.risk,
                }
                for o in self.optimizations
            ],
            "saveable_per_day": self.saveable_per_day,
            "saveable_per_month": self.saveable_per_month,
        }


def _duration_to_seconds(duration_str: str) -> int:
    s = str(duration_str).strip().lower()
    if s.endswith("s"):
        return int(float(s[:-1]))
    elif s.endswith("m"):
        return int(float(s[:-1]) * 60)
    elif s.endswith("h"):
        return int(float(s[:-1]) * 3600)
    try:
        return int(float(s))
    except ValueError:
        return 300


def _estimate_soul_cost(tier: str) -> float:
    costs = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
    return (AVG_INPUT_TOKENS * costs["input_per_1k"]) + (AVG_OUTPUT_TOKENS * costs["output_per_1k"])


def _get_cheaper_tiers(current_tier: str) -> list[tuple[str, float]]:
    current_cost = _estimate_soul_cost(current_tier)
    cheaper: list[tuple[str, float]] = []
    for tier in TIER_RANK:
        if tier == current_tier:
            continue
        tier_cost = _estimate_soul_cost(tier)
        if tier_cost < current_cost:
            cheaper.append((tier, tier_cost))
    cheaper.sort(key=lambda x: x[1])
    return cheaper


def _count_sense_calls(soul: SoulNode) -> int:
    count = 0
    if soul.instinct:
        body = soul.instinct if isinstance(soul.instinct, list) else [soul.instinct]
        for stmt in body:
            if hasattr(stmt, "kind") and "sense" in str(getattr(stmt, "kind", "")):
                count += 1
            elif hasattr(stmt, "__dict__"):
                for v in stmt.__dict__.values():
                    if hasattr(v, "kind") and "sense" in str(getattr(v, "kind", "")):
                        count += 1
    return max(count, 1)


def cost_oracle(program: NousProgram, period_days: int = 30) -> CostOracleResult:
    world_name = program.world.name if program.world else "Unknown"

    heartbeat_seconds = 300
    if program.world and hasattr(program.world, "heartbeat") and program.world.heartbeat:
        heartbeat_seconds = _duration_to_seconds(str(program.world.heartbeat))

    cost_ceiling: Optional[float] = None
    if program.world:
        for law in program.world.laws:
            if hasattr(law, "expr") and hasattr(law.expr, "amount"):
                cost_ceiling = float(law.expr.amount)
                break

    targets: set[str] = set()
    if program.nervous_system:
        for route in program.nervous_system.routes:
            dst = route.target if isinstance(route.target, str) else str(route.target)
            targets.add(dst)

    soul_costs: list[SoulCost] = []
    total_per_cycle = 0.0

    for soul in program.souls:
        tier = soul.mind.tier.value if soul.mind and soul.mind.tier else "Tier1"
        model = soul.mind.model if soul.mind else "unknown"
        cost_per_cycle = _estimate_soul_cost(tier)

        wake = "LISTENER" if soul.name in targets else "HEARTBEAT"

        if wake == "HEARTBEAT":
            cycles_per_day = 86400 / heartbeat_seconds
        else:
            heartbeat_souls = [s for s in program.souls if s.name not in targets]
            cycles_per_day = 86400 / heartbeat_seconds

        cost_per_day = cost_per_cycle * cycles_per_day
        cost_per_month = cost_per_day * period_days

        sc = SoulCost(
            name=soul.name,
            tier=tier,
            model=model,
            cost_per_cycle=cost_per_cycle,
            wake_strategy=wake,
            cycles_per_day=cycles_per_day,
            cost_per_day=cost_per_day,
            cost_per_month=cost_per_month,
        )
        soul_costs.append(sc)
        total_per_cycle += cost_per_cycle

    total_per_day = sum(s.cost_per_day for s in soul_costs)
    total_per_month = sum(s.cost_per_month for s in soul_costs)

    for sc in soul_costs:
        sc.pct_of_total = (sc.cost_per_day / total_per_day * 100) if total_per_day > 0 else 0

    soul_costs.sort(key=lambda s: s.cost_per_day, reverse=True)

    optimizations: list[Optimization] = []
    total_saveable_day = 0.0

    for sc in soul_costs:
        cheaper = _get_cheaper_tiers(sc.tier)
        if cheaper:
            best_tier, best_cost = cheaper[0]
            best_label = TIER_COSTS.get(best_tier, {}).get("label", best_tier)
            current_label = TIER_COSTS.get(sc.tier, {}).get("label", sc.tier)
            savings_day = sc.cost_per_day - (best_cost * sc.cycles_per_day)
            savings_month = savings_day * period_days

            if savings_day > 0.01:
                savings_pct = (savings_day / sc.cost_per_day * 100) if sc.cost_per_day > 0 else 0
                optimizations.append(Optimization(
                    soul=sc.name,
                    action=f"Switch tier {sc.tier} → {best_tier}",
                    current=f"{sc.tier} ({current_label})",
                    suggested=f"{best_tier} ({best_label})",
                    savings_per_day=savings_day,
                    savings_per_month=savings_month,
                    risk="low" if best_tier in ("Groq", "Fireworks", "Cerebras") else "medium",
                ))
                total_saveable_day += savings_day

        if sc.wake_strategy == "HEARTBEAT" and heartbeat_seconds < 120:
            doubled_hb = heartbeat_seconds * 2
            savings_day = sc.cost_per_day * 0.5
            savings_month = savings_day * period_days
            if savings_day > 0.01:
                optimizations.append(Optimization(
                    soul=sc.name,
                    action=f"Increase heartbeat {heartbeat_seconds}s → {doubled_hb}s",
                    current=f"{heartbeat_seconds}s ({sc.cycles_per_day:.0f} cycles/day)",
                    suggested=f"{doubled_hb}s ({sc.cycles_per_day / 2:.0f} cycles/day)",
                    savings_per_day=savings_day,
                    savings_per_month=savings_month,
                    risk="low",
                ))
                total_saveable_day += savings_day

    optimizations.sort(key=lambda o: o.savings_per_day, reverse=True)

    ceiling_headroom = 0.0
    cycles_until_ceiling = 0
    if cost_ceiling and total_per_cycle > 0:
        ceiling_headroom = ((cost_ceiling - total_per_cycle) / cost_ceiling) * 100
        if total_per_cycle > 0:
            cycles_until_ceiling = int(cost_ceiling / total_per_cycle)

    return CostOracleResult(
        world_name=world_name,
        heartbeat_seconds=heartbeat_seconds,
        cost_ceiling=cost_ceiling,
        soul_costs=soul_costs,
        optimizations=optimizations,
        total_per_cycle=total_per_cycle,
        total_per_day=total_per_day,
        total_per_month=total_per_month,
        ceiling_headroom_pct=ceiling_headroom,
        cycles_until_ceiling=cycles_until_ceiling,
        saveable_per_day=total_saveable_day,
        saveable_per_month=total_saveable_day * period_days,
    )


def format_oracle(result: CostOracleResult) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append(f"  ═══ NOUS Cost Oracle — {result.world_name} ═══")
    lines.append("")

    lines.append("  ── Projection ──")
    lines.append(f"  Per cycle:  ${result.total_per_cycle:.6f}")
    lines.append(f"  Daily:      ${result.total_per_day:.2f}")
    lines.append(f"  Monthly:    ${result.total_per_month:.2f}")
    if result.cost_ceiling:
        lines.append(f"  Ceiling:    ${result.cost_ceiling}/cycle ({result.ceiling_headroom_pct:.0f}% headroom)")
        lines.append(f"  Runway:     {result.cycles_until_ceiling} cycles before ceiling")
    lines.append("")

    lines.append("  ── Per-Soul Breakdown ──")
    for sc in result.soul_costs:
        bar_len = int(sc.pct_of_total / 5) if sc.pct_of_total > 0 else 0
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"  {sc.name:<16} ${sc.cost_per_day:>7.2f}/day  {bar} {sc.pct_of_total:>4.0f}%")
        lines.append(f"  {'':16} {sc.tier} ({sc.model}) · {sc.wake_strategy} · {sc.cycles_per_day:.0f} cycles/day")
    lines.append("")

    if result.optimizations:
        lines.append("  ── Optimization Suggestions ──")
        for i, opt in enumerate(result.optimizations, 1):
            lines.append(f"  {i}. {opt.soul}: {opt.action}")
            lines.append(f"     {opt.current} → {opt.suggested}")
            lines.append(f"     Save: ${opt.savings_per_day:.2f}/day (${opt.savings_per_month:.2f}/month) · Risk: {opt.risk}")
            lines.append("")

        lines.append(f"  Total saveable: ${result.saveable_per_day:.2f}/day (${result.saveable_per_month:.2f}/month)")
        if result.total_per_day > 0:
            optimized = result.total_per_day - result.saveable_per_day
            lines.append(f"  Optimized cost: ${result.total_per_day:.2f} → ${optimized:.2f}/day")
        lines.append("")

    lines.append("  ══════════════════════════════════════")
    if result.saveable_per_month > 10:
        lines.append(f"  OPTIMIZE: ${result.saveable_per_month:.2f}/month saveable across {len(result.optimizations)} suggestions")
    elif result.saveable_per_month > 0:
        lines.append(f"  EFFICIENT: ${result.saveable_per_month:.2f}/month potential savings")
    else:
        lines.append("  OPTIMAL: No cost optimizations available")
    lines.append("")

    return "\n".join(lines)


def oracle_file(file_path: str, period_days: int = 30, output_json: bool = False) -> str:
    from parser import parse_nous
    source = Path(file_path).read_text()
    program = parse_nous(source)
    result = cost_oracle(program, period_days=period_days)
    if output_json:
        return json.dumps(result.to_dict(), indent=2)
    return format_oracle(result)
