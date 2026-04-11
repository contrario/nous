"""
NOUS CodeGen — Γέννηση (Genesis)
=================================
Transforms the Living AST into production-grade Python 3.11+ asyncio code.
Generated code uses the NOUS Runtime for tool dispatch, LLM calls, and channels.
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
)


class NousCodeGen:

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
        self._emit_channel_setup()
        self._emit_blank()
        self._emit_soul_classes()
        self._emit_nervous_system()
        self._emit_world_runner()
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
        self._emit('"""')
        self._emit(f"NOUS Generated Code — {world_name}")
        self._emit("Auto-generated from .nous source. Do not edit manually.")
        self._emit("Runtime: Python 3.11+ asyncio + NOUS Runtime")
        self._emit('"""')

    def _emit_imports(self) -> None:
        self._emit("from __future__ import annotations")
        self._emit_blank()
        self._emit("import asyncio")
        self._emit("import logging")
        self._emit("import time")
        self._emit("from typing import Any, Optional")
        self._emit_blank()
        self._emit("from pydantic import BaseModel, Field")
        self._emit("from runtime import NousRuntime, ToolResult, BudgetExceededError, init_runtime")
        self._emit_blank()
        self._emit("log = logging.getLogger('nous.runtime')")

    def _emit_law_constants(self) -> None:
        if not self.program.world:
            return
        self._emit("# ═══ World Laws ═══")
        self._emit_blank()
        world = self.program.world
        self._emit(f'WORLD_NAME = "{world.name}"')
        if world.heartbeat:
            seconds = self._duration_to_seconds(world.heartbeat)
            self._emit(f"HEARTBEAT_SECONDS = {seconds}")
        else:
            self._emit("HEARTBEAT_SECONDS = 300")

        budget = 1.0
        for law in world.laws:
            name = f"LAW_{law.name.upper()}"
            if isinstance(law.expr, LawCost):
                self._emit(f"{name} = {law.expr.amount}")
                budget = law.expr.amount
            elif isinstance(law.expr, LawDuration):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawBool):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawInt):
                self._emit(f"{name} = {law.expr.value}")
            elif isinstance(law.expr, LawConstitutional):
                self._emit(f"{name} = {law.expr.count}")

        self._emit(f"BUDGET_PER_CYCLE = {budget}")

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

    def _emit_channel_setup(self) -> None:
        self._emit("# ═══ Runtime + Channels ═══")
        self._emit_blank()
        self._emit("runtime: NousRuntime = None  # type: ignore[assignment]")

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

        self._emit("def __init__(self, rt: NousRuntime) -> None:")
        self._indent()
        self._emit(f'self.name = "{soul.name}"')
        self._emit("self._runtime = rt")
        if soul.mind:
            self._emit(f'self.model = "{soul.mind.model}"')
            self._emit(f'self.tier = "{soul.mind.tier.value}"')
        self._emit(f"self.senses = {soul.senses}")
        self._emit("self.cycle_count = 0")
        self._emit("self._alive = True")

        if soul.memory:
            for f in soul.memory.fields:
                default = self._value_to_python(f.default)
                self._emit(f"self.{f.name} = {default}")

        if soul.dna:
            for gene in soul.dna.genes:
                self._emit(f"self.dna_{gene.name} = {self._value_to_python(gene.value)}")

        self._dedent()
        self._emit_blank()

        self._emit_instinct(soul)
        self._emit_blank()
        self._emit_heal(soul)
        self._emit_blank()
        self._emit_run_loop(soul)

        self._dedent()

    def _emit_instinct(self, soul: SoulNode) -> None:
        self._emit("async def instinct(self) -> None:")
        self._indent()
        self._emit(f'"""Instinct cycle for {soul.name}"""')
        if soul.instinct and soul.instinct.statements:
            for stmt in soul.instinct.statements:
                self._emit_statement(stmt, soul.name)
        else:
            self._emit("pass")
        self._dedent()

    def _emit_statement(self, stmt: Any, soul_name: str) -> None:
        if isinstance(stmt, LetNode):
            self._emit_let(stmt, soul_name)
        elif isinstance(stmt, RememberNode):
            val = self._expr_to_python(stmt.value)
            if stmt.op == "+=":
                self._emit(f"self.{stmt.name} += {val}")
            else:
                self._emit(f"self.{stmt.name} = {val}")
        elif isinstance(stmt, SpeakNode):
            self._emit_speak(stmt, soul_name)
        elif isinstance(stmt, GuardNode):
            cond = self._expr_to_python(stmt.condition)
            self._emit(f"if not ({cond}):")
            self._indent()
            self._emit("return")
            self._dedent()
        elif isinstance(stmt, SenseCallNode):
            self._emit_sense_call(stmt, soul_name)
        elif isinstance(stmt, SleepNode):
            self._emit(f"await asyncio.sleep(HEARTBEAT_SECONDS * {stmt.cycles})")
        elif isinstance(stmt, IfNode):
            self._emit_if(stmt, soul_name)
        elif isinstance(stmt, ForNode):
            self._emit_for(stmt, soul_name)
        elif isinstance(stmt, dict):
            kind = stmt.get("kind", "")
            if kind in ("method_call", "func_call"):
                self._emit(self._expr_to_python(stmt))

    def _emit_let(self, stmt: LetNode, soul_name: str) -> None:
        value = stmt.value
        if isinstance(value, dict):
            kind = value.get("kind", "")
            if kind == "listen":
                channel = f"{value['soul']}_{value['type']}"
                self._emit(f'{stmt.name} = await self._runtime.channels.receive("{channel}")')
                return
            if kind == "sense_call":
                tool = value.get("tool", "unknown")
                args = value.get("args", {})
                args_str = self._kwargs_to_python(args)
                self._emit(f'{stmt.name} = await self._runtime.sense(self.name, "{tool}"{", " + args_str if args_str else ""})')
                return
        self._emit(f"{stmt.name} = {self._expr_to_python(value)}")

    def _emit_speak(self, stmt: SpeakNode, soul_name: str) -> None:
        channel = f"{soul_name}_{stmt.message_type}"
        args_str = self._kv_to_python(stmt.args)
        self._emit(f'await self._runtime.channels.send("{channel}", {stmt.message_type}({args_str}))')

    def _emit_sense_call(self, stmt: SenseCallNode, soul_name: str) -> None:
        args_str = self._kwargs_to_python(stmt.args)
        call = f'await self._runtime.sense(self.name, "{stmt.tool_name}"{", " + args_str if args_str else ""})'
        if stmt.bind_name:
            self._emit(f"{stmt.bind_name} = {call}")
        else:
            self._emit(call)

    def _emit_if(self, stmt: IfNode, soul_name: str) -> None:
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

    def _emit_for(self, stmt: ForNode, soul_name: str) -> None:
        iterable = self._expr_to_python(stmt.iterable)
        self._emit(f"for {stmt.var_name} in {iterable}:")
        self._indent()
        if stmt.body:
            for s in stmt.body:
                self._emit_statement(s, soul_name)
        else:
            self._emit("pass")
        self._dedent()

    def _emit_heal(self, soul: SoulNode) -> None:
        self._emit("async def heal(self, error: Exception) -> bool:")
        self._indent()
        self._emit(f'"""Error recovery for {soul.name}"""')
        self._emit("etype = type(error).__name__.lower()")
        if soul.heal and soul.heal.rules:
            for i, rule in enumerate(soul.heal.rules):
                kw = "if" if i == 0 else "elif"
                self._emit(f'{kw} etype == "{rule.error_type}" or "{rule.error_type}" in str(error).lower():')
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

    def _emit_run_loop(self, soul: SoulNode) -> None:
        self._emit("async def run(self) -> None:")
        self._indent()
        self._emit(f'"""Main loop for {soul.name}"""')
        self._emit("log.info(f'{self.name}: soul alive')")
        self._emit("while self._alive:")
        self._indent()
        self._emit("try:")
        self._indent()
        self._emit("await self.instinct()")
        self._emit("self.cycle_count += 1")
        self._emit("log.info(f'{self.name}: cycle {self.cycle_count} complete')")
        self._dedent()
        self._emit("except BudgetExceededError as e:")
        self._indent()
        self._emit("log.warning(f'{self.name}: {e}')")
        self._emit("await asyncio.sleep(HEARTBEAT_SECONDS)")
        self._dedent()
        self._emit("except Exception as e:")
        self._indent()
        self._emit("log.error(f'{self.name}: error in cycle {self.cycle_count}: {e}')")
        self._emit("recovered = await self.heal(e)")
        self._emit("if not recovered:")
        self._indent()
        self._emit("log.critical(f'{self.name}: unrecoverable error, stopping')")
        self._emit("self._alive = False")
        self._dedent()
        self._dedent()
        self._emit("await asyncio.sleep(HEARTBEAT_SECONDS)")
        self._dedent()
        self._dedent()

    def _emit_nervous_system(self) -> None:
        ns = self.program.nervous_system
        if not ns:
            return
        self._emit_blank()
        self._emit("# ═══ Nervous System ═══")
        self._emit_blank()
        self._emit("def build_topology() -> dict[str, list[str]]:")
        self._indent()
        self._emit('"""Build the execution DAG."""')
        self._emit("graph: dict[str, list[str]] = {}")
        for route in ns.routes:
            if isinstance(route, RouteNode):
                self._emit(f'graph.setdefault("{route.source}", []).append("{route.target}")')
            elif isinstance(route, FanInNode):
                for src in route.sources:
                    self._emit(f'graph.setdefault("{src}", []).append("{route.target}")')
            elif isinstance(route, FanOutNode):
                for tgt in route.targets:
                    self._emit(f'graph.setdefault("{route.source}", []).append("{tgt}")')
        self._emit("return graph")
        self._dedent()

    def _emit_world_runner(self) -> None:
        self._emit_blank()
        self._emit("# ═══ World Runner ═══")
        self._emit_blank()
        self._emit("async def run_world() -> None:")
        self._indent()
        world_name = self.program.world.name if self.program.world else "Unknown"
        self._emit(f'"""Boot and run world: {world_name}"""')
        self._emit("global runtime")
        self._emit(f"runtime = init_runtime(")
        self._indent()
        self._emit(f'world_name="{world_name}",')
        self._emit("heartbeat_seconds=HEARTBEAT_SECONDS,")
        self._emit("budget_per_cycle=BUDGET_PER_CYCLE,")
        self._dedent()
        self._emit(")")
        self._emit_blank()

        for soul in self.program.souls:
            self._emit(f'runtime.register_soul("{soul.name}", Soul_{soul.name}(runtime))')

        self._emit_blank()

        if self.program.nervous_system:
            self._emit("topology = build_topology()")
            self._emit("log.info(f'Nervous system: {topology}')")
            self._emit_blank()

        if self.program.perception:
            self._emit("perception_rules = [")
            self._indent()
            for rule in self.program.perception.rules:
                trigger = {
                    "kind": rule.trigger.kind,
                    "name": rule.trigger.name,
                    "args": rule.trigger.args,
                }
                action = {
                    "kind": rule.action.kind,
                    "target": rule.action.target,
                }
                self._emit(f'{{"trigger": {trigger}, "action": {action}}},')
            self._dedent()
            self._emit("]")
            self._emit("await runtime.run(perception_rules)")
        else:
            self._emit("await runtime.run()")

        self._dedent()

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
        self._emit("asyncio.run(run_world())")
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
                return "self.name"
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
                obj = expr.get("obj")
                attr_name = expr["attr"]
                if obj == "world" or (isinstance(obj, dict) and obj.get("kind") == "attr" and self._is_world_ref(obj)):
                    path = self._flatten_world_ref(expr)
                    return f'runtime.laws.get("{path}", "")'
                obj_str = self._expr_to_python(obj)
                return f"{obj_str}.{attr_name}"
            elif kind == "method_call":
                obj = self._expr_to_python(expr["obj"])
                method = expr.get("method", "")
                args = expr.get("args", {})
                if method == "where" and args:
                    first_arg = args.get("_pos_0", {})
                    if isinstance(first_arg, dict) and first_arg.get("kind") == "binop":
                        field = first_arg.get("left", "")
                        op = first_arg.get("op", ">")
                        val = self._expr_to_python(first_arg.get("right", 0))
                        if isinstance(field, str) and field.replace("_", "").isalnum():
                            return f'{obj}.filter("{field}", "{op}", {val})'
                args_str = self._args_to_python(args)
                return f"{obj}.{method}({args_str})"
            elif kind == "func_call":
                func = self._expr_to_python(expr["func"])
                args = self._args_to_python(expr.get("args", {}))
                return f"{func}({args})"
            elif kind == "world_ref":
                path = expr.get("path", "")
                return f'runtime.laws.get("{path}", "")'
            elif kind == "soul_field":
                return f'runtime.souls["{expr["soul"]}"].{expr["field"]}'
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
                args = expr.get("args", {})
                args_str = self._kwargs_to_python(args)
                return f'await self._runtime.sense(self.name, "{tool}"{", " + args_str if args_str else ""})'
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

    def _kwargs_to_python(self, args: Any) -> str:
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

    @staticmethod
    def _is_world_ref(expr: Any) -> bool:
        if isinstance(expr, str):
            return expr == "world"
        if isinstance(expr, dict) and expr.get("kind") == "attr":
            return NousCodeGen._is_world_ref(expr.get("obj"))
        return False

    @staticmethod
    def _flatten_world_ref(expr: Any) -> str:
        if isinstance(expr, str):
            return expr
        if isinstance(expr, dict) and expr.get("kind") == "attr":
            parent = NousCodeGen._flatten_world_ref(expr.get("obj"))
            parts = parent.split(".")
            parts = [p for p in parts if p != "world"]
            parts.append(expr["attr"])
            return ".".join(parts)
        return str(expr)


def generate_python(program: NousProgram) -> str:
    gen = NousCodeGen(program)
    return gen.generate()
