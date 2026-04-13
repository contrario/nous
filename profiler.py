"""
NOUS Performance Profiler — Μέτρηση (Metrisi)
===============================================
Profile .nous programs: parse/validate/compile timing, per-soul analysis,
tool latency estimation, LLM cost estimation.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ast_nodes import (
    NousProgram, SoulNode, LawCost, LawCurrency,
    LetNode, SenseCallNode, SpeakNode, RememberNode,
    IfNode, ForNode, GuardNode, SleepNode,
)
from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python

TIER_COSTS = {
    "Tier0A": {"input": 0.25, "output": 1.25},
    "Tier0B": {"input": 0.15, "output": 0.60},
    "Tier1": {"input": 0.55, "output": 2.19},
    "Tier2": {"input": 2.50, "output": 10.00},
    "Tier3": {"input": 15.00, "output": 60.00},
}

AVG_TOKENS_PER_CYCLE = {"input": 800, "output": 200}


@dataclass
class SoulProfile:
    name: str
    model: str = ""
    tier: str = ""
    sense_count: int = 0
    memory_fields: int = 0
    instinct_stmts: int = 0
    speak_count: int = 0
    listen_count: int = 0
    sense_calls: int = 0
    if_branches: int = 0
    for_loops: int = 0
    guard_count: int = 0
    remember_ops: int = 0
    tools_used: list[str] = field(default_factory=list)
    est_cost_per_cycle: float = 0.0
    complexity_score: int = 0


@dataclass
class ProfileResult:
    file: str
    world_name: str = ""
    parse_time_ms: float = 0.0
    validate_time_ms: float = 0.0
    compile_time_ms: float = 0.0
    total_time_ms: float = 0.0
    generated_lines: int = 0
    soul_count: int = 0
    message_count: int = 0
    law_count: int = 0
    route_count: int = 0
    test_count: int = 0
    souls: list[SoulProfile] = field(default_factory=list)
    cost_ceiling: float = 0.0
    est_total_cost: float = 0.0
    heartbeat_seconds: int = 300
    est_daily_cost: float = 0.0
    est_monthly_cost: float = 0.0


def _count_stmts(stmts: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {
        "total": 0, "sense": 0, "speak": 0, "listen": 0,
        "if": 0, "for": 0, "guard": 0, "remember": 0,
    }
    tools: list[str] = []
    for stmt in stmts:
        counts["total"] += 1
        if isinstance(stmt, SenseCallNode):
            counts["sense"] += 1
            tools.append(stmt.tool_name)
        elif isinstance(stmt, SpeakNode):
            counts["speak"] += 1
        elif isinstance(stmt, RememberNode):
            counts["remember"] += 1
        elif isinstance(stmt, GuardNode):
            counts["guard"] += 1
        elif isinstance(stmt, LetNode):
            if isinstance(stmt.value, dict):
                kind = stmt.value.get("kind", "")
                if kind == "sense_call":
                    counts["sense"] += 1
                    tools.append(stmt.value.get("tool", ""))
                elif kind == "listen":
                    counts["listen"] += 1
        elif isinstance(stmt, IfNode):
            counts["if"] += 1
            sub = _count_stmts(stmt.then_body)
            for k in counts:
                counts[k] += sub[k]
            sub2 = _count_stmts(stmt.else_body)
            for k in counts:
                counts[k] += sub2[k]
            tools.extend(sub.get("_tools", []))
            tools.extend(sub2.get("_tools", []))
        elif isinstance(stmt, ForNode):
            counts["for"] += 1
            sub = _count_stmts(stmt.body)
            for k in counts:
                counts[k] += sub[k]
            tools.extend(sub.get("_tools", []))
    counts["_tools"] = tools
    return counts


def _profile_soul(soul: SoulNode) -> SoulProfile:
    sp = SoulProfile(name=soul.name)
    if soul.mind:
        sp.model = soul.mind.model
        sp.tier = soul.mind.tier.value
    sp.sense_count = len(soul.senses)
    sp.memory_fields = len(soul.memory.fields) if soul.memory else 0

    if soul.instinct:
        counts = _count_stmts(soul.instinct.statements)
        sp.instinct_stmts = counts["total"]
        sp.sense_calls = counts["sense"]
        sp.speak_count = counts["speak"]
        sp.listen_count = counts["listen"]
        sp.if_branches = counts["if"]
        sp.for_loops = counts["for"]
        sp.guard_count = counts["guard"]
        sp.remember_ops = counts["remember"]
        sp.tools_used = list(set(counts.get("_tools", [])))

    tier_cost = TIER_COSTS.get(sp.tier, TIER_COSTS["Tier1"])
    input_cost = (AVG_TOKENS_PER_CYCLE["input"] / 1_000_000) * tier_cost["input"]
    output_cost = (AVG_TOKENS_PER_CYCLE["output"] / 1_000_000) * tier_cost["output"]
    sp.est_cost_per_cycle = input_cost + output_cost

    sp.complexity_score = (
        sp.instinct_stmts * 1
        + sp.sense_calls * 3
        + sp.if_branches * 2
        + sp.for_loops * 4
        + sp.speak_count * 1
        + sp.listen_count * 2
    )

    return sp


def _duration_to_seconds(duration: str) -> int:
    if not duration:
        return 300
    if duration.endswith("ms"):
        return max(1, int(duration[:-2]) // 1000)
    unit = duration[-1]
    try:
        val = int(duration[:-1])
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


def profile(source_path: str) -> ProfileResult:
    path = Path(source_path)
    result = ProfileResult(file=str(path))

    t0 = time.perf_counter()
    program = parse_nous_file(path)
    result.parse_time_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    validate_program(program)
    result.validate_time_ms = (time.perf_counter() - t1) * 1000

    t2 = time.perf_counter()
    code = generate_python(program)
    result.compile_time_ms = (time.perf_counter() - t2) * 1000

    result.total_time_ms = (time.perf_counter() - t0) * 1000
    result.generated_lines = len(code.splitlines())

    w = program.world
    if w:
        result.world_name = w.name
        result.law_count = len(w.laws)
        result.heartbeat_seconds = _duration_to_seconds(w.heartbeat) if w.heartbeat else 300
        for law in w.laws:
            if isinstance(law.expr, LawCost):
                result.cost_ceiling = law.expr.amount

    result.soul_count = len(program.souls)
    result.message_count = len(program.messages)
    result.test_count = len(program.tests)
    if program.nervous_system:
        result.route_count = len(program.nervous_system.routes)

    for soul in program.souls:
        sp = _profile_soul(soul)
        result.souls.append(sp)

    result.est_total_cost = sum(s.est_cost_per_cycle for s in result.souls)
    cycles_per_day = 86400 / result.heartbeat_seconds
    result.est_daily_cost = result.est_total_cost * cycles_per_day
    result.est_monthly_cost = result.est_daily_cost * 30

    return result


def print_profile(r: ProfileResult) -> None:
    G = "\033[92m"
    Y = "\033[93m"
    C = "\033[96m"
    M = "\033[95m"
    D = "\033[2m"
    B = "\033[1m"
    R = "\033[0m"
    if not sys.stdout.isatty():
        G = Y = C = M = D = B = R = ""

    print(f"\n{B}═══ NOUS Profiler ═══{R}")
    print(f"File: {C}{r.file}{R}  World: {C}{r.world_name}{R}\n")

    print(f"{B}Pipeline Timing{R}")
    bar_parse = "█" * max(1, int(r.parse_time_ms / max(r.total_time_ms, 0.01) * 30))
    bar_valid = "█" * max(1, int(r.validate_time_ms / max(r.total_time_ms, 0.01) * 30))
    bar_comp = "█" * max(1, int(r.compile_time_ms / max(r.total_time_ms, 0.01) * 30))
    print(f"  Parse:    {G}{bar_parse}{R} {r.parse_time_ms:.1f}ms")
    print(f"  Validate: {Y}{bar_valid}{R} {r.validate_time_ms:.1f}ms")
    print(f"  Compile:  {C}{bar_comp}{R} {r.compile_time_ms:.1f}ms")
    print(f"  Total:    {B}{r.total_time_ms:.1f}ms{R} → {r.generated_lines} lines\n")

    print(f"{B}Program Structure{R}")
    print(f"  Souls: {r.soul_count}  Messages: {r.message_count}  Laws: {r.law_count}  Routes: {r.route_count}  Tests: {r.test_count}\n")

    print(f"{B}Soul Analysis{R}")
    print(f"  {'Name':<14} {'Tier':<8} {'Stmts':>5} {'Sense':>5} {'Speak':>5} {'If':>4} {'For':>4} {'Cost/cyc':>10} {'Complexity':>10}")
    print(f"  {'─'*76}")
    for s in r.souls:
        print(f"  {M}{s.name:<14}{R} {s.tier:<8} {s.instinct_stmts:>5} {s.sense_calls:>5} {s.speak_count:>5} {s.if_branches:>4} {s.for_loops:>4} {Y}${s.est_cost_per_cycle:.6f}{R} {s.complexity_score:>10}")
        if s.tools_used:
            tools = ", ".join(s.tools_used)
            print(f"  {D}  tools: {tools}{R}")
    print()

    print(f"{B}Cost Estimation{R} {D}(based on avg {AVG_TOKENS_PER_CYCLE['input']}+{AVG_TOKENS_PER_CYCLE['output']} tokens/cycle){R}")
    hb = r.heartbeat_seconds
    cpd = 86400 / hb
    print(f"  Heartbeat:       {hb}s ({cpd:.0f} cycles/day)")
    print(f"  Per cycle:       {Y}${r.est_total_cost:.6f}{R}")
    if r.cost_ceiling:
        pct = (r.est_total_cost / r.cost_ceiling) * 100
        color = G if pct < 80 else Y
        print(f"  Cost ceiling:    ${r.cost_ceiling:.2f}/cycle ({color}{pct:.0f}% utilized{R})")
    print(f"  Daily estimate:  {Y}${r.est_daily_cost:.4f}{R}")
    print(f"  Monthly estimate:{Y}${r.est_monthly_cost:.2f}{R}\n")
