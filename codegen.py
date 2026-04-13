"""
NOUS CodeGen — Γέννηση (Genesis)
=================================
Transforms the Living AST into production-grade Python 3.11+ asyncio code.
Generated code uses Pydantic V2 for message types, asyncio.Queue for channels,
and asyncio.TaskGroup for parallel execution.
"""
from __future__ import annotations

import textwrap
from typing import Any

from ast_nodes import (
    NousProgram, WorldNode, SoulNode, MindNode, MemoryNode,
    InstinctNode, DnaNode, HealNode, HealRuleNode, HealActionNode,
    HealStrategy, MessageNode, NervousSystemNode, RouteNode,
    MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
    EvolutionNode, PerceptionNode, LetNode, RememberNode,
    SpeakNode, GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
    GeneNode, LawCost, LawDuration, LawBool, LawInt, LawConstitutional,
    LawCurrency,
)


class NousCodeGen:
    """Generates Python 3.11+ asyncio code from a validated NousProgram."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.indent_level = 0
        self.lines: list[str] = []

    def generate(self) -> str:
        self._emit_header()
        self._emit_imports()
        self._emit_blank()
        self._emit_law_constants()
        self._emit_blank()
        self._emit_message_classes()
        self._emit_channel_registry()
        self._emit_blank()
        self._emit_soul_classes()
        self._emit_nervous_system()
        self._emit_world_runner()
        self._emit_main()
        return "\n".join(self.lines)

    # ── Output helpers ──

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

    # ── Header ──

    def _emit_header(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""')
        self._emit(f"NOUS Generated Code — {world_name}")
        self._emit(f"Auto-generated from .nous source. Do not edit manually.")
        self._emit(f"Runtime: Python 3.11+ asyncio")
        self._emit(f'"""')

    # ── Imports ──

    def _emit_imports(self) -> None:
        self._emit("from __future__ import annotations")
        self._emit_blank()
        self._emit("import asyncio")
        self._emit("import logging")
        self._emit("import time")
        self._emit("from dataclasses import dataclass, field")
        self._emit("from typing import Any, Optional")
        self._emit("from enum import Enum")
        self._emit_blank()
        self._emit("try:")
        self._indent()
        self._emit("from pydantic import BaseModel, Field")
        self._dedent()
        self._emit("except ImportError:")
        self._indent()
        self._emit("BaseModel = object  # fallback")
        self._emit("def Field(**kw): return kw.get('default')")
        self._dedent()
        self._emit_blank()
        self._emit("log = logging.getLogger('nous.runtime')")

    # ── Laws ──

    def _emit_law_constants(self) -> None:
        if not self.program.world:
            return
        self._emit("# ═══ World Laws ═══")
        self._emit_blank()
        world = self.program.world
        self._emit(f"WORLD_NAME = \"{world.name}\"")
        if world.heartbeat:
            seconds = self._duration_to_seconds(world.heartbeat)
            self._emit(f"HEARTBEAT_SECONDS = {seconds}")
        else:
            self._emit("HEARTBEAT_SECONDS = 300")

        for law in world.laws:
            name = f"LAW_{law.name.upper()}"
            if isinstance(law.expr, LawCost):
                self._emit(f"{name} = {law.expr.amount}  # {law.expr.currency} per {law.expr.per}")
            elif isinstance(law.expr, LawDuration):
                self._emit(f"{name} = {law.expr.value}  # {law.expr.unit}")
            elif isinstance(law.expr, LawBool):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawInt):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawConstitutional):
                self._emit(f"{name} = {law.expr.count}")
            elif isinstance(law.expr, LawCurrency):
                self._emit(f"{name} = {law.expr.amount}  # {law.expr.currency}")

    # ── Messages ──

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

    # ── Channels ──

    def _emit_channel_registry(self) -> None:
        self._emit("# ═══ Channel Registry ═══")
        self._emit_blank()
        self._emit("class ChannelRegistry:")
        self._indent()
        self._emit("def __init__(self) -> None:")
        self._indent()
        self._emit("self._channels: dict[str, asyncio.Queue] = {}")
        self._dedent()
        self._emit_blank()
        self._emit("def get(self, key: str) -> asyncio.Queue:")
        self._indent()
        self._emit("if key not in self._channels:")
        self._indent()
        self._emit("self._channels[key] = asyncio.Queue(maxsize=100)")
        self._dedent()
        self._emit("return self._channels[key]")
        self._dedent()
        self._emit_blank()
        self._emit("async def send(self, key: str, message: Any) -> None:")
        self._indent()
        self._emit("await self.get(key).put(message)")
        self._emit("log.debug(f'Channel {key}: message sent')")
        self._dedent()
        self._emit_blank()
        self._emit("async def receive(self, key: str, timeout: float = 30.0) -> Any:")
        self._indent()
        self._emit("try:")
        self._indent()
        self._emit("return await asyncio.wait_for(self.get(key).get(), timeout=timeout)")
        self._dedent()
        self._emit("except asyncio.TimeoutError:")
        self._indent()
        self._emit("raise TimeoutError(f'Channel {key}: receive timeout after {timeout}s')")
        self._dedent()
        self._dedent()
        self._dedent()
        self._emit_blank()
        self._emit("channels = ChannelRegistry()")

    # ── Souls ──

    def _emit_soul_classes(self) -> None:
        self._emit("# ═══ Soul Definitions ═══")
        for soul in self.program.souls:
            self._emit_blank()
            self._emit_soul(soul)

    def _emit_soul(self, soul: SoulNode) -> None:
        self._emit(f"class Soul_{soul.name}:")
        self._indent()
        self._emit(f'"""Soul: {soul.name}"""')
        self._emit_blank()

        # __init__
        self._emit("def __init__(self) -> None:")
        self._indent()
        self._emit(f"self.name = \"{soul.name}\"")
        if soul.mind:
            self._emit(f"self.model = \"{soul.mind.model}\"")
            self._emit(f"self.tier = \"{soul.mind.tier.value}\"")
        self._emit(f"self.senses = {soul.senses}")
        self._emit("self.cycle_count = 0")
        self._emit("self._alive = True")

        # Memory fields
        if soul.memory:
            for f in soul.memory.fields:
                default = self._value_to_python(f.default)
                self._emit(f"self.{f.name} = {default}")

        # DNA
        if soul.dna:
            for gene in soul.dna.genes:
                self._emit(f"self.dna_{gene.name} = {self._value_to_python(gene.value)}")

        self._dedent()
        self._emit_blank()

        # instinct method
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

        # heal method
        self._emit("async def heal(self, error: Exception) -> bool:")
        self._indent()
        self._emit(f'"""Error recovery for {soul.name}"""')
        self._emit("error_type = type(error).__name__.lower()")
        if soul.heal and soul.heal.rules:
            for i, rule in enumerate(soul.heal.rules):
                keyword = "if" if i == 0 else "elif"
                self._emit(f"{keyword} error_type == \"{rule.error_type}\" or \"{rule.error_type}\" in str(error).lower():")
                self._indent()
                for action in rule.actions:
                    self._emit_heal_action(action)
                self._emit("return True")
                self._dedent()
            self._emit("log.warning(f'{self.name}: unhandled error: {error}')")
            self._emit("return False")
        else:
            self._emit("log.warning(f'{self.name}: no heal rules, error: {error}')")
            self._emit("return False")
        self._dedent()
        self._emit_blank()

        # run loop
        self._emit("async def run(self) -> None:")
        self._indent()
        self._emit(f'"""Main loop for {soul.name}"""')
        self._emit("while self._alive:")
        self._indent()
        self._emit("try:")
        self._indent()
        self._emit("await self.instinct()")
        self._emit("self.cycle_count += 1")
        self._emit(f"log.info(f'{{self.name}}: cycle {{self.cycle_count}} complete')")
        self._dedent()
        self._emit("except Exception as e:")
        self._indent()
        self._emit(f"log.error(f'{{self.name}}: error in cycle {{self.cycle_count}}: {{e}}')")
        self._emit("recovered = await self.heal(e)")
        self._emit("if not recovered:")
        self._indent()
        self._emit(f"log.critical(f'{{self.name}}: unrecoverable error, stopping')")
        self._emit("self._alive = False")
        self._dedent()
        self._dedent()
        self._emit("await asyncio.sleep(HEARTBEAT_SECONDS)")
        self._dedent()
        self._dedent()

        self._dedent()

    # ── Statement codegen ──

    def _emit_statement(self, stmt: Any, soul_name: str) -> None:
        if isinstance(stmt, LetNode):
            value = stmt.value
            if isinstance(value, dict):
                kind = value.get("kind", "")
                if kind == "listen":
                    channel = f"{value['soul']}_{value['type']}"
                    self._emit(f"{stmt.name} = await channels.receive(\"{channel}\")")
                    return
                elif kind == "sense_call":
                    tool = value.get("tool", "unknown")
                    args = value.get("args", {})
                    args_str = self._args_to_python(args)
                    self._emit(f"{stmt.name} = await self._sense_{tool}({args_str})")
                    return
            self._emit(f"{stmt.name} = {self._expr_to_python(value)}")

        elif isinstance(stmt, RememberNode):
            val = self._expr_to_python(stmt.value)
            if stmt.op == "+=":
                self._emit(f"self.{stmt.name} += {val}")
            else:
                self._emit(f"self.{stmt.name} = {val}")

        elif isinstance(stmt, SpeakNode):
            channel = f"{soul_name}_{stmt.message_type}"
            args_str = self._kv_to_python(stmt.args)
            self._emit(f"await channels.send(\"{channel}\", {stmt.message_type}({args_str}))")

        elif isinstance(stmt, GuardNode):
            cond = self._expr_to_python(stmt.condition)
            self._emit(f"if not ({cond}):")
            self._indent()
            self._emit("return  # guard failed")
            self._dedent()

        elif isinstance(stmt, SenseCallNode):
            args_str = self._args_to_python(stmt.args)
            if stmt.bind_name:
                self._emit(f"{stmt.bind_name} = await self._sense_{stmt.tool_name}({args_str})")
            else:
                self._emit(f"await self._sense_{stmt.tool_name}({args_str})")

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
            if kind == "method_call":
                self._emit(self._expr_to_python(stmt))
            elif kind == "func_call":
                self._emit(self._expr_to_python(stmt))

    # ── Heal action codegen ──

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

    # ── Nervous System ──

    def _emit_nervous_system(self) -> None:
        ns = self.program.nervous_system
        if not ns:
            return
        self._emit_blank()
        self._emit("# ═══ Nervous System ═══")
        self._emit_blank()
        self._emit("def build_topology() -> dict[str, list[str]]:")
        self._indent()
        self._emit('"""Build the execution DAG from nervous_system declaration."""')
        self._emit("graph: dict[str, list[str]] = {}")
        for route in ns.routes:
            if isinstance(route, RouteNode):
                self._emit(f"graph.setdefault(\"{route.source}\", []).append(\"{route.target}\")")
            elif isinstance(route, FanInNode):
                for src in route.sources:
                    self._emit(f"graph.setdefault(\"{src}\", []).append(\"{route.target}\")")
            elif isinstance(route, FanOutNode):
                for tgt in route.targets:
                    self._emit(f"graph.setdefault(\"{route.source}\", []).append(\"{tgt}\")")
        self._emit("return graph")
        self._dedent()

    # ── World runner ──

    def _emit_world_runner(self) -> None:
        self._emit_blank()
        self._emit("# ═══ World Runner ═══")
        self._emit_blank()
        self._emit("async def run_world() -> None:")
        self._indent()
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""Boot and run world: {world_name}"""')
        self._emit(f"log.info(f'Booting world: {world_name}')")
        self._emit_blank()

        # Instantiate souls
        self._emit("# Spawn souls")
        self._emit("souls = {}")
        for soul in self.program.souls:
            self._emit(f"souls[\"{soul.name}\"] = Soul_{soul.name}()")
            self._emit(f"log.info(f'Spawned soul: {soul.name}')")
        self._emit_blank()

        # Build topology
        if self.program.nervous_system:
            self._emit("topology = build_topology()")
            self._emit("log.info(f'Nervous system: {topology}')")
            self._emit_blank()

        # Run all souls
        self._emit("# Run all souls concurrently")
        self._emit("async with asyncio.TaskGroup() as tg:")
        self._indent()
        for soul in self.program.souls:
            self._emit(f"tg.create_task(souls[\"{soul.name}\"].run())")
        self._dedent()

        self._dedent()

    # ── Main ──

    def _emit_main(self) -> None:
        self._emit_blank()
        self._emit_blank()
        self._emit("if __name__ == \"__main__\":")
        self._indent()
        self._emit("logging.basicConfig(")
        self._indent()
        self._emit("level=logging.INFO,")
        self._emit("format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',")
        self._emit("datefmt='%H:%M:%S',")
        self._dedent()
        self._emit(")")
        self._emit("asyncio.run(run_world())")
        self._dedent()

    # ── Expression → Python ──

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
            # Check if it looks like a variable/identifier
            if expr.replace("_", "").replace(".", "").isalnum() and expr[0:1].isalpha():
                return expr
            # Otherwise it's a string value that needs quoting
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
                return f"souls[\"{expr['soul']}\"].{expr['field']}"
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
                return f"await channels.receive(\"{channel}\")"
            elif kind == "sense_call":
                tool = expr.get("tool", "")
                args = self._args_to_python(expr.get("args", {}))
                return f"await self._sense_{tool}({args})"
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
            "string": "str",
            "float": "float",
            "int": "int",
            "bool": "bool",
            "timestamp": "float",
            "duration": "float",
            "currency": "float",
            "SoulRef": "str",
            "ToolRef": "str",
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


def generate_python(program: NousProgram) -> str:
    """Generate Python code from a validated NousProgram."""
    gen = NousCodeGen(program)
    return gen.generate()
