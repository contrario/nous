"""
NOUS REPL v3 — Ψυχή Ζωντανή (Living Soul)
=============================================
Interactive shell for NOUS programs.
Multi-line input, history, hot-reload, type checking, channel inspector.
"""
from __future__ import annotations

import atexit
import json
import os
import readline
import sys
import time
from pathlib import Path
from typing import Any, Optional

HISTORY_FILE = Path.home() / ".nous" / "repl_history"
MAX_HISTORY = 1000

BANNER = r"""
  _   _  ___  _   _ ____
 | \ | |/ _ \| | | / ___|
 |  \| | | | | | | \___ \    REPL v3
 | |\  | |_| | |_| |___) |   The Living Language
 |_| \_|\___/ \___/|____/

 Type :help for commands, :quit to exit
"""


class ReplState:
    """Tracks loaded program state for the REPL."""

    def __init__(self) -> None:
        self.program: Any = None
        self.source_path: Optional[Path] = None
        self.source_mtime: float = 0.0
        self.soul_names: list[str] = []
        self.message_names: list[str] = []
        self.memory_state: dict[str, dict[str, Any]] = {}
        self.channels: dict[str, list[dict[str, Any]]] = {}
        self.channel_log: list[dict[str, Any]] = []
        self.variables: dict[str, Any] = {}
        self.last_result: Any = None

    def load_file(self, path: Path) -> tuple[bool, str]:
        if not path.exists():
            return False, f"File not found: {path}"
        try:
            from parser import parse_nous_file
            self.program = parse_nous_file(path)
            self.source_path = path
            self.source_mtime = path.stat().st_mtime
            self._extract_info()
            return True, f"Loaded: {path.name} | {len(self.soul_names)} souls, {len(self.message_names)} messages"
        except Exception as e:
            return False, f"Parse error: {e}"

    def check_reload(self) -> Optional[str]:
        if self.source_path and self.source_path.exists():
            mtime = self.source_path.stat().st_mtime
            if mtime > self.source_mtime:
                ok, msg = self.load_file(self.source_path)
                if ok:
                    return f"♻ Hot-reloaded: {msg}"
                return f"♻ Reload failed: {msg}"
        return None

    def _extract_info(self) -> None:
        if self.program is None:
            return
        self.soul_names = [s.name for s in self.program.souls]
        self.message_names = [m.name for m in self.program.messages]
        self.memory_state.clear()
        for soul in self.program.souls:
            mem: dict[str, Any] = {}
            if soul.memory:
                for f in soul.memory.fields:
                    mem[f.name] = f.default
            if soul.dna:
                for g in soul.dna.genes:
                    mem[f"dna_{g.name}"] = g.value
            self.memory_state[soul.name] = mem


