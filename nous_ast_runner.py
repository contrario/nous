"""
NOUS AST Runner — Εκτέλεση (Ektelesi)
=======================================
Executes a parsed .nous AST directly via NousRuntime.
No codegen needed. Parse → AST → Live execution.

Usage:
    from nous_ast_runner import run_program
    run_program("gate_alpha.nous", mode="dry-run")

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MessageNode,
    NervousSystemNode, RouteNode, FanInNode, FanOutNode,
    LetNode, SpeakNode, GuardNode, SenseCallNode, ForNode, IfNode,
    RememberNode, LawCost, LawDuration, LawBool, LawInt,
)
from parser import parse_nous_file
from validator import validate_program
from nous_runtime import NousRuntime

log = logging.getLogger("nous.ast_runner")


def _extract_heartbeat(world: WorldNode) -> int:
    if world.heartbeat:
        val = world.heartbeat
        if isinstance(val, str):
            m = re.match(r"(\d+)\s*(s|m|h)", val)
            if m:
                n, unit = int(m.group(1)), m.group(2)
                if unit == "m":
                    return n * 60
                elif unit == "h":
                    return n * 3600
                return n
        elif isinstance(val, (int, float)):
            return int(val)
    return 300


def _extract_cost_ceiling(world: WorldNode) -> float:
    for law in world.laws:
        if isinstance(law, LawCost) and "cost" in law.name.lower():
            return law.amount
    return 0.10


def _extract_daily_budget(cost_ceiling: float, heartbeat: int) -> float:
    cycles_per_day = 86400 / heartbeat
    return cost_ceiling * cycles_per_day


def _build_soul_prompt(soul: SoulNode, world: WorldNode) -> str:
    sense_list = ", ".join(soul.senses) if soul.senses else "none"
    return (
        f"You are {soul.name}, an AI agent in world {world.name}. "
        f"Your available tools: {sense_list}. "
        f"Answer concisely in 2-4 sentences. Be specific and actionable."
    )


def _instinct_to_queries(soul: SoulNode) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    if not soul.instinct or not soul.instinct.statements:
        return queries
    for stmt in soul.instinct.statements:
        if isinstance(stmt, LetNode):
            if isinstance(stmt.value, SenseCallNode):
                queries.append({
                    "type": "sense",
                    "var": stmt.name,
                    "sense": stmt.value.name,
                    "args": [str(a) for a in stmt.value.args] if stmt.value.args else [],
                })
            else:
                queries.append({
                    "type": "let",
                    "var": stmt.name,
                    "expr": str(stmt.value),
                })
        elif isinstance(stmt, SpeakNode):
            queries.append({
                "type": "speak",
                "message_type": stmt.message_type,
                "fields": {f.name: str(f.value) for f in stmt.fields} if hasattr(stmt, "fields") and stmt.fields else {},
            })
        elif isinstance(stmt, GuardNode):
            queries.append({
                "type": "guard",
                "condition": str(stmt.condition),
            })
        elif isinstance(stmt, RememberNode):
            queries.append({
                "type": "remember",
                "field": stmt.field if hasattr(stmt, "field") else "",
                "expr": str(stmt.value) if hasattr(stmt, "value") else "",
            })
        elif isinstance(stmt, ForNode):
            queries.append({
                "type": "for",
                "var": stmt.var_name if hasattr(stmt, "var_name") else "item",
                "body_count": len(stmt.body) if hasattr(stmt, "body") and stmt.body else 0,
            })
    return queries


async def _run_soul_cycle(
    rt: NousRuntime,
    soul: SoulNode,
    world: WorldNode,
    routes: dict[str, list[str]],
    cycle: int,
) -> None:
    name = soul.name
    prompt = _build_soul_prompt(soul, world)
    queries = _instinct_to_queries(soul)

    sense_calls = [q for q in queries if q["type"] == "sense"]
    speak_calls = [q for q in queries if q["type"] == "speak"]

    if sense_calls:
        sense_desc = "; ".join(f"{s['sense']}({','.join(s['args'])})" for s in sense_calls)
        query = f"Execute your instinct cycle {cycle}. Call your senses: {sense_desc}. Report findings."
    else:
        query = f"Execute your instinct cycle {cycle}. Analyze current state and report."

    response = await rt.think(name, query, system_prompt=prompt)

    if response and speak_calls:
        for sp in speak_calls:
            msg_type = sp.get("message_type", "Signal")
            channel = f"{name}_{msg_type}"
            await rt.speak(name, channel, {"from": name, "type": msg_type, "data": response[:200], "cycle": cycle})

    targets = routes.get(name, [])
    for target in targets:
        if speak_calls:
            msg_type = speak_calls[0].get("message_type", "Signal")
            channel = f"{name}_{msg_type}"
        else:
            channel = f"{name}_output"
            await rt.speak(name, channel, {"from": name, "data": response[:200], "cycle": cycle})


async def _run_listener_cycle(
    rt: NousRuntime,
    soul: SoulNode,
    world: WorldNode,
    incoming: dict[str, list[str]],
    cycle: int,
) -> None:
    name = soul.name
    prompt = _build_soul_prompt(soul, world)
    sources = incoming.get(name, [])

    for src in sources:
        queries = _instinct_to_queries(soul)
        speak_calls = [q for q in queries if q["type"] == "speak"]

        for q in queries:
            if q["type"] == "sense" and q["sense"].startswith("listen"):
                pass

        channel_candidates = [f"{src}_Signal", f"{src}_Decision", f"{src}_output"]
        msg = None
        for ch in channel_candidates:
            msg = await rt.listen(name, ch, timeout=2)
            if msg:
                break

        if msg:
            query = f"Process incoming from {src}: {str(msg)[:200]}. Execute your analysis."
            response = await rt.think(name, query, system_prompt=prompt)

            if response and speak_calls:
                for sp in speak_calls:
                    msg_type = sp.get("message_type", "Decision")
                    channel = f"{name}_{msg_type}"
                    await rt.speak(name, channel, {"from": name, "type": msg_type, "data": response[:200], "cycle": cycle})


async def execute_program(
    program: NousProgram,
    mode: str = "dry-run",
    max_cycles: int = 3,
    daily_budget: float = 0.33,
    monthly_budget: float = 10.0,
) -> str:
    world = program.world
    if not world:
        log.error("No world defined")
        return "Error: no world"

    heartbeat = _extract_heartbeat(world)
    cost_ceiling = _extract_cost_ceiling(world)

    log.info(f"World: {world.name} | Heartbeat: {heartbeat}s | Cost ceiling: ${cost_ceiling}")

    rt = NousRuntime(
        mode=mode,
        daily_budget=daily_budget,
        monthly_budget=monthly_budget,
        heartbeat_seconds=heartbeat,
        max_cycles=max_cycles,
    )

    routes: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}

    if program.nervous_system:
        for route in program.nervous_system.routes:
            if isinstance(route, RouteNode):
                routes.setdefault(route.source, []).append(route.target)
                incoming.setdefault(route.target, []).append(route.source)
            elif isinstance(route, FanOutNode):
                for t in route.targets:
                    routes.setdefault(route.source, []).append(t)
                    incoming.setdefault(t, []).append(route.source)
            elif isinstance(route, FanInNode):
                for s in route.sources:
                    routes.setdefault(s, []).append(route.target)
                    incoming.setdefault(route.target, []).append(s)

    entrypoints: list[SoulNode] = []
    listeners: list[SoulNode] = []
    for soul in program.souls:
        if soul.name not in incoming:
            entrypoints.append(soul)
        else:
            listeners.append(soul)

    for soul in program.souls:
        model = soul.mind.model if soul.mind else "unknown"
        tier = soul.mind.tier if soul.mind else "Free"
        senses = soul.senses or []
        memory: dict[str, Any] = {}
        if soul.memory:
            for f in soul.memory.fields:
                memory[f.name] = f.default if hasattr(f, "default") else None
        rt.register_soul(soul.name, model, tier, senses, memory)

    log.info(f"Entrypoints: {[s.name for s in entrypoints]}")
    log.info(f"Listeners: {[s.name for s in listeners]}")
    log.info(f"Routes: {routes}")

    for cycle in range(1, max_cycles + 1):
        log.info(f"\n{'═' * 20} Cycle {cycle}/{max_cycles} {'═' * 20}")

        for soul in entrypoints:
            await _run_soul_cycle(rt, soul, world, routes, cycle)

        for soul in listeners:
            await _run_listener_cycle(rt, soul, world, incoming, cycle)

        if cycle < max_cycles:
            if mode == "live":
                log.info(f"Sleeping {heartbeat}s until next cycle...")
                await asyncio.sleep(min(heartbeat, 5))
            else:
                await asyncio.sleep(0.1)

    report = rt.report()
    print(f"\n{report}")

    log_path = Path(f"/opt/aetherlang_agents/nous/runtime_{world.name.lower()}_{mode}.json")
    rt.rlog.save(log_path)
    log.info(f"Log saved: {log_path}")

    return report


def run_program(
    nous_file: str,
    mode: str = "dry-run",
    max_cycles: int = 3,
    daily_budget: float = 0.33,
    monthly_budget: float = 10.0,
) -> str:
    path = Path(nous_file)
    if not path.exists():
        print(f"Error: {path} not found")
        return ""

    print(f"═══ NOUS Runtime v2 — {path.name} ═══")
    print(f"Mode: {mode} | Max cycles: {max_cycles} | Budget: ${daily_budget}/day, ${monthly_budget}/month")
    print()

    program = parse_nous_file(path)
    vresult = validate_program(program)
    if not vresult.ok:
        print(f"Validation FAILED:")
        for e in vresult.errors:
            print(f"  {e}")
        return ""
    print(f"Parse + validate OK ({len(program.souls)} souls, {len(program.messages)} messages)")

    return asyncio.run(execute_program(program, mode=mode, max_cycles=max_cycles,
                                        daily_budget=daily_budget, monthly_budget=monthly_budget))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")

    file = sys.argv[1] if len(sys.argv) > 1 else "gate_alpha.nous"
    mode = sys.argv[2] if len(sys.argv) > 2 else "dry-run"
    cycles = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    run_program(file, mode=mode, max_cycles=cycles)
