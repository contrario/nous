"""
NOUS Self-Compiler Runner — Εκκίνηση Αυτομεταγλώττισης
=========================================================
Bootstraps the self-hosting compiler:
1. Parses compiler.nous using the Python compiler
2. Generates Python code
3. Registers compiler senses (file I/O, parse, validate, codegen)
4. Executes the generated compiler as a single-pass pipeline
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.self_compiler")


async def run_self_compile(
    source_files: list[str],
    target: str = "python",
    output_dir: Optional[str] = None,
    compiler_nous: Optional[str] = None,
) -> dict[str, Any]:
    from parser import parse_nous_file
    from codegen import generate_python
    from validator import validate_program
    from typechecker import typecheck_program
    from compiler_senses import (
        tool_file_read, tool_file_write, tool_nous_parse,
        tool_nous_validate, tool_nous_typecheck, tool_nous_codegen,
    )

    t0 = time.perf_counter()

    compiler_path = Path(compiler_nous or Path(__file__).parent / "compiler.nous")
    if not compiler_path.exists():
        return {"ok": False, "error": f"compiler.nous not found at {compiler_path}"}

    print(f"[1/5] Parsing compiler.nous...")
    try:
        compiler_program = parse_nous_file(compiler_path)
    except Exception as e:
        return {"ok": False, "error": f"Failed to parse compiler.nous: {e}"}

    world_name = compiler_program.world.name if compiler_program.world else "Unknown"
    print(f"      World: {world_name} | {len(compiler_program.souls)} souls")

    print(f"[2/5] Validating compiler...")
    vresult = validate_program(compiler_program)
    if not vresult.ok:
        errors = [str(e) for e in vresult.errors]
        return {"ok": False, "error": f"Compiler validation failed: {errors}"}
    print(f"      Validation PASS")

    print(f"[3/5] Type checking compiler...")
    tresult = typecheck_program(compiler_program)
    tc_status = "PASS" if tresult.ok else f"{len(tresult.errors)} errors"
    print(f"      Type check {tc_status}")

    print(f"[4/5] Self-compiling {len(source_files)} source file(s)...")
    out_dir = Path(output_dir) if output_dir else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for source_file in source_files:
        source_path = Path(source_file)
        if not source_path.exists():
            results.append({"path": source_file, "ok": False, "error": "File not found"})
            continue

        file_result = await _compile_single(
            source_path, target, out_dir,
            tool_nous_parse, tool_nous_validate,
            tool_nous_typecheck, tool_nous_codegen,
            tool_file_write,
        )
        results.append(file_result)

    elapsed = time.perf_counter() - t0

    successes = sum(1 for r in results if r.get("ok"))
    failures = len(results) - successes
    print(f"\n[5/5] Self-compilation complete in {elapsed:.2f}s")
    print(f"      Results: {successes} succeeded, {failures} failed")

    for r in results:
        status = "✓" if r.get("ok") else "✗"
        path = r.get("path", "?")
        if r.get("ok"):
            print(f"      {status} {path} → {r.get('output_path', '?')} ({r.get('code_lines', 0)} lines)")
        else:
            print(f"      {status} {path}: {r.get('error', 'unknown error')}")

    return {
        "ok": failures == 0,
        "files": results,
        "elapsed": elapsed,
        "successes": successes,
        "failures": failures,
        "compiler": str(compiler_path),
    }


async def _compile_single(
    source_path: Path,
    target: str,
    out_dir: Path,
    parse_fn: Any,
    validate_fn: Any,
    typecheck_fn: Any,
    codegen_fn: Any,
    write_fn: Any,
) -> dict[str, Any]:
    source = source_path.read_text(encoding="utf-8")

    parsed_raw = await parse_fn(source=source)
    parsed = json.loads(parsed_raw) if isinstance(parsed_raw, str) else parsed_raw
    if not parsed.get("ok"):
        return {"path": str(source_path), "ok": False, "error": f"Parse: {parsed.get('error', '?')}", "stage": "parse"}

    validated_raw = await validate_fn(source=source)
    validated = json.loads(validated_raw) if isinstance(validated_raw, str) else validated_raw
    if not validated.get("ok"):
        errors = validated.get("errors", [])
        return {"path": str(source_path), "ok": False, "error": f"Validate: {errors}", "stage": "validate"}

    typed_raw = await typecheck_fn(source=source)
    typed = json.loads(typed_raw) if isinstance(typed_raw, str) else typed_raw

    gen_raw = await codegen_fn(source=source, target=target)
    gen = json.loads(gen_raw) if isinstance(gen_raw, str) else gen_raw
    if not gen.get("ok"):
        return {"path": str(source_path), "ok": False, "error": f"Codegen: {gen.get('error', '?')}", "stage": "codegen"}

    suffix = ".mjs" if target in ("js", "javascript") else ".py"
    out_name = source_path.stem + "_selfcompiled" + suffix
    out_path = out_dir / out_name

    written_raw = await write_fn(path=str(out_path), content=gen["code"])
    written = json.loads(written_raw) if isinstance(written_raw, str) else written_raw

    return {
        "path": str(source_path),
        "ok": True,
        "output_path": str(out_path),
        "code_lines": gen.get("lines", 0),
        "compile_check": gen.get("compile_check", False),
        "target": target,
        "world": parsed.get("world", "?"),
        "souls": parsed.get("soul_count", 0),
        "type_ok": typed.get("ok", False),
    }


def cmd_self_compile(args: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="nous self-compile")
    ap.add_argument("files", nargs="+", help=".nous files to compile")
    ap.add_argument("--target", default="python", choices=["python", "js"])
    ap.add_argument("-o", "--output", default=None, help="Output directory")
    ap.add_argument("--compiler", default=None, help="Path to compiler.nous")
    parsed = ap.parse_args(args)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    result = asyncio.run(run_self_compile(
        source_files=parsed.files,
        target=parsed.target,
        output_dir=parsed.output,
        compiler_nous=parsed.compiler,
    ))

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(cmd_self_compile(sys.argv[1:]))