class NousRepl:
    """Interactive REPL for NOUS."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self.state = ReplState()
        self.running = True
        self.multiline_buffer: list[str] = []
        self.brace_depth = 0
        self.mode = "normal"
        self._setup_history()
        self._setup_completer()

        if file_path:
            path = Path(file_path)
            ok, msg = self.state.load_file(path)
            print(f"  {msg}")

    def _setup_history(self) -> None:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if HISTORY_FILE.exists():
            try:
                readline.read_history_file(str(HISTORY_FILE))
            except Exception:
                pass
        readline.set_history_length(MAX_HISTORY)
        atexit.register(self._save_history)

    def _save_history(self) -> None:
        try:
            readline.write_history_file(str(HISTORY_FILE))
        except Exception:
            pass

    def _setup_completer(self) -> None:
        readline.set_completer(self._complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n;:{}")

    def _complete(self, text: str, idx: int) -> Optional[str]:
        if idx == 0:
            self._completions = []
            commands = [
                ":help", ":quit", ":load", ":reload", ":souls", ":messages",
                ":memory", ":channels", ":validate", ":typecheck", ":compile",
                ":ast", ":info", ":laws", ":routes", ":watch", ":inject",
                ":clear", ":history", ":mode",
            ]
            keywords = [
                "world", "soul", "message", "nervous_system", "let", "remember",
                "speak", "listen", "sense", "guard", "if", "else", "for", "in",
                "instinct", "memory", "mind", "senses", "dna", "heal", "law",
            ]
            all_options = commands + keywords + self.state.soul_names + self.state.message_names
            self._completions = [w for w in all_options if w.startswith(text)]
        if idx < len(self._completions):
            return self._completions[idx]
        return None

    def run(self) -> None:
        print(BANNER)
        if self.state.program:
            world = self.state.program.world
            if world:
                print(f"  World: {world.name}")
        print()

        while self.running:
            try:
                reload_msg = self.state.check_reload()
                if reload_msg:
                    print(reload_msg)

                if self.multiline_buffer:
                    prompt = "... "
                else:
                    prompt = "nous> " if self.mode == "normal" else f"nous({self.mode})> "

                line = input(prompt)
                self._process_line(line)

            except EOFError:
                print()
                self.running = False
            except KeyboardInterrupt:
                print()
                self.multiline_buffer.clear()
                self.brace_depth = 0

        print("Goodbye.")

    def _process_line(self, line: str) -> None:
        stripped = line.strip()

        if not self.multiline_buffer and stripped.startswith(":"):
            self._handle_command(stripped)
            return

        self.brace_depth += line.count("{") - line.count("}")
        self.multiline_buffer.append(line)

        if self.brace_depth <= 0:
            full_input = "\n".join(self.multiline_buffer)
            self.multiline_buffer.clear()
            self.brace_depth = 0
            if full_input.strip():
                self._eval_input(full_input.strip())

    def _handle_command(self, cmd: str) -> None:
        parts = cmd.split(None, 1)
        command = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if command in (":quit", ":q", ":exit"):
            self.running = False

        elif command in (":help", ":h"):
            self._cmd_help()

        elif command in (":load", ":l"):
            if not arg:
                print("Usage: :load <file.nous>")
                return
            ok, msg = self.state.load_file(Path(arg))
            print(msg)

        elif command in (":reload", ":r"):
            if self.state.source_path:
                ok, msg = self.state.load_file(self.state.source_path)
                print(msg)
            else:
                print("No file loaded")

        elif command == ":souls":
            self._cmd_souls()

        elif command == ":messages":
            self._cmd_messages()

        elif command in (":memory", ":mem"):
            self._cmd_memory(arg)

        elif command in (":channels", ":ch"):
            self._cmd_channels()

        elif command == ":validate":
            self._cmd_validate()

        elif command in (":typecheck", ":tc"):
            self._cmd_typecheck()

        elif command == ":compile":
            self._cmd_compile(arg)

        elif command == ":ast":
            self._cmd_ast(arg)

        elif command == ":info":
            self._cmd_info()

        elif command == ":laws":
            self._cmd_laws()

        elif command == ":routes":
            self._cmd_routes()

        elif command == ":watch":
            self._cmd_watch(arg)

        elif command == ":inject":
            self._cmd_inject(arg)

        elif command == ":clear":
            os.system("clear" if os.name != "nt" else "cls")

        elif command == ":history":
            self._cmd_history()

        elif command == ":mode":
            self._cmd_mode(arg)

        else:
            print(f"Unknown command: {command}. Type :help")

    def _eval_input(self, text: str) -> None:
        if text.startswith("world ") or text.startswith("soul ") or text.startswith("message "):
            self._eval_declaration(text)
        elif text.startswith("let "):
            self._eval_let(text)
        elif text.startswith("speak "):
            self._eval_speak(text)
        else:
            self._eval_expression(text)

    def _eval_declaration(self, text: str) -> None:
        try:
            from parser import parse_nous
            wrapped = text
            if text.startswith("soul ") or text.startswith("message "):
                if self.state.program and self.state.program.world:
                    world_name = self.state.program.world.name
                    wrapped = f'world {world_name} {{ law _repl = true }}\n{text}'
                else:
                    wrapped = f'world _Repl {{ law _repl = true }}\n{text}'

            prog = parse_nous(wrapped)
            print("  ✓ Parsed OK")

            from validator import validate_program
            vr = validate_program(prog)
            if not vr.ok:
                for e in vr.errors:
                    print(f"  ✗ {e}")
            else:
                print("  ✓ Valid")

            from typechecker import typecheck_program
            tc = typecheck_program(prog)
            for e in tc.errors:
                print(f"  ⚠ {e}")
            for w in tc.warnings:
                print(f"  ⚠ {w}")
            if tc.ok:
                print("  ✓ Type check clean")

        except Exception as e:
            print(f"  ✗ {e}")

    def _eval_let(self, text: str) -> None:
        parts = text[4:].split("=", 1)
        if len(parts) != 2:
            print("  ✗ Invalid let statement")
            return
        name = parts[0].strip()
        val_str = parts[1].strip()
        try:
            val = eval(val_str, {"__builtins__": {}}, self.state.variables)
            self.state.variables[name] = val
            self.state.last_result = val
            print(f"  {name} = {val}")
        except Exception:
            self.state.variables[name] = val_str
            self.state.last_result = val_str
            print(f"  {name} = {val_str}")

    def _eval_speak(self, text: str) -> None:
        parts = text[6:].strip()
        msg_name = parts.split("(")[0].strip() if "(" in parts else parts
        if msg_name in self.state.message_names:
            entry = {"type": msg_name, "time": time.time(), "raw": text}
            channel = f"repl_{msg_name}"
            if channel not in self.state.channels:
                self.state.channels[channel] = []
            self.state.channels[channel].append(entry)
            self.state.channel_log.append(entry)
            print(f"  → {channel}: {msg_name} sent")
        else:
            print(f"  ✗ Unknown message type: {msg_name}")

    def _eval_expression(self, text: str) -> None:
        try:
            from parser import parse_nous
            if self.state.program and self.state.program.world:
                world_name = self.state.program.world.name
            else:
                world_name = "_Repl"
            wrapped = f"""world {world_name} {{ law _repl = true }}
