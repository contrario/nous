"""
NOUS Profiler v2 — Μέτρηση (Metrisi)
=======================================
Per-soul cost tracking, token estimation, latency analysis.
Static analysis — no runtime needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, SoulNode, LawCost, LawDuration,
    LetNode, RememberNode, SpeakNode, GuardNode,
    SenseCallNode, SleepNode, IfNode, ForNode,
)

TIER_COSTS: dict[str, dict[str, float]] = {
    "Tier0A": {"input_per_1k": 0.00025, "output_per_1k": 0.00125, "label": "Haiku-class"},
    "Tier0B": {"input_per_1k": 0.0005, "output_per_1k": 0.0025, "label": "Flash-class"},
    "Tier1":  {"input_per_1k": 0.003, "output_per_1k": 0.015, "label": "Sonnet-class"},
    "Tier2":  {"input_per_1k": 0.005, "output_per_1k": 0.025, "label": "GPT4o-class"},
    "Tier3":  {"input_per_1k": 0.015, "output_per_1k": 0.075, "label": "Opus-class"},
}

SENSE_TOKEN_ESTIMATES: dict[str, int] = {
    "http_get": 200,
    "fetch_rsi": 150,
    "ddgs_search": 500,
    "calculate_kelly": 300,
    "execute_paper_trade": 200,
    "check_balance": 100,
    "check_positions": 300,
    "send_telegram": 100,
    "gate_alpha_scan": 800,
    "backtest_pair": 1000,
    "check_endpoint": 150,
    "compute_stats": 200,
    "cron_check": 100,
    "execute_task": 300,
    "resolve_route": 150,
    "deliver_message": 100,
    "write_log": 50,
    "query_logs": 200,
    "flush_logs": 100,
}

DEFAULT_SENSE_TOKENS = 200


@dataclass
class SoulProfile:
    name: str
    model: str = ""
    tier: str = ""
    tier_label: str = ""
    sense_count: int = 0
    memory_fields: int = 0
    gene_count: int = 0
    stmt_count: int = 0
    speak_count: int = 0
    listen_count: int = 0
    sense_call_count: int = 0
    guard_count: int = 0
    loop_count: int = 0
    branch_count: int = 0
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    est_cost_per_cycle: float = 0.0
    est_latency_ms: int = 0
    complexity_score: int = 0
    senses_used: list[str] = field(default_factory=list)


@dataclass
class ProfileReport:
    world_name: str = ""
    heartbeat: str = ""
    total_souls: int = 0
    total_messages: int = 0
    total_routes: int = 0
    soul_profiles: list[SoulProfile] = field(default_factory=list)
    total_cost_per_cycle: float = 0.0
    total_cost_per_hour: float = 0.0
    total_cost_per_day: float = 0.0
    law_cost_ceiling: Optional[float] = None
    budget_ok: bool = True


class NousProfiler:
    """Static profiler for NOUS programs."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program

    def profile(self) -> ProfileReport:
        report = ProfileReport()

        if self.program.world:
            report.world_name = self.program.world.name
            report.heartbeat = self.program.world.heartbeat or "5m"
            for law in self.program.world.laws:
                if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
                    report.law_cost_ceiling = law.expr.amount

        report.total_souls = len(self.program.souls)
        report.total_messages = len(self.program.messages)
        if self.program.nervous_system:
            report.total_routes = len(self.program.nervous_system.routes)

        for soul in self.program.souls:
            sp = self._profile_soul(soul)
            report.soul_profiles.append(sp)
            report.total_cost_per_cycle += sp.est_cost_per_cycle

        heartbeat_seconds = self._parse_duration(report.heartbeat)
        cycles_per_hour = 3600 / heartbeat_seconds if heartbeat_seconds > 0 else 0
        report.total_cost_per_hour = report.total_cost_per_cycle * cycles_per_hour
        report.total_cost_per_day = report.total_cost_per_hour * 24

        if report.law_cost_ceiling is not None:
            report.budget_ok = report.total_cost_per_cycle <= report.law_cost_ceiling

        return report

    def _profile_soul(self, soul: SoulNode) -> SoulProfile:
        sp = SoulProfile(name=soul.name)

        if soul.mind:
            sp.model = soul.mind.model
            sp.tier = soul.mind.tier.value
            tier_info = TIER_COSTS.get(sp.tier, TIER_COSTS["Tier1"])
            sp.tier_label = tier_info["label"]

        sp.sense_count = len(soul.senses)
        sp.senses_used = list(soul.senses)
        sp.memory_fields = len(soul.memory.fields) if soul.memory else 0
        sp.gene_count = len(soul.dna.genes) if soul.dna else 0

        if soul.instinct:
            counts = self._count_statements(soul.instinct.statements)
            sp.stmt_count = counts["total"]
            sp.speak_count = counts["speak"]
            sp.listen_count = counts["listen"]
            sp.sense_call_count = counts["sense"]
            sp.guard_count = counts["guard"]
            sp.loop_count = counts["loop"]
            sp.branch_count = counts["branch"]

        base_prompt = 200
        memory_tokens = sp.memory_fields * 30
        sense_context = sum(
            SENSE_TOKEN_ESTIMATES.get(s, DEFAULT_SENSE_TOKENS)
            for s in sp.senses_used
            if s in self._get_used_senses(soul)
        )
        if not sense_context:
            sense_context = sp.sense_call_count * DEFAULT_SENSE_TOKENS

        sp.est_input_tokens = base_prompt + memory_tokens + sense_context
        sp.est_output_tokens = max(100, sp.speak_count * 150 + sp.stmt_count * 20)

        tier_info = TIER_COSTS.get(sp.tier, TIER_COSTS["Tier1"])
        sp.est_cost_per_cycle = (
            (sp.est_input_tokens / 1000) * tier_info["input_per_1k"]
            + (sp.est_output_tokens / 1000) * tier_info["output_per_1k"]
        )

        base_latency = {"Tier0A": 500, "Tier0B": 800, "Tier1": 2000, "Tier2": 1500, "Tier3": 5000}
        sp.est_latency_ms = base_latency.get(sp.tier, 2000) + sp.sense_call_count * 300

        sp.complexity_score = (
            sp.stmt_count
            + sp.branch_count * 2
            + sp.loop_count * 3
            + sp.sense_call_count * 2
            + sp.guard_count
        )

        return sp

    def _count_statements(self, stmts: list[Any]) -> dict[str, int]:
        counts = {"total": 0, "speak": 0, "listen": 0, "sense": 0, "guard": 0, "loop": 0, "branch": 0}
        for stmt in stmts:
            counts["total"] += 1
            if isinstance(stmt, SpeakNode):
                counts["speak"] += 1
            elif isinstance(stmt, LetNode):
                if isinstance(stmt.value, dict):
                    kind = stmt.value.get("kind", "")
                    if kind == "listen":
                        counts["listen"] += 1
                    elif kind == "sense_call":
                        counts["sense"] += 1
            elif isinstance(stmt, SenseCallNode):
                counts["sense"] += 1
            elif isinstance(stmt, GuardNode):
                counts["guard"] += 1
            elif isinstance(stmt, ForNode):
                counts["loop"] += 1
                sub = self._count_statements(stmt.body)
                for k in counts:
                    counts[k] += sub[k]
            elif isinstance(stmt, IfNode):
                counts["branch"] += 1
                sub = self._count_statements(stmt.then_body)
                for k in counts:
                    counts[k] += sub[k]
                if stmt.else_body:
                    sub = self._count_statements(stmt.else_body)
                    for k in counts:
                        counts[k] += sub[k]
        return counts

    def _get_used_senses(self, soul: SoulNode) -> set[str]:
        used: set[str] = set()
        if soul.instinct:
            self._collect_senses(soul.instinct.statements, used)
        return used

    def _collect_senses(self, stmts: list[Any], used: set[str]) -> None:
        for stmt in stmts:
            if isinstance(stmt, SenseCallNode):
                used.add(stmt.tool_name)
            elif isinstance(stmt, LetNode) and isinstance(stmt.value, dict):
                if stmt.value.get("kind") == "sense_call":
                    used.add(stmt.value.get("tool", ""))
            elif isinstance(stmt, ForNode):
                self._collect_senses(stmt.body, used)
            elif isinstance(stmt, IfNode):
                self._collect_senses(stmt.then_body, used)
                self._collect_senses(stmt.else_body, used)

    def _parse_duration(self, d: str) -> int:
        if not d:
            return 300
        if d.endswith("ms"):
            return max(1, int(d[:-2]) // 1000)
        unit = d[-1]
        try:
            val = int(d[:-1])
        except ValueError:
            return 300
        if unit == "s":
            return val
        elif unit == "m":
            return val * 60
        elif unit == "h":
            return val * 3600
        elif unit == "d":
            return val * 86400
        return val


def print_profile(report: ProfileReport) -> None:
    print(f"\n═══ NOUS Profiler — {report.world_name} ═══\n")
    print(f"  Heartbeat:  {report.heartbeat}")
    print(f"  Souls:      {report.total_souls}")
    print(f"  Messages:   {report.total_messages}")
    print(f"  Routes:     {report.total_routes}")

    for sp in report.soul_profiles:
        print(f"\n  ┌─ {sp.name} ({sp.model} @ {sp.tier} / {sp.tier_label})")
        print(f"  │  Statements:  {sp.stmt_count} (speak:{sp.speak_count} listen:{sp.listen_count} sense:{sp.sense_call_count} guard:{sp.guard_count} if:{sp.branch_count} for:{sp.loop_count})")
        print(f"  │  Memory:      {sp.memory_fields} fields, {sp.gene_count} genes")
        print(f"  │  Tokens:      ~{sp.est_input_tokens} in / ~{sp.est_output_tokens} out")
        print(f"  │  Cost/cycle:  ${sp.est_cost_per_cycle:.6f}")
        print(f"  │  Latency:     ~{sp.est_latency_ms}ms")
        print(f"  └  Complexity:  {sp.complexity_score}")

    print(f"\n  ── Cost Summary ──")
    print(f"  Per cycle:  ${report.total_cost_per_cycle:.6f}")
    print(f"  Per hour:   ${report.total_cost_per_hour:.4f}")
    print(f"  Per day:    ${report.total_cost_per_day:.2f}")

    if report.law_cost_ceiling is not None:
        icon = "✓" if report.budget_ok else "✗"
        print(f"  Budget:     {icon} ${report.total_cost_per_cycle:.6f} / ${report.law_cost_ceiling:.2f} ceiling")


def cmd_profile(file_path: str) -> int:
    from parser import parse_nous_file
    source = Path(file_path)
    if not source.exists():
        print(f"Error: file not found: {source}")
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}")
        return 1
    profiler = NousProfiler(program)
    report = profiler.profile()
    print_profile(report)
    return 0
