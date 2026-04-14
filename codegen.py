"""
NOUS CodeGen v2 — Γέννηση (Genesis)
=====================================
Transforms the Living AST into production-grade Python 3.11+ asyncio code.
Event-driven architecture: entrypoint souls wake on heartbeat,
listener souls wake on message. Circuit breaker enforces cost ceiling.
Sense cache deduplicates API calls.
"""
from __future__ import annotations

from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MindNode, MemoryNode,
    InstinctNode, DnaNode, HealNode, HealRuleNode, HealActionNode,
    HealStrategy, MessageNode, NervousSystemNode, RouteNode,
    MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, PerceptionNode, LetNode, RememberNode,
    SpeakNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
    GeneNode, LawCost, LawDuration, LawBool, LawInt, LawConstitutional,
    TopologyNode, ServerNode,
)


class NousCodeGen:
    """Generates Python 3.11+ asyncio code with event-driven runtime."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.indent_level = 0
        self.lines: list[str] = []
        self._routes: list[tuple[str, str]] = []
        self._incoming: dict[str, list[str]] = {}
        self._outgoing: dict[str, list[str]] = {}
        self._entrypoints: set[str] = set()
        self._listeners: set[str] = set()
        self._cost_ceiling: float = 0.10
        self._heartbeat_seconds: int = 300
        self._analyze_topology()

    def _analyze_topology(self) -> None:
        ns = self.program.nervous_system
        if ns:
            for route in ns.routes:
                if isinstance(route, RouteNode):
                    self._routes.append((route.source, route.target))
                elif isinstance(route, FanInNode):
                    for src in route.sources:
                        self._routes.append((src, route.target))
                elif isinstance(route, FanOutNode):
                    for tgt in route.targets:
                        self._routes.append((route.source, tgt))

        for src, tgt in self._routes:
            self._outgoing.setdefault(src, []).append(tgt)
            self._incoming.setdefault(tgt, []).append(src)

        soul_names = {s.name for s in self.program.souls}
        self._listeners = soul_names & set(self._incoming.keys())
        self._entrypoints = soul_names - self._listeners

        if self.program.world:
            hb = self.program.world.heartbeat
            if hb:
                self._heartbeat_seconds = self._duration_to_seconds(hb)
            for law in self.program.world.laws:
                if isinstance(law.expr, LawCost) and law.expr.per == "cycle":
                    self._cost_ceiling = law.expr.amount

    def generate(self, node_filter: str | None = None) -> str:
        self._node_filter = node_filter
        self._emit_header()
        self._emit_imports()
        self._emit_blank()
        self._emit_law_constants()
        self._emit_blank()
        self._emit_message_classes()
        self._emit_blank()
        if hasattr(self.program, 'noesis') and self.program.noesis:
            self._emit_noesis_init()
        self._emit_soul_classes()
        if self.program.topology and self.program.topology.servers:
            self._emit_build_distributed_runtime()
        else:
            self._emit_build_runtime()
        self._emit_main()
        return "\n".join(self.lines)

    def _emit(self, text: str = "") -> None:
        if not text:
            self.lines.append("")
        else:
            self.lines.append("    " * self.indent_level + text)

    def _emit_blank(self) -> None:
        self.lines.append("")

    def _indent(self) -> None:
        self.indent_level += 1

    def _dedent(self) -> None:
        self.indent_level = max(0, self.indent_level - 1)

    def _emit_header(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""')
        self._emit(f"NOUS Generated Code — {world_name}")
        self._emit(f"Auto-generated from .nous source. Do not edit manually.")
        self._emit(f"Runtime: Python 3.11+ asyncio | Event-Driven Architecture")
        self._emit(f'"""')

    def _emit_imports(self) -> None:
        self._emit("from __future__ import annotations")
        self._emit_blank()
        self._emit("import asyncio")
        self._emit("import logging")
        self._emit("import time")
        self._emit("from typing import Any, Optional")
        self._emit_blank()
        self._emit("try:")
        self._indent()
        self._emit("from pydantic import BaseModel, Field")
        self._dedent()
        self._emit("except ImportError:")
        self._indent()
        self._emit("BaseModel = object")
        self._emit("def Field(**kw): return kw.get('default')")
        self._dedent()
        self._emit_blank()
        self._emit("from runtime import (")
        self._indent()
        self._emit("NousRuntime, SoulRunner, SoulWakeStrategy,")
        self._emit("CircuitBreakerTripped, CostTracker, SenseCache,")
        self._emit("ChannelRegistry, SenseExecutor, DistributedRuntime,")
        self._dedent()
        self._emit(")")
        has_mitosis = any(s.mitosis for s in self.program.souls)
        if has_mitosis:
            self._emit("from mitosis_engine import MitosisEngine, MitosisConfig")
        has_immune = any(s.immune_system for s in self.program.souls)
        if has_immune:
            self._emit("from immune_engine import ImmuneEngine, ImmuneConfig")
        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        if has_telemetry:
            self._emit("from telemetry_engine import TelemetryEngine, TelemetryConfig, SpanKind, SpanStatus")
        has_metabolism = any(s.metabolism for s in self.program.souls)
        if has_metabolism:
            self._emit("from metabolism_engine import MetabolismEngine, MetabolismConfig")
        has_symbiosis = any(s.symbiosis for s in self.program.souls)
        if has_symbiosis:
            self._emit("from symbiosis_engine import SymbiosisEngine, BondConfig")
        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit("from dream_engine import DreamEngine, DreamConfig")
        self._emit_blank()
        self._emit("log = logging.getLogger('nous.runtime')")

    def _emit_noesis_init(self) -> None:
        config = self.program.noesis
        lattice = config.lattice_path or "noesis_lattice.json"
        threshold = config.oracle_threshold
        auto_learn = config.auto_learn
        self._emit("# ═══ Noesis Symbolic Intelligence ═══")
        self._emit("from noesis_engine import NoesisEngine")
        self._emit("from pathlib import Path as _NoesisPath")
        self._emit("_noesis_engine = NoesisEngine()")
        self._emit(f'_noesis_lattice_path = _NoesisPath("{lattice}")')
        self._emit("if _noesis_lattice_path.exists():")
        self._emit("    _noesis_engine.load(_noesis_lattice_path)")
        self._emit(f"_noesis_engine.oracle.confidence_threshold = {threshold}")
        self._emit(f"_noesis_auto_learn = {auto_learn}")
        self._emit_blank()

    def _emit_law_constants(self) -> None:
        if not self.program.world:
            return
        self._emit("# ═══ World Laws ═══")
        self._emit_blank()
        world = self.program.world
        self._emit(f'WORLD_NAME = "{world.name}"')
        self._emit(f"HEARTBEAT_SECONDS = {self._heartbeat_seconds}")
        self._emit(f"COST_CEILING = {self._cost_ceiling}")

        for law in world.laws:
            name = f"LAW_{law.name.upper()}"
            if isinstance(law.expr, LawCost):
                self._emit(f"{name} = {law.expr.amount}")
            elif isinstance(law.expr, LawDuration):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawBool):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawInt):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawConstitutional):
                self._emit(f"{name} = {law.expr.count}")

        self._emit_blank()
        ep_list = sorted(self._entrypoints)
        ls_list = sorted(self._listeners)
        self._emit(f"ENTRYPOINT_SOULS = {ep_list}")
        self._emit(f"LISTENER_SOULS = {ls_list}")

    def _emit_message_classes(self) -> None:
        if not self.program.messages:
            return
        self._emit("# ═══ Message Types ═══")
        self._emit_blank()
        for msg in self.program.messages:
            self._emit(f"class {msg.name}(BaseModel):")
            self._indent()
            if not msg.fields:
                self._emit("pass")
            else:
                for f in msg.fields:
                    py_type = self._type_to_python(f.type_expr)
                    if f.default is not None:
                        self._emit(f"{f.name}: {py_type} = {self._value_to_python(f.default)}")
                    else:
                        self._emit(f"{f.name}: {py_type}")
            self._dedent()
            self._emit_blank()

    def _emit_soul_classes(self) -> None:
        self._emit("# ═══ Soul Definitions ═══")
        for soul in self.program.souls:
            self._emit_blank()
            self._emit_soul(soul)

    def _emit_soul(self, soul: SoulNode) -> None:
        is_listener = soul.name in self._listeners
        wake = "LISTENER" if is_listener else "HEARTBEAT"

        self._emit(f"class Soul_{soul.name}:")
        self._indent()
        self._emit(f'"""Soul: {soul.name} | Wake: {wake}"""')
        self._emit_blank()

        self._emit("def __init__(self, runtime: NousRuntime) -> None:")
        self._indent()
        self._emit(f'self.name = "{soul.name}"')
        self._emit("self._runtime = runtime")
        if soul.mind:
            self._emit(f'self.model = "{soul.mind.model}"')
            self._emit(f'self.tier = "{soul.mind.tier.value}"')
        else:
            self._emit('self.model = "unknown"')
            self._emit('self.tier = "Tier1"')
        self._emit(f"self.senses = {soul.senses}")
        self._emit("self.cycle_count = 0")

        if soul.memory:
            for f in soul.memory.fields:
                default = self._value_to_python(f.default)
                self._emit(f"self.{f.name} = {default}")

        if soul.dna:
            for gene in soul.dna.genes:
                self._emit(f"self.dna_{gene.name} = {self._value_to_python(gene.value)}")

        self._dedent()
        self._emit_blank()

        self._emit("async def _sense(self, tool_name: str, **kwargs: Any) -> Any:")
        self._indent()
        self._emit("return await self._runtime.sense_executor.call(tool_name, kwargs)")
        self._dedent()
        self._emit_blank()

        self._emit("async def instinct(self) -> None:")
        self._indent()
        self._emit(f'"""Instinct cycle for {soul.name}"""')
        if soul.instinct and soul.instinct.statements:
            for stmt in soul.instinct.statements:
                self._emit_statement(stmt, soul.name)
        else:
            self._emit("pass")
        self._dedent()
        self._emit_blank()

        self._emit("async def heal(self, error: Exception) -> bool:")
        self._indent()
        self._emit("error_type = type(error).__name__.lower()")
        if soul.heal and soul.heal.rules:
            for i, rule in enumerate(soul.heal.rules):
                keyword = "if" if i == 0 else "elif"
                self._emit(f'{keyword} error_type == "{rule.error_type}" or "{rule.error_type}" in str(error).lower():')
                self._indent()
                for action in rule.actions:
                    self._emit_heal_action(action)
                self._emit("return True")
                self._dedent()
            self._emit(f"log.warning(f'{{self.name}}: unhandled error: {{error}}')")
            self._emit("return False")
        else:
            self._emit(f"log.warning(f'{{self.name}}: no heal rules, error: {{error}}')")
            self._emit("return False")
        self._dedent()


        if soul.mitosis:
            self._emit_blank()
            self._emit_mitosis_methods(soul)

        self._dedent()

    def _emit_mitosis_methods(self, soul: SoulNode) -> None:
        m = soul.mitosis
        self._emit("def _mitosis_check(self, _metrics=None) -> bool:")
        self._indent()
        self._emit("metrics = {")
        self._indent()
        self._emit(f'"cycle_count": self.cycle_count,')
        self._emit(f'"queue_depth": getattr(self, "_queue_depth", 0),')
        self._emit(f'"latency": getattr(self, "_last_latency", 0.0),')
        self._emit(f'"error_count": getattr(self, "_error_count", 0),')
        if soul.memory:
            for f in soul.memory.fields:
                self._emit(f'"{f.name}": self.{f.name},')
        self._dedent()
        self._emit("}")
        trigger_code = self._expr_to_python(m.trigger)
        trigger_code = trigger_code.replace("scan_count", 'metrics.get("scan_count", 0)')
        trigger_code = trigger_code.replace("queue_depth", 'metrics.get("queue_depth", 0)')
        trigger_code = trigger_code.replace("latency", 'metrics.get("latency", 0)')
        trigger_code = trigger_code.replace("error_count", 'metrics.get("error_count", 0)')
        trigger_code = trigger_code.replace("cycle_count", 'metrics.get("cycle_count", 0)')
        if soul.memory:
            for f in soul.memory.fields:
                if f.name not in ("scan_count", "queue_depth", "latency", "error_count", "cycle_count"):
                    trigger_code = trigger_code.replace(f.name, f'metrics.get("{f.name}", 0)')
        self._emit(f"return {trigger_code}")
        self._dedent()
        self._emit_blank()

        if m.retire_trigger is not None:
            self._emit("def _retire_check(self, _metrics=None) -> bool:")
            self._indent()
            self._emit("metrics = {")
            self._indent()
            self._emit(f'"cycle_count": self.cycle_count,')
            self._emit(f'"queue_depth": getattr(self, "_queue_depth", 0),')
            self._emit(f'"latency": getattr(self, "_last_latency", 0.0),')
            self._emit(f'"error_count": getattr(self, "_error_count", 0),')
            if soul.memory:
                for f in soul.memory.fields:
                    self._emit(f'"{f.name}": self.{f.name},')
            self._dedent()
            self._emit("}")
            retire_code = self._expr_to_python(m.retire_trigger)
            retire_code = retire_code.replace("scan_count", 'metrics.get("scan_count", 0)')
            retire_code = retire_code.replace("queue_depth", 'metrics.get("queue_depth", 0)')
            retire_code = retire_code.replace("latency", 'metrics.get("latency", 0)')
            retire_code = retire_code.replace("error_count", 'metrics.get("error_count", 0)')
            retire_code = retire_code.replace("cycle_count", 'metrics.get("cycle_count", 0)')
            if soul.memory:
                for f in soul.memory.fields:
                    if f.name not in ("scan_count", "queue_depth", "latency", "error_count", "cycle_count"):
                        retire_code = retire_code.replace(f.name, f'metrics.get("{f.name}", 0)')
            self._emit(f"return {retire_code}")
            self._dedent()
            self._emit_blank()

        self._emit("@classmethod")
        self._emit("def clone_factory(cls, clone_name: str, clone_tier: str | None, runtime: NousRuntime) -> 'Soul_" + soul.name + "':")
        self._indent()
        self._emit(f"clone = cls(runtime)")
        self._emit(f"clone.name = clone_name")
        if soul.mind:
            self._emit(f'clone.tier = clone_tier or "{soul.mind.tier.value}"')
        self._emit(f"return clone")
        self._dedent()

    def _emit_statement(self, stmt: Any, soul_name: str) -> None:  # dream_cache_inject
        if isinstance(stmt, LetNode):
            value = stmt.value
            if isinstance(value, dict):
                kind = value.get("kind", "")
                if kind == "listen":
                    src_soul = value.get("soul", "")
                    msg_type = value.get("type", "")
                    channel = f"{src_soul}_{msg_type}"
                    self._emit(f'{stmt.name} = await self._runtime.channels.receive("{channel}")')
                    return
                elif kind == "resonate":
                    query = value.get("query", "")
                    is_dynamic = value.get("is_dynamic", False)
                    if is_dynamic:
                        query_expr = self._expr_to_python(query)
                        self._emit(f"{stmt.name} = _noesis_engine.think(str({query_expr}))")
                    else:
                        self._emit(f'{stmt.name} = _noesis_engine.think("{query}")')
                    gf = value.get("guard_field")
                    gt = value.get("guard_threshold")
                    if gf and gt is not None:
                        self._emit(f"if {stmt.name}.{gf} < {gt}:")
                        self._emit(f"    pass")
                    return
                elif kind == "sense_call":
                    tool = value.get("tool", "unknown")
                    args = value.get("args", {})
                    if tool in ("check_dream_cache", "dream_cache"):
                        args["soul"] = f'"{soul_name}"'
                    args_str = self._sense_args_to_python(args)
                    self._emit(f'{stmt.name} = await self._sense("{tool}", {args_str})')
                    return
            self._emit(f"{stmt.name} = {self._expr_to_python(value)}")

        elif isinstance(stmt, RememberNode):
            val = self._expr_to_python(stmt.value)
            if stmt.op == "+=":
                self._emit(f"self.{stmt.name} += {val}")
            else:
                self._emit(f"self.{stmt.name} = {val}")

        elif isinstance(stmt, SpeakNode):
            if stmt.target_world:
                channel = f"cross_{stmt.target_world}_{stmt.message_type}"
            else:
                channel = f"{soul_name}_{stmt.message_type}"
            args_str = self._kv_to_python(stmt.args)
            self._emit(f'await self._runtime.channels.send("{channel}", {stmt.message_type}({args_str}))')

        elif isinstance(stmt, GuardNode):
            cond = self._expr_to_python(stmt.condition)
            self._emit(f"if not ({cond}):")
            self._indent()
            self._emit("return")
            self._dedent()

        elif isinstance(stmt, SenseCallNode):
            args_str = self._sense_args_to_python(stmt.args)
            if stmt.tool_name in ("check_dream_cache", "dream_cache"):
                if args_str:
                    args_str = f'soul="{soul_name}", {args_str}'
                else:
                    args_str = f'soul="{soul_name}"'
            if stmt.bind_name:
                self._emit(f'{stmt.bind_name} = await self._sense("{stmt.tool_name}", {args_str})')
            else:
                self._emit(f'await self._sense("{stmt.tool_name}", {args_str})')

        elif isinstance(stmt, SleepNode):
            self._emit(f"await asyncio.sleep(HEARTBEAT_SECONDS * {stmt.cycles})")

        elif isinstance(stmt, IfNode):
            cond = self._expr_to_python(stmt.condition)
            self._emit(f"if {cond}:")
            self._indent()
            if stmt.then_body:
                for s in stmt.then_body:
                    self._emit_statement(s, soul_name)
            else:
                self._emit("pass")
            self._dedent()
            if stmt.else_body:
                self._emit("else:")
                self._indent()
                for s in stmt.else_body:
                    self._emit_statement(s, soul_name)
                self._dedent()

        elif isinstance(stmt, ForNode):
            iterable = self._expr_to_python(stmt.iterable)
            self._emit(f"for {stmt.var_name} in {iterable}:")
            self._indent()
            if stmt.body:
                for s in stmt.body:
                    self._emit_statement(s, soul_name)
            else:
                self._emit("pass")
            self._dedent()

        elif isinstance(stmt, dict):
            kind = stmt.get("kind", "")
            if kind in ("method_call", "func_call"):
                self._emit(self._expr_to_python(stmt))

    def _emit_heal_action(self, action: HealActionNode) -> None:
        if action.strategy == HealStrategy.RETRY:
            max_r = action.params.get("max", 1)
            backoff = action.params.get("backoff", "fixed")
            self._emit(f"for _retry in range({max_r}):")
            self._indent()
            if backoff == "exponential":
                self._emit("await asyncio.sleep(2 ** _retry)")
            else:
                self._emit("await asyncio.sleep(1)")
            self._emit("try:")
            self._indent()
            self._emit("await self.instinct()")
            self._emit("break")
            self._dedent()
            self._emit("except Exception:")
            self._indent()
            self._emit("continue")
            self._dedent()
            self._dedent()
        elif action.strategy == HealStrategy.LOWER:
            param = action.params.get("param", "")
            delta = action.params.get("delta", 0)
            self._emit(f"self.dna_{param} = max(0, self.dna_{param} - {self._value_to_python(delta)})")
            self._emit(f"log.info(f'{{self.name}}: lowered {param} to {{self.dna_{param}}}')")
        elif action.strategy == HealStrategy.RAISE:
            param = action.params.get("param", "")
            delta = action.params.get("delta", 0)
            self._emit(f"self.dna_{param} += {self._value_to_python(delta)}")
        elif action.strategy == HealStrategy.HIBERNATE:
            self._emit("log.info(f'{self.name}: hibernating until next cycle')")
            self._emit("await asyncio.sleep(HEARTBEAT_SECONDS)")
        elif action.strategy == HealStrategy.FALLBACK:
            target = action.params.get("target", "")
            self._emit(f"log.info(f'{{self.name}}: falling back to {target}')")
        elif action.strategy == HealStrategy.SLEEP:
            cycles = action.params.get("cycles", 1)
            self._emit(f"await asyncio.sleep(HEARTBEAT_SECONDS * {cycles})")
        elif action.strategy == HealStrategy.ALERT:
            channel = action.params.get("channel", "")
            self._emit(f"log.warning(f'{{self.name}}: ALERT sent to {channel}')")

    def _emit_build_runtime(self) -> None:
        self._emit_blank()
        self._emit("# ═══ Runtime Builder ═══")
        self._emit_blank()
        self._emit("def build_runtime() -> NousRuntime:")
        self._indent()
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""Build event-driven runtime for {world_name}"""')
        self._emit(f"rt = NousRuntime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit(f"cost_ceiling=COST_CEILING,")
        self._dedent()
        self._emit(")")
        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        if has_telemetry:
            t = self.program.world.telemetry
            self._emit_blank()
            self._emit("# ═══ Telemetry Engine ═══")
            endpoint_str = f'"{t.endpoint}"' if t.endpoint else "None"
            self._emit(f"_telemetry = TelemetryEngine(TelemetryConfig(")
            self._indent()
            self._emit(f"enabled=True,")
            self._emit(f'exporter="{t.exporter}",')
            self._emit(f"endpoint={endpoint_str},")
            self._emit(f"sample_rate={t.sample_rate},")
            self._emit(f"trace_senses={t.trace_senses},")
            self._emit(f"trace_llm={t.trace_llm},")
            self._emit(f"buffer_size={t.buffer_size},")
            self._dedent()
            self._emit(f"))")
            self._emit(f"rt._telemetry_engine = _telemetry")
        self._emit_blank()

        for soul in self.program.souls:
            sname = soul.name
            is_listener = sname in self._listeners
            wake = "SoulWakeStrategy.LISTENER" if is_listener else "SoulWakeStrategy.HEARTBEAT"
            tier = f'"{soul.mind.tier.value}"' if soul.mind else '"Tier1"'

            listen_ch = "None"
            if is_listener:
                sources = self._incoming.get(sname, [])
                if sources:
                    first_src = sources[0]
                    first_src_soul = self._find_soul(first_src)
                    if first_src_soul and first_src_soul.instinct:
                        msg_type = self._find_speak_type(first_src_soul)
                        if msg_type:
                            listen_ch = f'"{first_src}_{msg_type}"'

            self._emit(f"_soul_{sname.lower()} = Soul_{sname}(rt)")
            self._emit(f"rt.add_soul(SoulRunner(")
            self._indent()
            self._emit(f'name="{sname}",')
            self._emit(f"wake_strategy={wake},")
            self._emit(f"instinct_fn=_soul_{sname.lower()}.instinct,")
            self._emit(f"heal_fn=_soul_{sname.lower()}.heal,")
            self._emit(f"listen_channel={listen_ch},")
            self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
            self._emit(f"tier={tier},")
            self._dedent()
            self._emit("))")
            self._emit_blank()

        has_mitosis = any(s.mitosis for s in self.program.souls)
        if has_mitosis:
            self._emit_blank()
            self._emit("# ═══ Mitosis Engine ═══")
            self._emit("mitosis = MitosisEngine(rt, check_interval=HEARTBEAT_SECONDS / 3)")
            for soul in self.program.souls:
                if soul.mitosis:
                    m = soul.mitosis
                    sn = soul.name
                    cooldown_s = self._duration_to_seconds(m.cooldown)
                    tier_str = f'"{m.clone_tier}"' if m.clone_tier else "None"
                    self._emit(f"mitosis.register(")
                    self._indent()
                    self._emit(f'"{sn}",')
                    self._emit(f"MitosisConfig(")
                    self._indent()
                    self._emit(f"trigger_fn=_soul_{sn.lower()}._mitosis_check,")
                    self._emit(f'trigger_expr="",')
                    self._emit(f"max_clones={m.max_clones},")
                    self._emit(f"cooldown_seconds={cooldown_s},")
                    self._emit(f"clone_tier={tier_str},")
                    self._emit(f"verify={m.verify},")
                    self._dedent()
                    self._emit(f"),")
                    self._emit(f"clone_factory=lambda name, tier, rt=rt: Soul_{sn}.clone_factory(name, tier, rt),")
                    self._dedent()
                    self._emit(f")")
                    if m.retire_trigger is not None:
                        retire_cd = self._duration_to_seconds(m.retire_cooldown)
                        self._emit(f"mitosis._configs[\"{sn}\"].retire_trigger_fn = _soul_{sn.lower()}._retire_check")
                        self._emit(f"mitosis._configs[\"{sn}\"].retire_cooldown_seconds = {retire_cd}")
                        self._emit(f"mitosis._configs[\"{sn}\"].min_clones = {m.min_clones}")
            self._emit("rt._mitosis_engine = mitosis")
            self._emit_blank()

        has_dream = any(s.dream_system for s in self.program.souls)
        if has_dream:
            self._emit_blank()
            self._emit("# ═══ Dream Engine ═══")
            self._emit("dream = DreamEngine(rt)")
            for soul in self.program.souls:
                if soul.dream_system:
                    ds = soul.dream_system
                    sn = soul.name
                    dm_model = ds.dream_mind.model if ds.dream_mind else "deepseek-chat"
                    dm_tier = ds.dream_mind.tier.value if ds.dream_mind else "Tier1"
                    self._emit(f"dream.register(")
                    self._indent()
                    self._emit(f'"{sn}",')
                    self._emit(f"DreamConfig(")
                    self._indent()
                    self._emit(f"enabled={ds.enabled},")
                    self._emit(f"trigger_idle_sec={ds.trigger_idle_sec},")
                    self._emit(f'dream_mind_model="{dm_model}",')
                    self._emit(f'dream_mind_tier="{dm_tier}",')
                    self._emit(f"max_cache={ds.max_cache},")
                    self._emit(f"speculation_depth={ds.speculation_depth},")
                    self._dedent()
                    self._emit(f"),")
                    self._dedent()
                    self._emit(")")
            self._emit("rt._dream_engine = dream")
            self._emit("")
            self._emit("async def dream_cache_sense(**kwargs):")
            self._emit("    soul_name = kwargs.get('soul', '')")
            self._emit("    query = kwargs.get('query', '')")
            self._emit("    if not dream or not soul_name:")
            self._emit("        return None")
            self._emit("    insight = dream.check_cache(soul_name, query)")
            self._emit("    if insight:")
            self._emit("        return insight.precomputed_result")
            self._emit("    return None")
            self._emit("rt.sense_executor.register_tool('dream_cache', dream_cache_sense)")
            self._emit_blank()

        has_immune = any(s.immune_system for s in self.program.souls)
        if has_immune:
            self._emit_blank()
            self._emit("# ═══ Immune Engine ═══")
            self._emit("immune = ImmuneEngine(rt)")
            for soul in self.program.souls:
                if soul.immune_system:
                    im = soul.immune_system
                    sn = soul.name
                    self._emit(f"immune.register(")
                    self._indent()
                    self._emit(f'"{sn}",')
                    self._emit(f"ImmuneConfig(")
                    self._indent()
                    self._emit(f"adaptive_recovery={im.adaptive_recovery},")
                    self._emit(f"share_with_clones={im.share_with_clones},")
                    lifespan_s = self._duration_to_seconds(im.antibody_lifespan)
                    self._emit(f"antibody_lifespan_seconds={lifespan_s},")
                    self._dedent()
                    self._emit(f"),")
                    self._dedent()
                    self._emit(")")
            self._emit("rt._immune_engine = immune")
            self._emit_blank()

        self._emit("return rt")
        self._dedent()

    def _emit_build_distributed_runtime(self) -> None:
        self._emit_blank()
        self._emit("# ═══ Topology ═══")
        self._emit_blank()
        self._emit("TOPOLOGY = [")
        self._indent()
        speak_map: dict[str, str] = {}
        for soul in self.program.souls:
            msg_type = self._find_speak_type(soul)
            if msg_type:
                speak_map[soul.name] = f"{soul.name}_{msg_type}"
        for srv in self.program.topology.servers:
            self._emit(f'{{"name": "{srv.name}", "host": "{srv.host}", "port": {srv.port}, "souls": {srv.souls}}},')
        self._dedent()
        self._emit("]")
        self._emit_blank()
        speak_dict_str = ", ".join(f'"{k}": "{v}"' for k, v in speak_map.items())
        self._emit(f"SPEAK_CHANNELS = {{{speak_dict_str}}}")
        routes_str = ", ".join(f'("{src}", "{tgt}")' for src, tgt in self._routes)
        self._emit(f"ROUTES = [{routes_str}]")
        self._emit_blank()

        self._emit_blank()
        self._emit("# ═══ Runtime Builder ═══")
        self._emit_blank()
        self._emit("def build_runtime(node_name: str = \"\") -> NousRuntime:")
        self._indent()
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""Build runtime for {world_name} — auto-selects distributed if topology present."""')
        self._emit("if not node_name:")
        self._indent()
        self._emit("import sys, os")
        self._emit("node_name = os.environ.get(\"NOUS_NODE\", \"\")")
        self._emit("for arg in sys.argv:")
        self._indent()
        self._emit("if arg.startswith(\"--node=\"):")
        self._indent()
        self._emit("node_name = arg.split(\"=\", 1)[1]")
        self._dedent()
        self._dedent()
        self._dedent()
        self._emit_blank()
        self._emit("node_info = None")
        self._emit("for n in TOPOLOGY:")
        self._indent()
        self._emit("if n[\"name\"] == node_name:")
        self._indent()
        self._emit("node_info = n")
        self._emit("break")
        self._dedent()
        self._dedent()
        self._emit_blank()
        self._emit("if node_info:")
        self._indent()
        self._emit(f"rt = DistributedRuntime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit(f"cost_ceiling=COST_CEILING,")
        self._emit(f"node_name=node_name,")
        self._emit(f'node_host=node_info["host"],')
        self._emit(f'node_port=node_info["port"],')
        self._emit(f"topology=TOPOLOGY,")
        self._emit(f'local_souls=node_info["souls"],')
        self._dedent()
        self._emit(")")
        self._emit("rt.set_route_map(ROUTES, SPEAK_CHANNELS)")
        self._emit("local_set = set(node_info[\"souls\"])")
        self._dedent()
        self._emit("else:")
        self._indent()
        self._emit(f"rt = NousRuntime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit(f"cost_ceiling=COST_CEILING,")
        self._dedent()
        self._emit(")")
        has_telemetry = self.program.world and self.program.world.telemetry and self.program.world.telemetry.enabled
        if has_telemetry:
            t = self.program.world.telemetry
            self._emit_blank()
            self._emit("# ═══ Telemetry Engine ═══")
            endpoint_str = f'"{t.endpoint}"' if t.endpoint else "None"
            self._emit(f"_telemetry = TelemetryEngine(TelemetryConfig(")
            self._indent()
            self._emit(f"enabled=True,")
            self._emit(f'exporter="{t.exporter}",')
            self._emit(f"endpoint={endpoint_str},")
            self._emit(f"sample_rate={t.sample_rate},")
            self._emit(f"trace_senses={t.trace_senses},")
            self._emit(f"trace_llm={t.trace_llm},")
            self._emit(f"buffer_size={t.buffer_size},")
            self._dedent()
            self._emit(f"))")
            self._emit(f"rt._telemetry_engine = _telemetry")
        self._emit("local_set = None")
        self._dedent()
        self._emit_blank()

        for soul in self.program.souls:
            sname = soul.name
            is_listener = sname in self._listeners
            wake = "SoulWakeStrategy.LISTENER" if is_listener else "SoulWakeStrategy.HEARTBEAT"
            tier = f'"{soul.mind.tier.value}"' if soul.mind else '"Tier1"'

            listen_ch = "None"
            if is_listener:
                sources = self._incoming.get(sname, [])
                if sources:
                    first_src = sources[0]
                    first_src_soul = self._find_soul(first_src)
                    if first_src_soul and first_src_soul.instinct:
                        msg_type = self._find_speak_type(first_src_soul)
                        if msg_type:
                            listen_ch = f'"{first_src}_{msg_type}"'

            self._emit(f"if local_set is None or \"{sname}\" in local_set:")
            self._indent()
            self._emit(f"_soul_{sname.lower()} = Soul_{sname}(rt)")
            self._emit(f"rt.add_soul(SoulRunner(")
            self._indent()
            self._emit(f'name="{sname}",')
            self._emit(f"wake_strategy={wake},")
            self._emit(f"instinct_fn=_soul_{sname.lower()}.instinct,")
            self._emit(f"heal_fn=_soul_{sname.lower()}.heal,")
            self._emit(f"listen_channel={listen_ch},")
            self._emit(f"heartbeat_seconds=HEARTBEAT_SECONDS,")
            self._emit(f"tier={tier},")
            self._dedent()
            self._emit("))")
            self._dedent()
            self._emit_blank()

        self._emit("return rt")
        self._dedent()

    def _find_soul(self, name: str) -> SoulNode | None:
        for s in self.program.souls:
            if s.name == name:
                return s
        return None

    def _find_speak_type(self, soul: SoulNode) -> str | None:
        if not soul.instinct:
            return None
        for stmt in soul.instinct.statements:
            if isinstance(stmt, SpeakNode):
                return stmt.message_type
            if isinstance(stmt, IfNode):
                for s in stmt.then_body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
                for s in stmt.else_body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
            if isinstance(stmt, ForNode):
                for s in stmt.body:
                    if isinstance(s, SpeakNode):
                        return s.message_type
        return None

    def _emit_main(self) -> None:
        self._emit_blank()
        self._emit_blank()
        self._emit('if __name__ == "__main__":')
        self._indent()
        self._emit("logging.basicConfig(")
        self._indent()
        self._emit("level=logging.INFO,")
        self._emit("format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',")
        self._emit("datefmt='%H:%M:%S',")
        self._dedent()
        self._emit(")")
        self._emit("rt = build_runtime()")
        self._emit("asyncio.run(rt.run())")
        self._dedent()

    def _expr_to_python(self, expr: Any) -> str:
        if expr is None:
            return "None"
        if isinstance(expr, bool):
            return str(expr)
        if isinstance(expr, (int, float)):
            return str(expr)
        if isinstance(expr, str):
            if expr == "self":
                return "self"
            if expr == "now()":
                return "time.time()"
            if expr.startswith('"') or expr.startswith("'"):
                return expr
            if expr.replace("_", "").replace(".", "").isalnum() and expr[0:1].isalpha():
                return expr
            escaped = expr.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(expr, list):
            items = ", ".join(self._expr_to_python(i) for i in expr)
            return f"[{items}]"
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                left = self._expr_to_python(expr["left"])
                right = self._expr_to_python(expr["right"])
                op = expr["op"]
                if op == "&&":
                    op = "and"
                elif op == "||":
                    op = "or"
                return f"({left} {op} {right})"
            elif kind == "not":
                return f"not ({self._expr_to_python(expr['operand'])})"
            elif kind == "neg":
                return f"-({self._expr_to_python(expr['operand'])})"
            elif kind == "attr":
                obj = self._expr_to_python(expr["obj"])
                return f"{obj}.{expr['attr']}"
            elif kind == "method_call":
                obj = self._expr_to_python(expr["obj"])
                args = self._args_to_python(expr.get("args", {}))
                return f"{obj}.{expr['method']}({args})"
            elif kind == "func_call":
                func = self._expr_to_python(expr["func"])
                args = self._args_to_python(expr.get("args", {}))
                return f"{func}({args})"
            elif kind == "world_ref":
                path = expr.get("path", "")
                return f"world_config.{path}"
            elif kind == "soul_field":
                return f'souls["{expr["soul"]}"].{expr["field"]}'
            elif kind == "inline_if":
                cond = self._expr_to_python(expr["condition"])
                then = self._expr_to_python(expr["then"])
                else_ = self._expr_to_python(expr["else"])
                return f"({then} if {cond} else {else_})"
            elif kind == "message_construct":
                msg_type = expr.get("type", "")
                args = self._kv_to_python(expr.get("args", {}))
                return f"{msg_type}({args})"
            elif kind == "listen":
                channel = f"{expr['soul']}_{expr['type']}"
                return f'await self._runtime.channels.receive("{channel}")'
            elif kind == "sense_call":
                tool = expr.get("tool", "")
                args = self._sense_args_to_python(expr.get("args", {}))
                return f'await self._sense("{tool}", {args})'
            else:
                return str(expr)
        return str(expr)

    def _value_to_python(self, val: Any) -> str:
        if val is None:
            return "None"
        if isinstance(val, bool):
            return str(val)
        if isinstance(val, str):
            if val == "now()":
                return "time.time()"
            if val.startswith('"'):
                return val
            return f'"{val}"'
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, list):
            items = ", ".join(self._value_to_python(i) for i in val)
            return f"[{items}]"
        if isinstance(val, dict):
            return self._expr_to_python(val)
        return str(val)

    def _args_to_python(self, args: Any) -> str:
        if not args:
            return ""
        if isinstance(args, dict):
            parts = []
            for k, v in args.items():
                if k.startswith("_pos_"):
                    parts.append(self._expr_to_python(v))
                else:
                    parts.append(f"{k}={self._expr_to_python(v)}")
            return ", ".join(parts)
        return str(args)

    def _sense_args_to_python(self, args: Any) -> str:
        if not args:
            return ""
        if isinstance(args, dict):
            parts = []
            for k, v in args.items():
                if k.startswith("_pos_"):
                    parts.append(f"_pos_{k.split('_')[-1]}={self._expr_to_python(v)}")
                else:
                    parts.append(f"{k}={self._expr_to_python(v)}")
            return ", ".join(parts)
        return str(args)

    def _kv_to_python(self, kv: Any) -> str:
        if not kv:
            return ""
        if isinstance(kv, dict):
            parts = []
            for k, v in kv.items():
                parts.append(f"{k}={self._expr_to_python(v)}")
            return ", ".join(parts)
        return str(kv)

    def _type_to_python(self, type_expr: str) -> str:
        if type_expr.endswith("?"):
            inner = self._type_to_python(type_expr[:-1])
            return f"Optional[{inner}]"
        if type_expr.startswith("[") and type_expr.endswith("]"):
            inner = self._type_to_python(type_expr[1:-1])
            return f"list[{inner}]"
        mapping = {
            "string": "str", "float": "float", "int": "int", "bool": "bool",
            "timestamp": "float", "duration": "float", "currency": "float",
            "SoulRef": "str", "ToolRef": "str",
        }
        return mapping.get(type_expr, type_expr)

    def _duration_to_seconds(self, duration: str) -> int:
        if duration.endswith("ms"):
            return max(1, int(duration[:-2]) // 1000)
        unit = duration[-1]
        val = int(duration[:-1])
        if unit == "s":
            return val
        elif unit == "m":
            return val * 60
        elif unit == "h":
            return val * 3600
        elif unit == "d":
            return val * 86400
        return val


def generate_python(program: NousProgram, node_filter: str | None = None) -> str:
    gen = NousCodeGen(program)
    return gen.generate(node_filter=node_filter)
