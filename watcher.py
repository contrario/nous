"""
NOUS Watch Mode — Φρουρός (Frouros)
=====================================
Watches .nous files for changes, auto-recompiles.
Incremental: only re-runs pipeline on modified files.
"""
from __future__ import annotations

import os
import py_compile
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


def watch_file(source: Path, output: Optional[Path] = None, interval: float = 1.0) -> None:
    if not source.exists():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return

    out_path = output or source.with_suffix(".py")
    print(f"═══ NOUS Watch Mode ═══")
    print(f"  Watching: {source}")
    print(f"  Output:   {out_path}")
    print(f"  Interval: {interval}s")
    print(f"  Press Ctrl+C to stop\n")

    last_mtime: float = 0.0
    last_imports_mtime: dict[str, float] = {}
    cycle = 0

    _run_pipeline(source, out_path, cycle)
    last_mtime = source.stat().st_mtime

    try:
        while True:
            time.sleep(interval)
            current_mtime = source.stat().st_mtime if source.exists() else 0.0
            changed = current_mtime > last_mtime
            changed_file = str(source) if changed else None

            if not changed:
                imports_changed, changed_file = _check_import_changes(source, last_imports_mtime)
                changed = imports_changed

            if changed:
                cycle += 1
                last_mtime = current_mtime
                ts = time.strftime("%H:%M:%S")
                trigger = Path(changed_file).name if changed_file else source.name
                print(f"\n[{ts}] Change detected: {trigger}")
                _run_pipeline(source, out_path, cycle)
                _update_import_mtimes(source, last_imports_mtime)

    except KeyboardInterrupt:
        print(f"\n\nWatch stopped. {cycle} recompiles.")


def _run_pipeline(source: Path, out_path: Path, cycle: int) -> bool:
    t0 = time.perf_counter()

    script_dir = str(Path(__file__).parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    import parser as parser_mod
    parser_mod._PARSER_CACHE = None

    from parser import parse_nous_file
    from validator import validate_program
    from typechecker import typecheck_program
    from codegen import generate_python

    try:
        program = parse_nous_file(source)
    except Exception as e:
        _error(f"Parse: {e}")
        return False
    world_name = program.world.name if program.world else "?"
    soul_count = len(program.souls)
    msg_count = len(program.messages)

    if program.imports:
        try:
            from import_resolver import resolve_imports
            ir = resolve_imports(program, source)
            if not ir.ok:
                for e in ir.errors:
                    _error(str(e))
                return False
            program = ir.program
            soul_count = len(program.souls)
            msg_count = len(program.messages)
            _ok(f"Imports resolved ({len(ir.resolved_files)} files)")
        except Exception as e:
            _warn(f"Import resolver: {e}")

    vr = validate_program(program)
    if not vr.ok:
        for e in vr.errors:
            _error(f"Validate: {e}")
        return False
    for w in vr.warnings:
        _warn(f"Validate: {w}")

    tc = typecheck_program(program)
    if not tc.ok:
        for e in tc.errors:
            _error(f"TypeCheck: {e}")
        return False
    for w in tc.warnings:
        _warn(f"TypeCheck: {w}")

    code = generate_python(program)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        _error(f"py_compile: {e}")
        os.unlink(tmp)
        return False
    os.unlink(tmp)

    out_path.write_text(code, encoding="utf-8")
    elapsed = (time.perf_counter() - t0) * 1000
    _ok(f"#{cycle} {world_name} | {soul_count} souls | {msg_count} msgs | {len(code.splitlines())} lines | {elapsed:.0f}ms")

    if program.tests:
        try:
            from test_runner import run_tests
            suite = run_tests(program)
            if suite.ok:
                _ok(f"Tests: {suite.passed_tests}/{suite.total_tests} passed ({suite.total_assertions} assertions)")
            else:
                _error(f"Tests: {suite.passed_tests}/{suite.total_tests} passed ({suite.failed_tests} failed)")
        except Exception as e:
            _warn(f"Tests: {e}")

    return True


def _check_import_changes(source: Path, last_mtimes: dict[str, float]) -> tuple[bool, Optional[str]]:
    try:
        from parser import parse_nous_file
        program = parse_nous_file(source)
    except Exception:
        return False, None

    base_dir = source.parent
    for imp in program.imports:
        if imp.is_package:
            continue
        imp_path = base_dir / imp.path
        if not imp_path.exists():
            continue
        key = str(imp_path)
        current = imp_path.stat().st_mtime
        if key in last_mtimes and current > last_mtimes[key]:
            return True, key

    return False, None


def _update_import_mtimes(source: Path, last_mtimes: dict[str, float]) -> None:
    try:
        from parser import parse_nous_file
        program = parse_nous_file(source)
    except Exception:
        return

    base_dir = source.parent
    for imp in program.imports:
        if imp.is_package:
            continue
        imp_path = base_dir / imp.path
        if imp_path.exists():
            last_mtimes[str(imp_path)] = imp_path.stat().st_mtime


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _error(msg: str) -> None:
    print(f"  ✗ {msg}")
