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


def _extract_cost_ceiling(world: WorldNode) -> float:  # __session87_runner_cost_ceiling_fix_v1__
    for law in world.laws:
        if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
            return law.expr.amount
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
            event_label = msg_type if msg_type in world.events else None  # __s104_label_bind_soul_cycle_v1__
            await rt.speak(name, channel, {"from": name, "type": msg_type, "data": response[:200], "cycle": cycle}, event_label=event_label)

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
                    event_label = msg_type if msg_type in world.events else None  # __s104_label_bind_listener_cycle_v1__
                    await rt.speak(name, channel, {"from": name, "type": msg_type, "data": response[:200], "cycle": cycle}, event_label=event_label)


async def execute_program(
    program: NousProgram,
    mode: str = "dry-run",
    max_cycles: int = 3,
    daily_budget: float = 0.33,
    monthly_budget: float = 10.0,
    source_text: "Optional[str]" = None,  # __nous_n2b_execsig_v1__
    emit_trace: bool = False,
    trace_capture: "Optional[dict]" = None,  # __s105_capture_sig_v1__
    consult_memory: bool = False,  # __s107_u4_consult_sig_v1__
    apply_remedy: bool = False,  # __s111_u6_apply_sig_v1__
) -> str:
    world = program.world
    if not world:
        log.error("No world defined")
        return "Error: no world"

    if consult_memory and not emit_trace:  # __s107_u4_consult_guard_v1__
        from run_identity import MemoryConsultationError as _MCErr0
        raise _MCErr0("consult_memory requires emit_trace")

    if apply_remedy and not consult_memory:  # __s111_u6_apply_guard_v1__
        from run_identity import MemoryConsultationError as _MCErr1
        raise _MCErr1("apply_remedy requires consult_memory")

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

    if emit_trace:  # __nous_n2b_build_v1__
        from run_shas import compute_run_shas
        from trace_recorder import TraceRecorder
        if source_text is None:
            raise RuntimeError(
                "emit_trace requested but source_text is None; cannot "
                "derive the trace subject binding"
            )
        try:
            from _version import __version__ as _nous_version
        except Exception:
            _nous_version = "0.0.0-unknown"
        _src_sha, _smt_sha, _pricing_sha = compute_run_shas(source_text)
        from run_shas import compute_run_gated_actions  # __s142_u3_runner_gated_v1__
        _gated_actions = compute_run_gated_actions(source_text)
        from run_shas import compute_codegen_sha256  # __s155_u4_runner_codegen_import_v1__
        _codegen_sha = compute_codegen_sha256(source_text)
        _trust_kwargs = {}  # __s144_u2_runner_witnessed_stamp_v1__
        if mode == "live":
            _trust_kwargs = {
                "evidence_kind": "witnessed_run",
                "cost_binding": "realized",
                "provider_token_integrity": "unattested",
            }
        rt.attach_trace_recorder(
            TraceRecorder(
                _nous_version,
                world.name,
                _src_sha,
                _smt_sha,
                _pricing_sha,
                gated_actions=_gated_actions,
                codegen_sha256=_codegen_sha,  # __s155_u4_runner_codegen_stamp_v1__
                **_trust_kwargs,
            )
        )
        if consult_memory:  # __s107_u4_consult_read_v1__
            from pathlib import Path as _Path
            import os as _os_env  # __s112_u7_membase_runner_v2__
            _mem_base = _Path(
                _os_env.environ.get("NOUS_MEMORY_BASE_DIR", "/var/lib/nous")
            )
            from run_identity import (
                MemoryConsultationError as _MCErr,
                build_run_consultation as _build_consult,
            )
            if len(program.souls) != 1:
                raise _MCErr(
                    "Phase 1 memory consultation requires exactly 1 "
                    "soul defined in the world (found "
                    + str(len(program.souls)) + ")"
                )
            rt.trace_recorder.set_memory_consultation(
                consultation=_build_consult(
                    world.name,
                    program.souls[0].name,
                    base_dir=_mem_base,
                )
            )
            if apply_remedy:  # __s111_u6_ar_wrap_v1__
                from run_identity import (
                    build_run_remedy_application as _build_remedy,
                )
                _ra = _build_remedy(
                    world.name,
                    program.souls[0].name,
                    list(program.souls),
                    base_dir=_mem_base,
                )
                if _ra is not None:
                    rt.trace_recorder.set_remedy_application(
                        remedy_application=_ra
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

    import os as _os_out  # __s163_p5_outdir_v1__
    _trace_dir_env = _os_out.environ.get("NOUS_TRACE_DIR")
    _out_dir = Path(_trace_dir_env) if _trace_dir_env else Path.cwd()
    _out_dir.mkdir(parents=True, exist_ok=True)
    log_path = _out_dir / f"runtime_{world.name.lower()}_{mode}.json"
    rt.rlog.save(log_path)
    log.info(f"Log saved: {log_path}")

    if rt.trace_recorder is not None:  # __nous_n2b_write_v1__
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey as _Ed25519PrivateKey,
        )
        _trace_env = rt.trace_recorder.finalize(
            private_key=_Ed25519PrivateKey.generate()
        )
        if trace_capture is not None:  # __s105_capture_emit_v1__
            trace_capture["envelope"] = _trace_env.persisted_dict()  # __s107_u2_persist_capture_v1__
        else:
            _trace_path = _out_dir / f"trace_{world.name.lower()}_{mode}.json"  # __s163_p5_outdir_v1__
            import json as _json
            import os as _os
            import tempfile as _tempfile
            _payload = _json.dumps(
                _trace_env.persisted_dict(), indent=2, ensure_ascii=False  # __s107_u2_persist_disk_v1__
            )
            _fd, _tmp = _tempfile.mkstemp(
                suffix=".tmp", prefix=_trace_path.name + ".",
                dir=str(_trace_path.parent),
            )
            with _os.fdopen(_fd, "w", encoding="utf-8") as _fh:
                _fh.write(_payload)
            _os.chmod(_tmp, 0o644)
            _os.replace(_tmp, str(_trace_path))
            log.info(f"Trace saved (signed): {_trace_path}")

    return report


