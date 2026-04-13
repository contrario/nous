"""
NOUS Debugger — Σκαραβαίος (Scarab)
=====================================
Step-through execution of .nous programs.
Breakpoints, memory inspection, channel tracing.
"""
from __future__ import annotations

import asyncio
import json
import readline
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, SoulNode, LetNode, RememberNode, SpeakNode,
    GuardNode, SenseCallNode, SleepNode, IfNode, ForNode,
)


@dataclass
class Breakpoint:
    soul_name: str
    statement_index: int
    enabled: bool = True
    hit_count: int = 0

    def __str__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"BP#{self.soul_name}:{self.statement_index} [{state}] hits={self.hit_count}"


@dataclass
class ChannelMessage:
    channel: str
    message_type: str
    data: dict[str, Any]
    timestamp: float
    sender: str


@dataclass
class SoulState:
    name: str
    memory: dict[str, Any] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    cycle: int = 0
    alive: bool = True
    current_stmt: int = 0


class DebugRuntime:
    """Simulated runtime for debugging."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.soul_states: dict[str, SoulState] = {}
        self.channels: dict[str, list[ChannelMessage]] = {}
        self.channel_log: list[ChannelMessage] = []
        self.breakpoints: list[Breakpoint] = []
        self.step_mode: bool = True
        self.current_soul: Optional[str] = None
        self.watch_vars: set[str] = set()

        for soul in program.souls:
            state = SoulState(name=soul.name)
            if soul.memory:
                for f in soul.memory.fields:
                    state.memory[f.name] = self._default_value(f.default)
            if soul.dna:
                for g in soul.dna.genes:
                    state.memory[f"dna_{g.name}"] = g.value
            self.soul_states[soul.name] = state

    def _default_value(self, val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, (int, float, bool, str)):
            return val
        if isinstance(val, list):
            return list(val)
        if isinstance(val, dict):
            return dict(val)
        return val

    def send_channel(self, channel: str, msg_type: str, data: dict[str, Any], sender: str) -> None:
        msg = ChannelMessage(
            channel=channel,
            message_type=msg_type,
            data=data,
            timestamp=time.time(),
            sender=sender,
        )
        if channel not in self.channels:
            self.channels[channel] = []
        self.channels[channel].append(msg)
        self.channel_log.append(msg)

    def receive_channel(self, channel: str) -> Optional[ChannelMessage]:
        msgs = self.channels.get(channel, [])
        if msgs:
            return msgs.pop(0)
        return None

    def has_breakpoint(self, soul_name: str, stmt_idx: int) -> Optional[Breakpoint]:
        for bp in self.breakpoints:
            if bp.soul_name == soul_name and bp.statement_index == stmt_idx and bp.enabled:
                return bp
        return None


class NousDebugger:
    """Interactive debugger for NOUS programs."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.runtime = DebugRuntime(program)
        self.running = True
        self.soul_order: list[str] = [s.name for s in program.souls]

    def start(self) -> None:
        world_name = self.program.world.name if self.program.world else "Unknown"
        print(f"\n═══ NOUS Debugger — {world_name} ═══")
        print(f"Souls: {', '.join(self.soul_order)}")
        print(f"Messages: {', '.join(m.name for m in self.program.messages)}")
        print(f"\nCommands: step(s), continue(c), break(b), memory(m),")
        print(f"          channels(ch), watch(w), locals(l), souls, quit(q)")
        print(f"          inject <channel> <json>  — inject message into channel")
        print()

        try:
            self._run_loop()
        except (EOFError, KeyboardInterrupt):
            print("\n\nDebugger terminated.")

    def _run_loop(self) -> None:
        while self.running:
            for soul_name in self.soul_order:
                if not self.running:
                    break
                soul = next((s for s in self.program.souls if s.name == soul_name), None)
                if soul is None or soul.instinct is None:
                    continue
                state = self.runtime.soul_states[soul_name]
                if not state.alive:
                    continue

                self.runtime.current_soul = soul_name
                state.cycle += 1
                state.locals.clear()
                state.current_stmt = 0

                print(f"\n{'─'*50}")
                print(f"▶ Soul: {soul_name} | Cycle: {state.cycle}")
                print(f"{'─'*50}")

                for i, stmt in enumerate(soul.instinct.statements):
                    if not self.running:
                        break
                    state.current_stmt = i
                    bp = self.runtime.has_breakpoint(soul_name, i)
                    if bp:
                        bp.hit_count += 1
                        print(f"\n⚑ Breakpoint hit: {bp}")

                    self._show_statement(stmt, i, soul_name)
                    self._simulate_statement(stmt, state, soul_name)
                    self._show_watches(state)

                    if self.runtime.step_mode or bp:
                        if not self._prompt():
                            return

            if not self.runtime.step_mode:
                print(f"\n═══ All souls completed one cycle ═══")
                if not self._prompt():
                    return

    def _show_statement(self, stmt: Any, idx: int, soul_name: str) -> None:
        prefix = f"  [{idx}]"
        if isinstance(stmt, LetNode):
            val_str = self._expr_summary(stmt.value)
            print(f"{prefix} let {stmt.name} = {val_str}")
        elif isinstance(stmt, RememberNode):
            val_str = self._expr_summary(stmt.value)
            print(f"{prefix} remember {stmt.name} {stmt.op} {val_str}")
        elif isinstance(stmt, SpeakNode):
            args_str = ", ".join(f"{k}: {self._expr_summary(v)}" for k, v in (stmt.args.items() if isinstance(stmt.args, dict) else []))
            print(f"{prefix} speak {stmt.message_type}({args_str})")
        elif isinstance(stmt, GuardNode):
            print(f"{prefix} guard {self._expr_summary(stmt.condition)}")
        elif isinstance(stmt, SenseCallNode):
            args_str = ", ".join(f"{k}: {self._expr_summary(v)}" for k, v in (stmt.args.items() if isinstance(stmt.args, dict) else []))
            print(f"{prefix} sense {stmt.tool_name}({args_str})")
        elif isinstance(stmt, SleepNode):
            print(f"{prefix} sleep {stmt.cycles} cycle")
        elif isinstance(stmt, IfNode):
            print(f"{prefix} if {self._expr_summary(stmt.condition)} {{ {len(stmt.then_body)} stmts }}")
        elif isinstance(stmt, ForNode):
            print(f"{prefix} for {stmt.var_name} in {self._expr_summary(stmt.iterable)} {{ {len(stmt.body)} stmts }}")
        else:
            print(f"{prefix} {type(stmt).__name__}: {stmt}")

    def _simulate_statement(self, stmt: Any, state: SoulState, soul_name: str) -> None:
        if isinstance(stmt, LetNode):
            if isinstance(stmt.value, dict):
                kind = stmt.value.get("kind", "")
                if kind == "listen":
                    channel = f"{stmt.value['soul']}_{stmt.value['type']}"
                    msg = self.runtime.receive_channel(channel)
                    if msg:
                        state.locals[stmt.name] = msg.data
                        print(f"       → {stmt.name} = {msg.data}")
                    else:
                        state.locals[stmt.name] = {"_pending": f"waiting on {channel}"}
                        print(f"       → {stmt.name} = <waiting on {channel}>")
                    return
                elif kind == "sense_call":
                    state.locals[stmt.name] = {"_simulated": True, "tool": stmt.value.get("tool", "")}
                    print(f"       → {stmt.name} = <sense {stmt.value.get('tool', '')} simulated>")
                    return
            state.locals[stmt.name] = self._eval_expr(stmt.value, state)
            print(f"       → {stmt.name} = {state.locals[stmt.name]}")

        elif isinstance(stmt, RememberNode):
            old = state.memory.get(stmt.name, None)
            val = self._eval_expr(stmt.value, state)
            if stmt.op == "+=":
                if isinstance(old, (int, float)) and isinstance(val, (int, float)):
                    state.memory[stmt.name] = old + val
                elif isinstance(old, list):
                    state.memory[stmt.name] = old + [val]
                else:
                    state.memory[stmt.name] = val
            else:
                state.memory[stmt.name] = val
            print(f"       → memory.{stmt.name}: {old} → {state.memory[stmt.name]}")

        elif isinstance(stmt, SpeakNode):
            channel = f"{soul_name}_{stmt.message_type}"
            data = {}
            if isinstance(stmt.args, dict):
                for k, v in stmt.args.items():
                    data[k] = self._eval_expr(v, state)
            self.runtime.send_channel(channel, stmt.message_type, data, soul_name)
            print(f"       → channel '{channel}': {data}")

        elif isinstance(stmt, GuardNode):
            result = self._eval_expr(stmt.condition, state)
            if not result:
                print(f"       → GUARD FAILED — skipping rest of instinct")
            else:
                print(f"       → guard passed")

    def _eval_expr(self, expr: Any, state: SoulState) -> Any:
        if expr is None:
            return None
        if isinstance(expr, (int, float, bool)):
            return expr
        if isinstance(expr, str):
            if expr == "self":
                return state.name
            if expr == "now()":
                return time.time()
            if expr in state.locals:
                return state.locals[expr]
            if expr in state.memory:
                return state.memory[expr]
            return expr
        if isinstance(expr, list):
            return [self._eval_expr(e, state) for e in expr]
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                left = self._eval_expr(expr.get("left"), state)
                right = self._eval_expr(expr.get("right"), state)
                return self._eval_binop(expr.get("op", ""), left, right)
            elif kind == "attr":
                obj = self._eval_expr(expr.get("obj"), state)
                attr = expr.get("attr", "")
                if isinstance(obj, dict):
                    return obj.get(attr, f"<{attr}>")
                return f"<{attr}>"
            elif kind == "not":
                return not self._eval_expr(expr.get("operand"), state)
            elif kind == "inline_if":
                cond = self._eval_expr(expr.get("condition"), state)
                if cond:
                    return self._eval_expr(expr.get("then"), state)
                return self._eval_expr(expr.get("else"), state)
            elif kind == "message_construct":
                return {k: self._eval_expr(v, state) for k, v in expr.get("args", {}).items()}
            elif kind == "world_ref":
                return f"<world.{expr.get('path', '')}>"
            return expr
        return expr

    def _eval_binop(self, op: str, left: Any, right: Any) -> Any:
        try:
            if op == "+":
                return left + right
            elif op == "-":
                return left - right
            elif op == "*":
                return left * right
            elif op == "/":
                return left / right if right != 0 else float("inf")
            elif op == "%":
                return left % right if right != 0 else 0
            elif op == "==":
                return left == right
            elif op == "!=":
                return left != right
            elif op == ">":
                return left > right
            elif op == "<":
                return left < right
            elif op == ">=":
                return left >= right
            elif op == "<=":
                return left <= right
            elif op == "&&":
                return bool(left) and bool(right)
            elif op == "||":
                return bool(left) or bool(right)
        except (TypeError, ValueError):
            return f"<{left} {op} {right}>"
        return f"<{op}?>"

    def _expr_summary(self, expr: Any) -> str:
        if expr is None:
            return "None"
        if isinstance(expr, (int, float, bool)):
            return str(expr)
        if isinstance(expr, str):
            if expr.replace("_", "").replace(".", "").isalnum():
                return expr
            return f'"{expr}"'
        if isinstance(expr, list):
            return f"[{', '.join(self._expr_summary(e) for e in expr)}]"
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                return f"{self._expr_summary(expr.get('left'))} {expr.get('op')} {self._expr_summary(expr.get('right'))}"
            elif kind == "attr":
                return f"{self._expr_summary(expr.get('obj'))}.{expr.get('attr')}"
            elif kind == "method_call":
                return f"{self._expr_summary(expr.get('obj'))}.{expr.get('method')}(...)"
            elif kind == "func_call":
                return f"{self._expr_summary(expr.get('func'))}(...)"
            elif kind == "listen":
                return f"listen {expr.get('soul')}::{expr.get('type')}"
            elif kind == "sense_call":
                return f"sense {expr.get('tool')}(...)"
            elif kind == "message_construct":
                return f"{expr.get('type')}(...)"
            elif kind == "world_ref":
                return f"world.{expr.get('path')}"
            elif kind == "inline_if":
                return f"if ... {{ ... }} else {{ ... }}"
            elif kind == "not":
                return f"!{self._expr_summary(expr.get('operand'))}"
            elif kind == "soul_field":
                return f"{expr.get('soul')}::{expr.get('field')}"
            return str(expr)
        return str(expr)

    def _show_watches(self, state: SoulState) -> None:
        if not self.watch_vars:
            return
        parts = []
        for var in sorted(self.watch_vars):
            if var in state.locals:
                parts.append(f"{var}={state.locals[var]}")
            elif var in state.memory:
                parts.append(f"mem.{var}={state.memory[var]}")
        if parts:
            print(f"       ⊳ watch: {', '.join(parts)}")

    def _prompt(self) -> bool:
        while True:
            try:
                cmd = input("\nnous-dbg> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return False

            if not cmd or cmd in ("s", "step"):
                return True

            elif cmd in ("c", "continue"):
                self.runtime.step_mode = False
                return True

            elif cmd in ("q", "quit", "exit"):
                self.running = False
                return False

            elif cmd.startswith("b ") or cmd.startswith("break "):
                self._cmd_breakpoint(cmd.split(None, 1)[1] if " " in cmd else "")

            elif cmd in ("m", "memory", "mem"):
                self._cmd_memory()

            elif cmd in ("l", "locals"):
                self._cmd_locals()

            elif cmd in ("ch", "channels"):
                self._cmd_channels()

            elif cmd.startswith("w ") or cmd.startswith("watch "):
                var = cmd.split(None, 1)[1].strip()
                self.watch_vars.add(var)
                print(f"Watching: {var}")

            elif cmd == "souls":
                self._cmd_souls()

            elif cmd.startswith("inject "):
                self._cmd_inject(cmd[7:].strip())

            elif cmd in ("bl", "breakpoints"):
                for bp in self.runtime.breakpoints:
                    print(f"  {bp}")

            elif cmd == "step-mode":
                self.runtime.step_mode = True
                print("Step mode enabled")

            elif cmd in ("h", "help"):
                print("  s/step      — execute next statement")
                print("  c/continue  — run until breakpoint")
                print("  b <soul>:<n> — set breakpoint")
                print("  m/memory    — show current soul memory")
                print("  l/locals    — show local variables")
                print("  ch/channels — show channel state")
                print("  w <var>     — watch variable")
                print("  souls       — show all soul states")
                print("  inject <ch> <json> — inject message")
                print("  bl          — list breakpoints")
                print("  q/quit      — exit debugger")

            else:
                print(f"Unknown command: {cmd}")

    def _cmd_breakpoint(self, arg: str) -> None:
        if ":" not in arg:
            print("Usage: break <soul>:<statement_index>")
            return
        parts = arg.split(":", 1)
        soul_name = parts[0].strip()
        try:
            idx = int(parts[1].strip())
        except ValueError:
            print("Statement index must be a number")
            return
        if soul_name not in self.runtime.soul_states:
            print(f"Unknown soul: {soul_name}")
            return
        bp = Breakpoint(soul_name=soul_name, statement_index=idx)
        self.runtime.breakpoints.append(bp)
        print(f"Breakpoint set: {bp}")

    def _cmd_memory(self) -> None:
        soul = self.runtime.current_soul
        if soul and soul in self.runtime.soul_states:
            state = self.runtime.soul_states[soul]
            print(f"  Memory for {soul}:")
            for k, v in sorted(state.memory.items()):
                print(f"    {k} = {v}")
        else:
            for name, state in self.runtime.soul_states.items():
                print(f"  {name}:")
                for k, v in sorted(state.memory.items()):
                    print(f"    {k} = {v}")

    def _cmd_locals(self) -> None:
        soul = self.runtime.current_soul
        if soul and soul in self.runtime.soul_states:
            state = self.runtime.soul_states[soul]
            print(f"  Locals for {soul}:")
            if not state.locals:
                print("    (empty)")
            for k, v in sorted(state.locals.items()):
                print(f"    {k} = {v}")

    def _cmd_channels(self) -> None:
        if not self.runtime.channel_log:
            print("  No messages sent yet")
            return
        print(f"  Channel log ({len(self.runtime.channel_log)} messages):")
        for msg in self.runtime.channel_log[-10:]:
            print(f"    [{msg.sender}] → {msg.channel}: {msg.message_type}({msg.data})")
        pending = {ch: len(msgs) for ch, msgs in self.runtime.channels.items() if msgs}
        if pending:
            print(f"  Pending: {pending}")

    def _cmd_souls(self) -> None:
        for name, state in self.runtime.soul_states.items():
            status = "alive" if state.alive else "dead"
            print(f"  {name}: cycle={state.cycle} status={status} memory_fields={len(state.memory)}")

    def _cmd_inject(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            print("Usage: inject <channel> <json>")
            return
        channel = parts[0]
        try:
            data = json.loads(parts[1])
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return
        msg_type = channel.split("_", 1)[1] if "_" in channel else "Unknown"
        self.runtime.send_channel(channel, msg_type, data, "debugger")
        print(f"Injected into {channel}: {data}")


def debug_program(program: NousProgram) -> None:
    debugger = NousDebugger(program)
    debugger.start()


def debug_file(path: str | Path) -> None:
    from parser import parse_nous_file
    from validator import validate_program

    source = Path(path)
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return

    program = parse_nous_file(source)
    result = validate_program(program)
    if not result.ok:
        print("Validation FAILED:")
        for e in result.errors:
            print(f"  {e}")
        return

    debug_program(program)
