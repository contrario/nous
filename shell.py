"""
NOUS Interactive Shell — Κέλυφος (Kelyfos) v2
================================================
Tab completion, colorized output, memory inspection, direct tool invocation.
"""
from __future__ import annotations

import json
import readline
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Optional

from parser import parse_nous_file, parse_nous
from validator import validate_program
from codegen import generate_python
from ast_nodes import (
    NousProgram, SoulNode, MessageNode, WorldNode,
    LetNode, RememberNode, SpeakNode, SenseCallNode,
    IfNode, ForNode, GuardNode, SleepNode,
    RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode,
)


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    @staticmethod
    def disable() -> None:
        for attr in dir(Colors):
            if attr.isupper() and not attr.startswith("_"):
                setattr(Colors, attr, "")


if not sys.stdout.isatty():
    Colors.disable()

C = Colors


def _c(color: str, text: str) -> str:
    return f"{color}{text}{C.RESET}"


COMMANDS = [
    "souls", "laws", "messages", "dna", "routes", "ast", "tools",
    "memory", "sense", "run", "compile", "eval", "reload", "info",
    "history", "help", "quit", "exit",
]

HELP_TEXT = {
    "souls": "List all souls with mind, senses, memory summary",
    "laws": "Show world laws",
    "messages": "Show message types and fields",
    "dna": "Show DNA genes and ranges for all souls",
    "routes": "Show nervous system routing",
    "ast": "Display Living AST (use 'ast json' for JSON)",
    "tools": "List all tools/senses across souls",
    "memory": "Inspect soul memory ('memory' for all, 'memory SoulName' for one)",
    "sense": "Invoke a tool: sense tool_name(arg1: val1, arg2: val2)",
    "run": "Execute the compiled world",
    "compile": "Generate Python from current program",
    "eval": "Evaluate a NOUS expression",
    "reload": "Re-parse the source file",
    "info": "Show program summary",
    "history": "Show command history",
    "help": "Show this help",
    "quit": "Exit the shell (also: exit, Ctrl+D)",
}


class NousCompleter:
    def __init__(self, shell: NousShell) -> None:
        self.shell = shell
        self._matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            line = readline.get_line_buffer().lstrip()
            if " " not in line:
                self._matches = [c + " " for c in COMMANDS if c.startswith(text)]
            else:
                parts = line.split(None, 1)
                cmd = parts[0]
                if cmd == "memory":
                    names = self._soul_names()
                    self._matches = [n for n in names if n.startswith(text)]
                elif cmd == "sense":
                    tools = self._tool_names()
                    self._matches = [t + "(" for t in tools if t.startswith(text)]
                elif cmd == "eval":
                    names = self._soul_names() + self._message_names()
                    self._matches = [n for n in names if n.startswith(text)]
                else:
                    self._matches = []
        return self._matches[state] if state < len(self._matches) else None

    def _soul_names(self) -> list[str]:
        p = self.shell.program
        return [s.name for s in p.souls] if p else []

    def _message_names(self) -> list[str]:
        p = self.shell.program
        return [m.name for m in p.messages] if p else []

    def _tool_names(self) -> list[str]:
        p = self.shell.program
        if not p:
            return []
        tools: set[str] = set()
        for soul in p.souls:
            tools.update(soul.senses)
        return sorted(tools)