message _ReplMsg {{ val: string }}
soul _ReplSoul {{
    mind: test @ Tier1
    senses: [_repl]
    instinct {{
        {text}
    }}
    heal {{ on timeout => retry }}
}}"""
            prog = parse_nous(wrapped)
            print("  ✓ Valid NOUS expression")

            from typechecker import typecheck_program
            tc = typecheck_program(prog)
            for e in tc.errors:
                print(f"  ⚠ {e}")
            for w in tc.warnings:
                print(f"  ⚠ {w}")

        except Exception as e:
            err_msg = str(e)
            if "Unexpected token" in err_msg:
                short = err_msg.split("\n")[0]
                print(f"  ✗ Parse: {short}")
            else:
                print(f"  ✗ {err_msg}")

    def _cmd_help(self) -> None:
        print("""
  :load <file>    Load a .nous file
  :reload         Reload current file (hot-reload auto-detects changes)
  :souls          List all souls
  :messages       List all messages with fields
  :memory [soul]  Show memory state
  :channels       Show channel log
  :validate       Run law validator
  :typecheck      Run type checker
  :compile [out]  Compile to Python
  :ast [--json]   Show AST
  :info           Program summary
  :laws           Show world laws
  :routes         Show nervous system routes
  :watch <expr>   Watch a memory field
  :inject <ch> <json>  Inject message into channel
  :history        Show command history
  :mode <m>       Switch mode: normal, inspect, trace
  :clear          Clear screen
  :quit           Exit REPL

  You can also type NOUS code directly:
    let x = 42
    speak Signal(pair: "BTC/USDT", score: 0.9)
    soul MySoul { ... }
