"""
NOUS Hot Reload — File Watcher
==============================
Watches .nous files for changes, recompiles and restarts automatically.
Zero external dependencies (stat-based polling).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python


class NousWatcher:

    def __init__(self, sources: list[Path], poll_interval: float = 1.0) -> None:
        self._sources = sources
        self._poll = poll_interval
        self._mtimes: dict[Path, float] = {}
        self._proc: subprocess.Popen[bytes] | None = None
        self._compiled: dict[Path, Path] = {}
        self._running = False

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _get_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _compile(self, source: Path) -> Path | None:
        t0 = time.perf_counter()
        try:
            program = parse_nous_file(source)
        except Exception as e:
            print(f"  [{self._ts()}] ✗ Parse error: {e}")
            return None

        result = validate_program(program)
        for w in result.warnings:
            print(f"  [{self._ts()}] ⚠ {w}")
        if not result.ok:
            for e in result.errors:
                print(f"  [{self._ts()}] ✗ {e}")
            return None

        code = generate_python(program)
        out = source.with_suffix(".py")
        out.write_text(code, encoding="utf-8")
        elapsed = time.perf_counter() - t0
        world = program.world.name if program.world else source.stem
        print(f"  [{self._ts()}] ✓ {source.name} → {out.name} ({len(code.splitlines())} lines, {elapsed:.2f}s)")
        return out

    def _kill_proc(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            print(f"  [{self._ts()}] ↻ Stopping previous run...")
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            self._proc = None

    def _start_proc(self) -> None:
        if len(self._compiled) == 1:
            py_file = list(self._compiled.values())[0]
            self._proc = subprocess.Popen(
                [sys.executable, str(py_file)],
                cwd=str(py_file.parent),
                preexec_fn=os.setsid,
            )
        else:
            py_files = list(self._compiled.values())
            cmd = [sys.executable, "-c",
                   "import asyncio, importlib.util, sys\n"
                   "async def run():\n"
                   "    async with asyncio.TaskGroup() as tg:\n"
                   + "".join(
                       f"        spec{i} = importlib.util.spec_from_file_location('w{i}', '{pf}')\n"
                       f"        mod{i} = importlib.util.module_from_spec(spec{i})\n"
                       f"        spec{i}.loader.exec_module(mod{i})\n"
                       f"        tg.create_task(mod{i}.run_world())\n"
                       for i, pf in enumerate(py_files)
                   )
                   + "asyncio.run(run())\n"
            ]
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(py_files[0].parent),
                preexec_fn=os.setsid,
            )
        print(f"  [{self._ts()}] ▶ Running ({self._proc.pid})")

    def _initial_compile(self) -> bool:
        ok = True
        for src in self._sources:
            self._mtimes[src] = self._get_mtime(src)
            out = self._compile(src)
            if out is None:
                ok = False
            else:
                self._compiled[src] = out
        return ok

    def _check_changes(self) -> list[Path]:
        changed = []
        for src in self._sources:
            mt = self._get_mtime(src)
            if mt != self._mtimes.get(src, 0):
                self._mtimes[src] = mt
                changed.append(src)
        return changed

    def run(self) -> int:
        self._running = True
        files_str = ", ".join(s.name for s in self._sources)
        print(f"\n  NOUS Watch — {files_str}")
        print(f"  [{self._ts()}] Compiling...\n")

        if self._initial_compile() and self._compiled:
            self._start_proc()

        print(f"\n  [{self._ts()}] Watching for changes... (Ctrl+C to stop)\n")

        try:
            while self._running:
                time.sleep(self._poll)
                changed = self._check_changes()
                if not changed:
                    if self._proc and self._proc.poll() is not None:
                        code = self._proc.returncode
                        print(f"  [{self._ts()}] Process exited ({code}). Waiting for changes...")
                        self._proc = None
                    continue

                print(f"\n  [{self._ts()}] Changed: {', '.join(c.name for c in changed)}")
                recompile_ok = True
                for src in changed:
                    out = self._compile(src)
                    if out is None:
                        recompile_ok = False
                    else:
                        self._compiled[src] = out

                if recompile_ok and self._compiled:
                    self._kill_proc()
                    self._start_proc()
                    print(f"  [{self._ts()}] Watching for changes...\n")
                else:
                    print(f"  [{self._ts()}] Fix errors and save. Watching...\n")

        except KeyboardInterrupt:
            print(f"\n  [{self._ts()}] Stopping...")
            self._kill_proc()
            print(f"  [{self._ts()}] Bye.\n")
            return 0

        return 0


def watch(sources: list[Path], poll: float = 1.0) -> int:
    for s in sources:
        if not s.exists():
            print(f"Error: file not found: {s}", file=sys.stderr)
            return 1
    watcher = NousWatcher(sources, poll)
    return watcher.run()
