"""
NOUS REPL — Διάλογος (Dialogos)
================================
Interactive shell for the Living Language.
Commands start with ':'. Everything else is NOUS code.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import readline
import sys
import time
from pathlib import Path
from typing import Any, Optional

from ast_nodes import NousProgram, SoulNode
from parser import parse_nous, parse_nous_file
from validator import validate_program
from codegen import generate_python

log = logging.getLogger("nous.repl")

HISTORY_FILE = Path.home() / ".nous_history"

KEYWORDS = [
    "world", "soul", "mind", "memory", "instinct", "dna", "heal",
    "law", "message", "nervous_system", "evolution", "perception",
    "sense", "speak", "listen", "guard", "remember", "let", "for",
    "if", "else", "sleep", "spawn", "match",
    "κόσμος", "ψυχή", "νους", "μνήμη", "ένστικτο", "αίσθηση",
    "θυμάμαι", "λέω", "ακούω", "φύλακας", "θεραπεία", "νόμος",
    "Tier0A", "Tier0B", "Tier1", "Tier2", "Tier3",
]

HELP_TEXT = """
<b>NOUS Shell Commands:</b>

  :help              Show this help
  :load <file>       Load a .nous file
  :ast               Show Living AST of loaded program
  :ast <soul>        Show AST for specific soul
  :compile           Compile loaded program to Python
  :compile -o <file> Compile and save to file
  :validate          Validate loaded program
  :info              Show program summary
  :dna               Show all DNA values
  :dna <soul>        Show DNA for specific soul
  :souls             List all souls
  :tools             List available Noosphere tools
  :evolve            Run evolution cycle on loaded program
  :evolve <soul>     Evolve specific soul
  :run               Run loaded program
  :clear             Clear screen
  :reset             Reset (unload program)
  :quit / :q         Exit shell

  <nous code>        Parse and show AST for snippet