""")

    def _cmd_souls(self) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        for soul in self.state.program.souls:
            mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
            senses = ", ".join(soul.senses) if soul.senses else "none"
            mem = len(soul.memory.fields) if soul.memory else 0
            genes = len(soul.dna.genes) if soul.dna else 0
            stmts = len(soul.instinct.statements) if soul.instinct else 0
            print(f"  {soul.name}")
            print(f"    mind:     {mind}")
            print(f"    senses:   {senses}")
            print(f"    memory:   {mem} fields")
            if genes:
                print(f"    dna:      {genes} genes")
            print(f"    instinct: {stmts} statements")

    def _cmd_messages(self) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        for msg in self.state.program.messages:
            fields = ", ".join(f"{f.name}: {f.type_expr}" for f in msg.fields)
            print(f"  {msg.name}({fields})")

    def _cmd_memory(self, arg: str) -> None:
        if not self.state.memory_state:
            print("  No memory state")
            return
        if arg:
            mem = self.state.memory_state.get(arg)
            if mem:
                print(f"  {arg}:")
                for k, v in sorted(mem.items()):
                    print(f"    {k} = {v}")
            else:
                print(f"  Unknown soul: {arg}")
        else:
            for soul_name, mem in self.state.memory_state.items():
                print(f"  {soul_name}:")
                for k, v in sorted(mem.items()):
                    print(f"    {k} = {v}")

    def _cmd_channels(self) -> None:
        if not self.state.channel_log:
            print("  No channel activity")
            return
        print(f"  Channel log ({len(self.state.channel_log)} messages):")
        for entry in self.state.channel_log[-15:]:
            print(f"    [{entry.get('type', '?')}] {entry.get('raw', '')[:60]}")

    def _cmd_validate(self) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        from validator import validate_program
        result = validate_program(self.state.program)
        for e in result.errors:
            print(f"  ✗ {e}")
        for w in result.warnings:
            print(f"  ⚠ {w}")
        if result.ok:
            print(f"  ✓ Validation PASS ({len(result.warnings)} warnings)")
        else:
            print(f"  ✗ Validation FAIL ({len(result.errors)} errors)")

    def _cmd_typecheck(self) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        from typechecker import typecheck_program
        result = typecheck_program(self.state.program)
        for e in result.errors:
            print(f"  ✗ {e}")
        for w in result.warnings:
            print(f"  ⚠ {w}")
        if result.ok:
            print(f"  ✓ Type check PASS ({len(result.warnings)} warnings)")
        else:
            print(f"  ✗ Type check FAIL ({len(result.errors)} errors)")

    def _cmd_compile(self, arg: str) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        from codegen import generate_python
        code = generate_python(self.state.program)
        if arg:
            out = Path(arg)
            out.write_text(code, encoding="utf-8")
            print(f"  ✓ Written to {out} ({len(code.splitlines())} lines)")
        else:
            print(f"  Generated {len(code.splitlines())} lines")
            print(f"  Use :compile <output.py> to save")

    def _cmd_ast(self, arg: str) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        data = self.state.program.model_dump(exclude_none=True)
        if arg == "--json":
            print(json.dumps(data, indent=2, default=str))
        else:
            self._print_ast_compact(data)

    def _cmd_info(self) -> None:
        if not self.state.program:
            print("  No program loaded")
            return
        p = self.state.program
        w = p.world
        print(f"  World:      {w.name if w else 'none'}")
        print(f"  Heartbeat:  {w.heartbeat if w else 'N/A'}")
        print(f"  Laws:       {len(w.laws) if w else 0}")
        print(f"  Souls:      {len(p.souls)}")
        print(f"  Messages:   {len(p.messages)}")
        if p.nervous_system:
            print(f"  Routes:     {len(p.nervous_system.routes)}")
        if p.evolution:
            print(f"  Mutations:  {len(p.evolution.mutations)}")
        if p.perception:
            print(f"  Perception: {len(p.perception.rules)} rules")
        if self.state.source_path:
            print(f"  File:       {self.state.source_path}")

    def _cmd_laws(self) -> None:
        if not self.state.program or not self.state.program.world:
            print("  No world loaded")
            return
        for law in self.state.program.world.laws:
            print(f"  {law.name} = {law.expr}")

    def _cmd_routes(self) -> None:
        if not self.state.program or not self.state.program.nervous_system:
            print("  No nervous system defined")
            return
        from ast_nodes import RouteNode, MatchRouteNode, FanInNode, FanOutNode, FeedbackNode
        for r in self.state.program.nervous_system.routes:
            if isinstance(r, RouteNode):
                print(f"  {r.source} → {r.target}")
            elif isinstance(r, MatchRouteNode):
                print(f"  {r.source} → match ({len(r.arms)} arms)")
            elif isinstance(r, FanInNode):
                print(f"  [{', '.join(r.sources)}] → {r.target}")
            elif isinstance(r, FanOutNode):
                print(f"  {r.source} → [{', '.join(r.targets)}]")
            elif isinstance(r, FeedbackNode):
                print(f"  {r.source_soul}::{r.source_field} → {r.target_soul}::{r.target_field}")

    def _cmd_watch(self, arg: str) -> None:
        if not arg:
            print("Usage: :watch <soul.field>")
            return
        parts = arg.split(".")
        if len(parts) == 2:
            soul, field = parts
            mem = self.state.memory_state.get(soul, {})
            if field in mem:
                print(f"  {soul}.{field} = {mem[field]}")
            else:
                print(f"  Field not found: {soul}.{field}")
        else:
            for soul_name, mem in self.state.memory_state.items():
                if arg in mem:
                    print(f"  {soul_name}.{arg} = {mem[arg]}")

    def _cmd_inject(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            print("Usage: :inject <channel> <json>")
            return
        channel = parts[0]
        try:
            data = json.loads(parts[1])
        except json.JSONDecodeError as e:
            print(f"  Invalid JSON: {e}")
            return
        entry = {"type": channel, "data": data, "time": time.time(), "raw": arg}
        if channel not in self.state.channels:
            self.state.channels[channel] = []
        self.state.channels[channel].append(entry)
        self.state.channel_log.append(entry)
        print(f"  Injected into {channel}: {data}")

    def _cmd_history(self) -> None:
        n = readline.get_current_history_length()
        start = max(1, n - 20)
        for i in range(start, n + 1):
            item = readline.get_history_item(i)
            if item:
                print(f"  {i}: {item}")

    def _cmd_mode(self, arg: str) -> None:
        if arg in ("normal", "inspect", "trace"):
            self.mode = arg
            print(f"  Mode: {self.mode}")
        else:
            print(f"  Current mode: {self.mode}")
            print(f"  Available: normal, inspect, trace")

    def _print_ast_compact(self, data: Any, indent: int = 0) -> None:
        prefix = "  " * (indent + 1)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    print(f"{prefix}{k}:")
                    self._print_ast_compact(v, indent + 1)
                else:
                    print(f"{prefix}{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name", item.get("kind", ""))
                    print(f"{prefix}- {name}:")
                    self._print_ast_compact(item, indent + 1)
                else:
                    print(f"{prefix}- {item}")


def start_repl(file_path: Optional[str] = None) -> None:
    repl = NousRepl(file_path)
    repl.run()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    start_repl(path)
