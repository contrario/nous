"""
NOUS REPL — Interactive Shell
==============================
Load a .nous world, run individual souls, inspect AST, memory, channels.
"""
from __future__ import annotations

import asyncio
import cmd
import importlib.util
import os
import readline
import sys
import time
from pathlib import Path
from typing import Any

from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python


class NousREPL(cmd.Cmd):
    intro = ""
    prompt = "nous> "

    def __init__(self) -> None:
        super().__init__()
        self._program: Any = None
        self._source: Path | None = None
        self._module: Any = None
        self._compiled: Path | None = None
        self._loop = asyncio.new_event_loop()

    def _ts(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def do_load(self, arg: str) -> None:
        """Load a .nous file: load gate_alpha.nous"""
        path = Path(arg.strip())
        if not path.exists():
            print(f"  File not found: {path}")
            return
        t0 = time.perf_counter()
        try:
            self._program = parse_nous_file(path)
        except Exception as e:
            print(f"  Parse error: {e}")
            return
        result = validate_program(self._program)
        for w in result.warnings:
            print(f"  {w}")
        if not result.ok:
            for e in result.errors:
                print(f"  {e}")
            print("  Validation FAILED")
            return
        code = generate_python(self._program)
        self._compiled = path.with_suffix(".repl.py")
        self._compiled.write_text(code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("nous_repl_world", str(self._compiled))
        if spec and spec.loader:
            self._module = importlib.util.module_from_spec(spec)
            sys.modules["nous_repl_world"] = self._module
            spec.loader.exec_module(self._module)
        self._source = path
        world = self._program.world.name if self._program.world else "?"
        souls = [s.name for s in self._program.souls]
        elapsed = time.perf_counter() - t0
        print(f"  Loaded: {world} ({len(souls)} souls) in {elapsed:.2f}s")
        print(f"  Souls: {', '.join(souls)}")
        self.prompt = f"nous:{world}> "

    def do_souls(self, arg: str) -> None:
        """List all souls in loaded world"""
        if not self._program:
            print("  No world loaded. Use: load <file.nous>")
            return
        for soul in self._program.souls:
            mind = f"{soul.mind.model} @ {soul.mind.tier}" if soul.mind else "none"
            senses = ", ".join(soul.senses) if soul.senses else "none"
            print(f"  {soul.name}: mind={mind} senses=[{senses}]")

    def do_laws(self, arg: str) -> None:
        """Show all laws"""
        if not self._program or not self._program.world:
            print("  No world loaded.")
            return
        for law in self._program.world.laws:
            print(f"  {law.name} = {law.expr}")

    def do_ast(self, arg: str) -> None:
        """Show AST for a soul: ast Scout"""
        if not self._program:
            print("  No world loaded.")
            return
        name = arg.strip()
        if not name:
            print(f"  World: {self._program.world.name if self._program.world else '?'}")
            print(f"  Souls: {[s.name for s in self._program.souls]}")
            print(f"  Messages: {[m.name for m in self._program.messages]}")
            return
        for soul in self._program.souls:
            if soul.name == name:
                print(soul.model_dump_json(indent=2))
                return
        print(f"  Soul '{name}' not found")

    def do_messages(self, arg: str) -> None:
        """List all message types"""
        if not self._program:
            print("  No world loaded.")
            return
        for msg in self._program.messages:
            fields = ", ".join(f"{f.name}: {f.type_expr}" for f in msg.fields)
            print(f"  {msg.name} {{ {fields} }}")

    def do_dna(self, arg: str) -> None:
        """Show DNA for a soul: dna Scout"""
        if not self._program:
            print("  No world loaded.")
            return
        name = arg.strip()
        for soul in self._program.souls:
            if not name or soul.name == name:
                if soul.dna and soul.dna.genes:
                    print(f"  {soul.name}:")
                    for gene in soul.dna.genes:
                        r = gene.range; print(f"    {gene.name}: {gene.value} ~ [{r[0]}, {r[1]}]" if len(r) >= 2 else f"    {gene.name}: {gene.value}")
                elif not name:
                    continue
                else:
                    print(f"  {soul.name}: no DNA")

    def do_routes(self, arg: str) -> None:
        """Show nervous system routes"""
        if not self._program or not self._program.nervous_system:
            print("  No nervous system defined.")
            return
        ns = self._program.nervous_system
        for route in ns.routes:
            print(f"  {route.source} -> {route.target}")
        # Only routes in current NervousSystemNode

    def do_run(self, arg: str) -> None:
        """Run a soul: run Scout (or 'run' for all)"""
        if not self._module:
            print("  No world loaded.")
            return
        name = arg.strip()
        if not name:
            run_fn = getattr(self._module, "run_world", None)
            if run_fn:
                print(f"  [{self._ts()}] Running all souls... (Ctrl+C to stop)")
                try:
                    self._loop.run_until_complete(run_fn())
                except KeyboardInterrupt:
                    print(f"\n  [{self._ts()}] Stopped.")
                except Exception as e:
                    print(f"  Error: {e}")
            return
        soul_cls = getattr(self._module, f"Soul_{name}", None)
        if not soul_cls:
            print(f"  Soul '{name}' not found in compiled module")
            return
        print(f"  [{self._ts()}] Running {name}...")
        soul = soul_cls()
        try:
            self._loop.run_until_complete(soul.run_cycle())
        except KeyboardInterrupt:
            print(f"\n  [{self._ts()}] Stopped.")
        except Exception as e:
            print(f"  Error: {e}")

    def do_compile(self, arg: str) -> None:
        """Compile loaded world and show output path"""
        if not self._source:
            print("  No world loaded.")
            return
        code = generate_python(self._program)
        out = self._source.with_suffix(".py")
        out.write_text(code, encoding="utf-8")
        print(f"  {out} ({len(code.splitlines())} lines)")

    def do_tools(self, arg: str) -> None:
        """List available tools"""
        tools_dir = Path("/opt/aetherlang_agents/tools")
        if not tools_dir.exists():
            print("  Tools dir not found")
            return
        tools = sorted(f.stem for f in tools_dir.glob("*.py") if not f.stem.startswith("_") and f.stem != "base")
        print(f"  {len(tools)} tools: {', '.join(tools[:20])}")
        if len(tools) > 20:
            print(f"  ... and {len(tools)-20} more")

    def do_reload(self, arg: str) -> None:
        """Reload current .nous file"""
        if self._source:
            self.do_load(str(self._source))
        else:
            print("  No file loaded.")

    def do_eval(self, arg: str) -> None:
        """Evaluate Python expression in module context: eval WORLD_CONFIG"""
        if not self._module:
            print("  No world loaded.")
            return
        try:
            result = eval(arg.strip(), vars(self._module))
            print(f"  {result}")
        except Exception as e:
            print(f"  Error: {e}")

    def do_quit(self, arg: str) -> None:
        """Exit REPL"""
        if self._compiled and self._compiled.exists():
            self._compiled.unlink(missing_ok=True)
        print("  Bye.")
        return True

    do_exit = do_quit
    do_q = do_quit

    def do_help(self, arg: str) -> None:
        """Show commands"""
        if arg:
            super().do_help(arg)
            return
        print("  Commands:")
        print("    load <file.nous>   Load and compile a world")
        print("    reload             Reload current file")
        print("    souls              List souls")
        print("    laws               Show laws")
        print("    messages           Show message types")
        print("    dna [soul]         Show DNA params")
        print("    routes             Show nervous system")
        print("    ast [soul]         Show AST (JSON)")
        print("    tools              List available tools")
        print("    run [soul]         Run all or one soul")
        print("    compile            Compile to .py")
        print("    eval <expr>        Eval Python in module context")
        print("    quit               Exit")

    def default(self, line: str) -> None:
        if line.strip():
            print(f"  Unknown command: {line}. Type 'help' for commands.")

    def emptyline(self) -> None:
        pass


def start_repl(source: Path | None = None) -> int:
    repl = NousREPL()
    print("  NOUS Shell v1.0")
    print("  Type 'help' for commands, 'quit' to exit.\n")
    if source:
        repl.do_load(str(source))
        print()
    try:
        repl.cmdloop()
    except KeyboardInterrupt:
        print("\n  Bye.")
    return 0