"""


class NousCompleter:
    def __init__(self) -> None:
        self.matches: list[str] = []

    def complete(self, text: str, state: int) -> Optional[str]:
        if state == 0:
            if text.startswith(":"):
                commands = [
                    ":help", ":load", ":ast", ":compile", ":validate",
                    ":info", ":dna", ":souls", ":tools", ":evolve",
                    ":run", ":clear", ":reset", ":quit", ":q",
                ]
                self.matches = [c for c in commands if c.startswith(text)]
            else:
                self.matches = [k for k in KEYWORDS if k.startswith(text)]
        return self.matches[state] if state < len(self.matches) else None


class NousREPL:

    def __init__(self) -> None:
        self.program: Optional[NousProgram] = None
        self.source_path: Optional[Path] = None
        self.buffer: list[str] = []
        self.running = True

    def start(self) -> None:
        self._setup_readline()
        self._print_banner()

        while self.running:
            try:
                prompt = self._get_prompt()
                line = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print("\n")
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith(":"):
                self._handle_command(line)
            else:
                self._handle_code(line)

        self._save_history()

    def _setup_readline(self) -> None:
        completer = NousCompleter()
        readline.set_completer(completer.complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")
        if HISTORY_FILE.exists():
            try:
                readline.read_history_file(str(HISTORY_FILE))
            except OSError:
                pass

    def _save_history(self) -> None:
        try:
            readline.write_history_file(str(HISTORY_FILE))
        except OSError:
            pass

    def _print_banner(self) -> None:
        print("""
  \033[1;36m╔═══════════════════════════════════════╗
  ║  NOUS Shell — Νοῦς Interactive       ║
  ║  Type :help for commands              ║
  ╚═══════════════════════════════════════╝\033[0m
""")
        if self.program:
            name = self.program.world.name if self.program.world else "Unknown"
            print(f"  Loaded: {name} ({len(self.program.souls)} souls)")
        else:
            print("  No program loaded. Use :load <file.nous>")
        print()

    def _get_prompt(self) -> str:
        if self.buffer:
            return "\033[33m...  \033[0m"
        if self.program and self.program.world:
            return f"\033[1;32mnous:{self.program.world.name}\033[0m> "
        return "\033[1;32mnous\033[0m> "

    def _handle_command(self, line: str) -> None:
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in (":quit", ":q", ":exit"):
            self.running = False
        elif cmd == ":help":
            print(HELP_TEXT.replace("<b>", "\033[1m").replace("</b>", "\033[0m"))
        elif cmd == ":load":
            self._cmd_load(arg)
        elif cmd == ":ast":
            self._cmd_ast(arg)
        elif cmd == ":compile":
            self._cmd_compile(arg)
        elif cmd == ":validate":
            self._cmd_validate()
        elif cmd == ":info":
            self._cmd_info()
        elif cmd == ":dna":
            self._cmd_dna(arg)
        elif cmd == ":souls":
            self._cmd_souls()
        elif cmd == ":tools":
            self._cmd_tools()
        elif cmd == ":evolve":
            self._cmd_evolve(arg)
        elif cmd == ":run":
            self._cmd_run()
        elif cmd == ":clear":
            os.system("clear" if os.name != "nt" else "cls")
        elif cmd == ":reset":
            self.program = None
            self.source_path = None
            print("Program unloaded.")
        else:
            print(f"Unknown command: {cmd}. Type :help for available commands.")

    def _handle_code(self, line: str) -> None:
        self.buffer.append(line)

        if line.endswith("{"):
            return

        brace_count = sum(l.count("{") - l.count("}") for l in self.buffer)
        if brace_count > 0:
            return

        code = "\n".join(self.buffer)
        self.buffer.clear()

        try:
            prog = parse_nous(code)
            if prog.souls:
                for soul in prog.souls:
                    self._print_soul_summary(soul)
            elif prog.world:
                print(f"  World: {prog.world.name}")
                for law in prog.world.laws:
                    print(f"    law {law.name} = {law.expr}")
            elif prog.messages:
                for msg in prog.messages:
                    print(f"  Message: {msg.name} ({len(msg.fields)} fields)")
            else:
                print(f"  Parsed OK ({len(code)} chars)")

            result = validate_program(prog)
            if result.errors:
                for e in result.errors:
                    print(f"  \033[31m⚠ {e}\033[0m")
            if result.warnings:
                for w in result.warnings:
                    print(f"  \033[33m⚠ {w}\033[0m")

        except Exception as e:
            error_msg = str(e)
            print(f"  \033[31mError: {self._format_error(error_msg)}\033[0m")

    def _cmd_load(self, path: str) -> None:
        if not path:
            print("Usage: :load <file.nous>")
            return

        p = Path(path)
        if not p.exists():
            p = Path("/opt/aetherlang_agents/nous") / path
        if not p.exists():
            print(f"\033[31mFile not found: {path}\033[0m")
            return

        try:
            t0 = time.perf_counter()
            self.program = parse_nous_file(p)
            self.source_path = p
            elapsed = time.perf_counter() - t0
            name = self.program.world.name if self.program.world else "Unknown"
            souls = len(self.program.souls)
            msgs = len(self.program.messages)
            print(f"  Loaded: {name} | {souls} souls | {msgs} messages | {elapsed:.2f}s")
        except Exception as e:
            print(f"\033[31mParse error: {self._format_error(str(e))}\033[0m")

    def _cmd_ast(self, soul_name: str) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        if soul_name:
            soul = next((s for s in self.program.souls if s.name == soul_name), None)
            if not soul:
                print(f"Soul not found: {soul_name}")
                return
            data = soul.model_dump(exclude_none=True)
            print(json.dumps(data, indent=2, default=str))
        else:
            data = self.program.model_dump(exclude_none=True)
            print(json.dumps(data, indent=2, default=str)[:3000])
            total = len(json.dumps(data, default=str))
            if total > 3000:
                print(f"\n  ... ({total} chars total, use :ast <soul> for specific)")

    def _cmd_compile(self, arg: str) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        code = generate_python(self.program)
        if arg.startswith("-o "):
            outpath = arg[3:].strip()
            Path(outpath).write_text(code, encoding="utf-8")
            print(f"  Compiled: {outpath} ({len(code.splitlines())} lines)")
        else:
            print(f"  {len(code.splitlines())} lines Python generated")
            print(f"  Use :compile -o <file> to save")

    def _cmd_validate(self) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        result = validate_program(self.program)
        if result.ok:
            print("  \033[32mValidation PASS\033[0m")
        else:
            for e in result.errors:
                print(f"  \033[31m✗ {e}\033[0m")
        for w in result.warnings:
            print(f"  \033[33m⚠ {w}\033[0m")

    def _cmd_info(self) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        p = self.program
        name = p.world.name if p.world else "Unknown"
        print(f"  World: {name}")
        if p.world and p.world.laws:
            for law in p.world.laws:
                print(f"    law {law.name}")
        print(f"  Souls: {len(p.souls)}")
        for s in p.souls:
            mind = f"{s.mind.model} @ {s.mind.tier.value}" if s.mind else "none"
            print(f"    {s.name}: {mind} | {len(s.senses)} senses")
        print(f"  Messages: {len(p.messages)}")
        for m in p.messages:
            print(f"    {m.name}: {len(m.fields)} fields")
        if p.nervous_system:
            print(f"  Nervous system: {len(p.nervous_system.routes)} routes")
        if p.evolution:
            print(f"  Evolution: {len(p.evolution.mutations)} mutation targets")
        if p.perception:
            print(f"  Perception: {len(p.perception.rules)} triggers")

    def _cmd_dna(self, soul_name: str) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        souls = self.program.souls
        if soul_name:
            souls = [s for s in souls if s.name == soul_name]
            if not souls:
                print(f"Soul not found: {soul_name}")
                return

        for soul in souls:
            if soul.dna and soul.dna.genes:
                print(f"  {soul.name}.dna:")
                for g in soul.dna.genes:
                    range_str = f" ~ [{', '.join(str(v) for v in g.range)}]" if g.range else ""
                    print(f"    {g.name}: {g.value}{range_str}")

    def _cmd_souls(self) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return
        for s in self.program.souls:
            mind = f"{s.mind.model} @ {s.mind.tier.value}" if s.mind else "none"
            stmts = len(s.instinct.statements) if s.instinct else 0
            heals = len(s.heal.rules) if s.heal else 0
            genes = len(s.dna.genes) if s.dna else 0
            print(f"  {s.name}: {mind} | {stmts} stmts | {genes} genes | {heals} heals")

    def _cmd_tools(self) -> None:
        try:
            from runtime import ToolRegistry
            t = ToolRegistry()
            t.scan_noosphere()
            tools = t.available
            print(f"  {len(tools)} tools available:")
            for tool in tools:
                print(f"    {tool}")
        except Exception as e:
            print(f"  Error scanning tools: {e}")

    def _cmd_evolve(self, soul_name: str) -> None:
        if not self.program:
            print("No program loaded. Use :load first.")
            return

        from aevolver import Aevolver
        evo = Aevolver(self.program)
        if soul_name:
            result = evo.mutate_soul_dna(soul_name)
            status = "\033[32m✓ ACCEPTED\033[0m" if result.accepted else "\033[31m✗ ROLLED BACK\033[0m"
            print(f"  {result.soul_name}: {status}")
            print(f"  Fitness: {result.parent_fitness:.3f} → {result.child_fitness:.3f}")
            for m in result.mutations:
                print(f"    {m.gene_name}: {m.old_value} → {m.new_value}")
        else:
            report = evo.evolve()
            for c in report.cycles:
                status = "\033[32m✓\033[0m" if c.accepted else "\033[31m✗\033[0m"
                print(f"  {status} {c.soul_name}: {c.parent_fitness:.3f} → {c.child_fitness:.3f}")
                for m in c.mutations:
                    print(f"    {m.gene_name}: {m.old_value} → {m.new_value}")

    def _cmd_run(self) -> None:
        if not self.source_path:
            print("No file loaded. Use :load first.")
            return
        import subprocess
        code = generate_python(self.program)
        tmp = self.source_path.with_suffix(".repl.py")
        tmp.write_text(code, encoding="utf-8")
        print(f"  Running {self.source_path.name}... (Ctrl+C to stop)\n")
        try:
            subprocess.run([sys.executable, str(tmp)], cwd=str(self.source_path.parent))
        except KeyboardInterrupt:
            print("\n  Stopped.")
        finally:
            if tmp.exists():
                tmp.unlink()

    def _print_soul_summary(self, soul: SoulNode) -> None:
        mind = f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none"
        stmts = len(soul.instinct.statements) if soul.instinct else 0
        print(f"  Soul: {soul.name} | {mind} | {stmts} statements | {len(soul.senses)} senses")

    @staticmethod
    def _format_error(error: str) -> str:
        if "Expected one of" in error:
            lines = error.split("\n")
            first = lines[0] if lines else error
            if "at line" in first:
                return first
            return first[:200]

        if "Unexpected token" in error:
            parts = error.split("at line ")
            if len(parts) > 1:
                loc = parts[1].split(",")[0]
                return f"Unexpected token at line {loc}"

        return error[:300]


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    repl = NousREPL()
    if len(sys.argv) > 1:
        repl._cmd_load(sys.argv[1])
    repl.start()


if __name__ == "__main__":
    main()