def run_program(
    nous_file: str,
    mode: str = "dry-run",
    max_cycles: int = 3,
    daily_budget: float = 0.33,
    monthly_budget: float = 10.0,
    emit_trace: bool = False,  # __nous_n2b_runsig_v1__
    consult_memory: bool = False,  # __s107_u5_runsig_consult_v1__
    apply_remedy: bool = False,  # __s111_u6_runsig_apply_v1__
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
                                        daily_budget=daily_budget, monthly_budget=monthly_budget,
                                        source_text=path.read_text(encoding="utf-8"),
                                        emit_trace=emit_trace,
                                        consult_memory=consult_memory,
                                        apply_remedy=apply_remedy))  # __nous_n2b_ret_v1__  # __s107_u5_runcall_consult_v1__  # __s111_u6_runcall_apply_v1__


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")

    file = sys.argv[1] if len(sys.argv) > 1 else "gate_alpha.nous"
    mode = sys.argv[2] if len(sys.argv) > 2 else "dry-run"
    cycles = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    run_program(file, mode=mode, max_cycles=cycles)


# === GAP 1 differential surface ===  __session87_runner_codegen_equiv_v1__
from dataclasses import dataclass, field as _ss_field  # noqa: E402
from typing import Mapping as _SSMapping  # noqa: E402


@dataclass(frozen=True)
class SemanticSurface:
    """Deterministic facts both execution paths derive from one validated AST.

    Field-wise equality. Routes are intentionally excluded from this v1
    surface: codegen emits no structured route table, so recovering route
    edges from the emitted module requires inverting channel-name strings,
    a lossy operation that would make equality unsound. Route lowering is
    covered by a separate forward test.
    """

    souls: frozenset
    messages: frozenset
    soul_models: _SSMapping
    soul_senses: _SSMapping
    soul_memory: _SSMapping
    heartbeat_seconds: int
    cost_ceiling: float

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticSurface):
            return NotImplemented
        return (
            self.souls == other.souls
            and self.messages == other.messages
            and dict(self.soul_models) == dict(other.soul_models)
            and {k: set(v) for k, v in self.soul_senses.items()}
            == {k: set(v) for k, v in other.soul_senses.items()}
            and {k: set(v) for k, v in self.soul_memory.items()}
            == {k: set(v) for k, v in other.soul_memory.items()}
            and self.heartbeat_seconds == other.heartbeat_seconds
            and self.cost_ceiling == other.cost_ceiling
        )

    def __hash__(self) -> int:
        return hash((self.souls, self.messages, self.heartbeat_seconds))


def derive_runtime_surface(program: "NousProgram") -> SemanticSurface:
    """Derive the semantic surface the live runner consumes, from the AST.

    Mirrors the setup logic of execute_program (soul registration, law
    constants) without running any cycle. Standalone by design: the
    derivation needs no runtime state, so re-deriving here keeps
    execute_program byte-identical and side-effect free.
    """
    world = program.world
    if world is not None:
        heartbeat = _extract_heartbeat(world)
        cost_ceiling = _extract_cost_ceiling(world)
    else:
        heartbeat = 300
        cost_ceiling = 0.10

    souls = frozenset(s.name for s in program.souls)
    messages = frozenset(m.name for m in program.messages)

    soul_models: dict = {}
    soul_senses: dict = {}
    soul_memory: dict = {}
    for soul in program.souls:
        if soul.mind is not None:
            model = soul.mind.model
            tier = soul.mind.tier.value
        else:
            model = "unknown"
            tier = "Tier1"
        soul_models[soul.name] = model + " @ " + tier
        soul_senses[soul.name] = frozenset(soul.senses or [])
        fields = set()
        if soul.memory is not None:
            for f in soul.memory.fields:
                fields.add(f.name if hasattr(f, "name") else str(f))
        soul_memory[soul.name] = frozenset(fields)

    return SemanticSurface(
        souls=souls,
        messages=messages,
        soul_models=soul_models,
        soul_senses=soul_senses,
        soul_memory=soul_memory,
        heartbeat_seconds=int(heartbeat),
        cost_ceiling=float(cost_ceiling),
    )