class NousShell:
    def __init__(self, source_path: str | None = None) -> None:
        self.source_path = source_path
        self.program: NousProgram | None = None
        self.source: str = ""
        self._history_file = os.path.expanduser("~/.nous_history")

    def start(self) -> None:
        self._setup_readline()
        self._print_banner()

        if self.source_path:
            self._load(self.source_path)

        self._loop()

    def _setup_readline(self) -> None:
        completer = NousCompleter(self)
        readline.set_completer(completer.complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n(,:")
        try:
            readline.read_history_file(self._history_file)
        except FileNotFoundError:
            pass

    def _save_history(self) -> None:
        try:
            readline.set_history_length(1000)
            readline.write_history_file(self._history_file)
        except Exception:
            pass

    def _print_banner(self) -> None:
        print(_c(C.CYAN, """
  ╔═══════════════════════════════════════╗
  ║   ΝΟΥΣ Shell v2.0 — The Living REPL  ║
  ╚═══════════════════════════════════════╝"""))
        print(f"  {_c(C.DIM, 'Type')} {_c(C.YELLOW, 'help')} {_c(C.DIM, 'for commands, tab for completion')}")
        print()

    def _load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            print(_c(C.RED, f"  File not found: {path}"))
            return
        try:
            self.source = p.read_text(encoding="utf-8")
            self.program = parse_nous_file(p)
            world_name = self.program.world.name if self.program.world else "?"
            soul_count = len(self.program.souls)
            msg_count = len(self.program.messages)
            print(f"  {_c(C.GREEN, '✓')} Loaded {_c(C.BOLD, p.name)}: "
                  f"world={_c(C.CYAN, world_name)} "
                  f"souls={_c(C.YELLOW, str(soul_count))} "
                  f"messages={_c(C.YELLOW, str(msg_count))}")
            result = validate_program(self.program)
            if not result.ok:
                for e in result.errors:
                    print(f"  {_c(C.RED, '✗')} {e}")
            for w in result.warnings:
                print(f"  {_c(C.YELLOW, '⚠')} {w}")
            print()
        except Exception as e:
            print(_c(C.RED, f"  Parse error: {e}"))

    def _loop(self) -> None:
        while True:
            try:
                prompt = _c(C.BLUE, "nous") + _c(C.DIM, "> ")
                line = input(prompt).strip()
                if not line:
                    continue
                self._dispatch(line)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
        self._save_history()

    def _dispatch(self, line: str) -> None:
        parts = line.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "souls": self._cmd_souls,
            "laws": self._cmd_laws,
            "messages": self._cmd_messages,
            "dna": self._cmd_dna,
            "routes": self._cmd_routes,
            "ast": self._cmd_ast,
            "tools": self._cmd_tools,
            "memory": self._cmd_memory,
            "sense": self._cmd_sense,
            "run": self._cmd_run,
            "compile": self._cmd_compile,
            "eval": self._cmd_eval,
            "reload": self._cmd_reload,
            "info": self._cmd_info,
            "history": self._cmd_history,
            "help": self._cmd_help,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            handler(arg)
        else:
            print(_c(C.RED, f"  Unknown command: {cmd}") + f" — type {_c(C.YELLOW, 'help')} for commands")

    def _require_program(self) -> bool:
        if self.program is None:
            print(_c(C.RED, "  No program loaded. Use: nous shell file.nous"))
            return False
        return True

    def _cmd_souls(self, _arg: str) -> None:
        if not self._require_program():
            return
        print(f"\n  {_c(C.BOLD, 'Souls')} ({len(self.program.souls)})")
        print(f"  {'─' * 50}")
        for soul in self.program.souls:
            mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
            senses = ", ".join(soul.senses) if soul.senses else "none"
            mem = len(soul.memory.fields) if soul.memory else 0
            genes = len(soul.dna.genes) if soul.dna else 0
            heals = len(soul.heal.rules) if soul.heal else 0
            print(f"  {_c(C.CYAN, soul.name)}")
            print(f"    mind:    {_c(C.GREEN, mind)}")
            print(f"    senses:  [{_c(C.YELLOW, senses)}]")
            print(f"    memory:  {mem} fields | dna: {genes} genes | heal: {heals} rules")
        print()

    def _cmd_laws(self, _arg: str) -> None:
        if not self._require_program():
            return
        w = self.program.world
        if not w or not w.laws:
            print(_c(C.DIM, "  No laws defined"))
            return
        print(f"\n  {_c(C.BOLD, 'Laws')} ({len(w.laws)})")
        print(f"  {'─' * 50}")
        for law in w.laws:
            expr = law.expr
            kind = expr.kind
            if kind == "cost":
                val = f"${expr.amount} {expr.currency} per {expr.per}"
            elif kind == "currency":
                val = f"${expr.amount} {expr.currency}"
            elif kind == "duration":
                val = f"{expr.value}{expr.unit}"
            elif kind == "bool":
                val = str(expr.value)
            elif kind == "int":
                val = str(expr.value)
            elif kind == "constitutional":
                val = f"constitutional({expr.count})"
            else:
                val = str(expr)
            print(f"  {_c(C.MAGENTA, law.name)} = {_c(C.WHITE, val)}")
        print()

    def _cmd_messages(self, _arg: str) -> None:
        if not self._require_program():
            return
        print(f"\n  {_c(C.BOLD, 'Messages')} ({len(self.program.messages)})")
        print(f"  {'─' * 50}")
        for msg in self.program.messages:
            fields = ", ".join(f"{_c(C.YELLOW, f.name)}: {f.type_expr}" for f in msg.fields)
            print(f"  {_c(C.CYAN, msg.name)}({fields})")
        print()

    def _cmd_dna(self, _arg: str) -> None:
        if not self._require_program():
            return
        found = False
        for soul in self.program.souls:
            if soul.dna and soul.dna.genes:
                found = True
                print(f"\n  {_c(C.BOLD, soul.name)} DNA")
                print(f"  {'─' * 40}")
                for gene in soul.dna.genes:
                    rng = f"[{', '.join(str(v) for v in gene.range)}]"
                    print(f"  {_c(C.YELLOW, gene.name)}: {_c(C.WHITE, str(gene.value))} ~ {_c(C.DIM, rng)}")
        if not found:
            print(_c(C.DIM, "  No DNA blocks found"))
        print()

    def _cmd_routes(self, _arg: str) -> None:
        if not self._require_program():
            return
        ns = self.program.nervous_system
        if not ns:
            print(_c(C.DIM, "  No nervous system defined"))
            return
        print(f"\n  {_c(C.BOLD, 'Nervous System')} ({len(ns.routes)} routes)")
        print(f"  {'─' * 40}")
        for route in ns.routes:
            if isinstance(route, RouteNode):
                print(f"  {_c(C.CYAN, route.source)} {_c(C.DIM, '→')} {_c(C.GREEN, route.target)}")
            elif isinstance(route, MatchRouteNode):
                print(f"  {_c(C.CYAN, route.source)} {_c(C.DIM, '→ match')}")
                for arm in route.arms:
                    tgt = "silence" if arm.is_silence else arm.target
                    print(f"    {arm.condition} => {_c(C.GREEN, tgt)}")
            elif isinstance(route, FanInNode):
                srcs = ", ".join(route.sources)
                print(f"  [{_c(C.CYAN, srcs)}] {_c(C.DIM, '→')} {_c(C.GREEN, route.target)}")
            elif isinstance(route, FanOutNode):
                tgts = ", ".join(route.targets)
                print(f"  {_c(C.CYAN, route.source)} {_c(C.DIM, '→')} [{_c(C.GREEN, tgts)}]")
            elif isinstance(route, FeedbackNode):
                print(f"  {_c(C.CYAN, route.source_soul)}.{route.source_field} {_c(C.DIM, '↺')} {_c(C.GREEN, route.target_soul)}.{route.target_field}")
        print()

    def _cmd_ast(self, arg: str) -> None:
        if not self._require_program():
            return
        data = self.program.model_dump(exclude_none=True)
        if arg.strip() == "json":
            print(json.dumps(data, indent=2, default=str))
        else:
            self._print_tree(data)

    def _print_tree(self, data: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    print(f"{prefix}{_c(C.YELLOW, k)}:")
                    self._print_tree(v, indent + 1)
                else:
                    print(f"{prefix}{_c(C.YELLOW, k)}: {_c(C.WHITE, str(v))}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    name = item.get("name", item.get("kind", f"[{i}]"))
                    print(f"{prefix}{_c(C.DIM, '•')} {_c(C.CYAN, str(name))}")
                    self._print_tree(item, indent + 1)
                else:
                    print(f"{prefix}{_c(C.DIM, '•')} {item}")

    def _cmd_tools(self, _arg: str) -> None:
        if not self._require_program():
            return
        all_tools: dict[str, list[str]] = {}
        for soul in self.program.souls:
            for tool in soul.senses:
                all_tools.setdefault(tool, []).append(soul.name)
        print(f"\n  {_c(C.BOLD, 'Tools')} ({len(all_tools)})")
        print(f"  {'─' * 40}")
        for tool, souls in sorted(all_tools.items()):
            soul_list = ", ".join(_c(C.CYAN, s) for s in souls)
            print(f"  {_c(C.YELLOW, tool)} ← {soul_list}")
        print()

    def _cmd_memory(self, arg: str) -> None:
        if not self._require_program():
            return
        target = arg.strip() if arg.strip() else None
        found = False
        for soul in self.program.souls:
            if target and soul.name != target:
                continue
            if soul.memory and soul.memory.fields:
                found = True
                print(f"\n  {_c(C.BOLD, soul.name)} Memory")
                print(f"  {'─' * 40}")
                for field in soul.memory.fields:
                    default = str(field.default) if field.default is not None else "None"
                    print(f"  {_c(C.YELLOW, field.name)}: {_c(C.DIM, field.type_expr)} = {_c(C.WHITE, default)}")
        if not found:
            if target:
                print(_c(C.DIM, f"  No memory found for soul: {target}"))
            else:
                print(_c(C.DIM, "  No memory blocks found"))
        print()

    def _cmd_sense(self, arg: str) -> None:
        if not arg.strip():
            print(f"  Usage: {_c(C.YELLOW, 'sense tool_name(arg1: val1, arg2: val2)')}")
            return
        print(_c(C.DIM, "  Note: Direct tool invocation requires runtime."))
        print(_c(C.DIM, "  Use 'nous run file.nous' to execute with tools."))
        print()
        # Parse the sense call for display
        import re
        m = re.match(r'(\w+)\((.*)\)', arg.strip())
        if m:
            tool_name = m.group(1)
            args_str = m.group(2)
            print(f"  Tool: {_c(C.CYAN, tool_name)}")
            if args_str:
                for part in args_str.split(","):
                    part = part.strip()
                    if ":" in part:
                        k, v = part.split(":", 1)
                        print(f"    {_c(C.YELLOW, k.strip())}: {v.strip()}")
            if self.program:
                all_tools: set[str] = set()
                for soul in self.program.souls:
                    all_tools.update(soul.senses)
                if tool_name not in all_tools:
                    print(f"\n  {_c(C.RED, '⚠')} Tool '{tool_name}' not found in any soul's senses")
        else:
            print(_c(C.RED, "  Cannot parse sense call. Format: tool_name(arg: val)"))
        print()

    def _cmd_run(self, _arg: str) -> None:
        if not self._require_program():
            return
        code = generate_python(self.program)
        tmp = Path("/tmp/nous_repl_run.py")
        tmp.write_text(code, encoding="utf-8")
        world_name = self.program.world.name if self.program.world else "?"
        print(f"  {_c(C.GREEN, '▶')} Running {_c(C.CYAN, world_name)}...\n")
        import subprocess
        try:
            subprocess.run([sys.executable, str(tmp)])
        except KeyboardInterrupt:
            print(f"\n  {_c(C.YELLOW, '■')} Stopped")
        finally:
            tmp.unlink(missing_ok=True)

    def _cmd_compile(self, _arg: str) -> None:
        if not self._require_program():
            return
        code = generate_python(self.program)
        lines = code.splitlines()
        print(f"\n  {_c(C.GREEN, '✓')} Generated {_c(C.WHITE, str(len(lines)))} lines of Python\n")
        if self.source_path:
            out = Path(self.source_path).with_suffix(".py")
            out.write_text(code, encoding="utf-8")
            print(f"  Saved to: {_c(C.CYAN, str(out))}")
        else:
            for i, line in enumerate(lines[:20], 1):
                print(f"  {_c(C.DIM, f'{i:3d}')} {line}")
            if len(lines) > 20:
                print(f"  {_c(C.DIM, f'... ({len(lines) - 20} more lines)')}")
        print()

    def _cmd_eval(self, arg: str) -> None:
        if not arg.strip():
            print(f"  Usage: {_c(C.YELLOW, 'eval <expression>')}")
            return
        expr = arg.strip()
        try:
            src = f'world _Eval {{ }} soul _E {{ mind: x @ Tier1 senses: [x] instinct {{ let _result = {expr} }} heal {{ on e => retry }} }}'
            prog = parse_nous(src)
            print(f"  {_c(C.GREEN, '✓')} Valid expression")
            if prog.souls and prog.souls[0].instinct:
                for stmt in prog.souls[0].instinct.statements:
                    if isinstance(stmt, LetNode):
                        print(f"  AST: {_c(C.WHITE, str(stmt.value))}")
        except Exception as e:
            print(f"  {_c(C.RED, '✗')} {e}")
        print()

    def _cmd_reload(self, _arg: str) -> None:
        if self.source_path:
            self._load(self.source_path)
        else:
            print(_c(C.RED, "  No source file to reload"))

    def _cmd_info(self, _arg: str) -> None:
        if not self._require_program():
            return
        p = self.program
        w = p.world
        print(f"\n  {_c(C.BOLD, '═══ Program Info ═══')}")
        if self.source_path:
            print(f"  File:       {_c(C.CYAN, self.source_path)}")
        print(f"  World:      {_c(C.CYAN, w.name if w else 'None')}")
        print(f"  Heartbeat:  {w.heartbeat if w else 'N/A'}")
        print(f"  Laws:       {len(w.laws) if w else 0}")
        print(f"  Souls:      {len(p.souls)}")
        print(f"  Messages:   {len(p.messages)}")
        ns = p.nervous_system
        print(f"  Routes:     {len(ns.routes) if ns else 0}")
        if p.topology:
            print(f"  Topology:   {len(p.topology.servers)} servers")
        if p.evolution:
            print(f"  Evolution:  {len(p.evolution.mutations)} mutation targets")
        result = validate_program(p)
        status = _c(C.GREEN, "VALID") if result.ok else _c(C.RED, f"INVALID ({len(result.errors)} errors)")
        print(f"  Status:     {status}")
        print()

    def _cmd_history(self, _arg: str) -> None:
        length = readline.get_current_history_length()
        start = max(1, length - 20)
        print(f"\n  {_c(C.BOLD, 'History')} (last {min(20, length)} commands)")
        print(f"  {'─' * 40}")
        for i in range(start, length + 1):
            item = readline.get_history_item(i)
            if item:
                print(f"  {_c(C.DIM, f'{i:3d}')} {item}")
        print()

    def _cmd_help(self, _arg: str) -> None:
        print(f"\n  {_c(C.BOLD, 'NOUS Shell Commands')}")
        print(f"  {'─' * 50}")
        for cmd, desc in HELP_TEXT.items():
            print(f"  {_c(C.YELLOW, f'{cmd:<12}')} {desc}")
        print()

    def _cmd_quit(self, _arg: str) -> None:
        self._save_history()
        print(_c(C.DIM, "  Αντίο."))
        sys.exit(0)


def run_shell(source_path: str | None = None) -> None:
    shell = NousShell(source_path)
    shell.start()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run_shell(path)
