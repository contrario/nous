"""
NOUS Test Suite — Self-Hosting Compiler (P28)
===============================================
Tests: compiler senses, compiler.nous parsing, self-compilation pipeline.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def test_1_compiler_senses_registration() -> None:
    print("\n═══ Test 1: Compiler Senses Registration ═══")
    from compiler_senses import COMPILER_SENSES
    expected = ["file_read", "file_write", "file_list", "nous_parse",
                "nous_validate", "nous_typecheck", "nous_codegen",
                "nous_format", "nous_info"]
    for name in expected:
        check(f"sense '{name}' registered", name in COMPILER_SENSES)
    check("total count", len(COMPILER_SENSES) == 9, f"got {len(COMPILER_SENSES)}")


def test_2_file_read_sense() -> None:
    print("\n═══ Test 2: file_read Sense ═══")
    from compiler_senses import tool_file_read

    async def _run() -> None:
        result_raw = await tool_file_read(path="compiler.nous")
        result = json.loads(result_raw)
        check("file_read ok", result["ok"])
        check("has content", len(result.get("content", "")) > 0)
        check("has lines", result.get("lines", 0) > 0)
        check("has size", result.get("size", 0) > 0)

        bad_raw = await tool_file_read(path="nonexistent_file.xyz")
        bad = json.loads(bad_raw)
        check("missing file returns error", not bad["ok"])

    asyncio.run(_run())


def test_3_nous_parse_sense() -> None:
    print("\n═══ Test 3: nous_parse Sense ═══")
    from compiler_senses import tool_nous_parse

    async def _run() -> None:
        source = '''
world TestWorld {
    law cost = $0.10 per cycle
    heartbeat = 5m
}
message Ping { ts: float = 0.0 }
soul Worker {
    mind: claude-sonnet @ Tier0A
    instinct { speak Ping(ts: now()) }
    heal { on timeout => retry(3, exponential) }
}
'''
        result_raw = await tool_nous_parse(source=source)
        result = json.loads(result_raw)
        check("parse ok", result["ok"])
        check("world name", result["world"] == "TestWorld")
        check("soul count", result["soul_count"] == 1)
        check("message count", result["message_count"] == 1)

        bad_raw = await tool_nous_parse(source="this is not valid nous code {{{")
        bad = json.loads(bad_raw)
        check("bad source returns error", not bad["ok"])

    asyncio.run(_run())


def test_4_nous_validate_sense() -> None:
    print("\n═══ Test 4: nous_validate Sense ═══")
    from compiler_senses import tool_nous_validate

    async def _run() -> None:
        good = '''
world V {
    law c = $0.10 per cycle
    heartbeat = 5m
}
message P { x: int = 0 }
soul S {
    mind: claude-sonnet @ Tier0A
    instinct { speak P(x: 1) }
    heal { on timeout => retry(1, fixed) }
}
'''
        result_raw = await tool_nous_validate(source=good)
        result = json.loads(result_raw)
        check("valid source ok", result["ok"])
        check("zero errors", result["error_count"] == 0)

    asyncio.run(_run())


def test_5_nous_codegen_sense() -> None:
    print("\n═══ Test 5: nous_codegen Sense ═══")
    from compiler_senses import tool_nous_codegen

    async def _run() -> None:
        source = '''
world CG {
    law c = $0.10 per cycle
    heartbeat = 5m
}
message Out { v: string = "" }
soul Gen {
    mind: claude-sonnet @ Tier0A
    instinct { speak Out(v: "hello") }
    heal { on timeout => retry(1, fixed) }
}
'''
        py_raw = await tool_nous_codegen(source=source, target="python")
        py = json.loads(py_raw)
        check("python codegen ok", py["ok"])
        check("python has code", len(py.get("code", "")) > 0)
        check("python compile_check", py.get("compile_check", False))
        check("python lines > 0", py.get("lines", 0) > 0)

        js_raw = await tool_nous_codegen(source=source, target="js")
        js = json.loads(js_raw)
        check("js codegen ok", js["ok"])
        check("js has code", len(js.get("code", "")) > 0)
        check("js target", js.get("target") == "js")

    asyncio.run(_run())


def test_6_compiler_nous_parses() -> None:
    print("\n═══ Test 6: compiler.nous Parses ═══")
    from parser import parse_nous_file
    from validator import validate_program
    p = parse_nous_file("compiler.nous")
    check("world is NousCompiler", p.world.name == "NousCompiler")
    check("3 souls", len(p.souls) == 3)
    check("soul names", [s.name for s in p.souls] == ["Reader", "Analyzer", "Emitter"])
    check("3 messages", len(p.messages) == 3)
    check("msg names", sorted(m.name for m in p.messages) == ["AnalysisResult", "CompileResult", "SourceBundle"])
    check("has nervous_system", p.nervous_system is not None)
    check("2 routes", len(p.nervous_system.routes) == 2)

    vresult = validate_program(p)
    check("validation PASS", vresult.ok, f"{len(vresult.errors)} errors")


def test_7_compiler_nous_codegen() -> None:
    print("\n═══ Test 7: compiler.nous CodeGen ═══")
    from parser import parse_nous_file
    from codegen import generate_python
    import py_compile
    import tempfile
    import os
    p = parse_nous_file("compiler.nous")
    code = generate_python(p)
    check("python code generated", len(code) > 0)
    check("has Soul_Reader", "Soul_Reader" in code)
    check("has Soul_Analyzer", "Soul_Analyzer" in code)
    check("has Soul_Emitter", "Soul_Emitter" in code)
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        check("py_compile PASS", True)
    except py_compile.PyCompileError as e:
        check("py_compile PASS", False, str(e))
    finally:
        os.unlink(tmp)


def test_8_self_compile_pipeline() -> None:
    print("\n═══ Test 8: Self-Compile Pipeline ═══")
    from self_compiler import run_self_compile

    async def _run() -> None:
        result = await run_self_compile(
            source_files=["gate_alpha.nous"],
            target="python",
            output_dir="/tmp/nous_selfcompile",
        )
        check("pipeline ok", result.get("ok", False), result.get("error", ""))
        check("has files", len(result.get("files", [])) > 0)
        if result.get("files"):
            f = result["files"][0]
            check("file compiled", f.get("ok", False), f.get("error", ""))
            if f.get("ok"):
                check("output exists", Path(f["output_path"]).exists())
                check("code lines > 0", f.get("code_lines", 0) > 0)
                check("compile_check pass", f.get("compile_check", False))

    asyncio.run(_run())


def test_9_self_compile_js_target() -> None:
    print("\n═══ Test 9: Self-Compile JS Target ═══")
    from self_compiler import run_self_compile

    async def _run() -> None:
        result = await run_self_compile(
            source_files=["gate_alpha.nous"],
            target="js",
            output_dir="/tmp/nous_selfcompile_js",
        )
        check("js pipeline ok", result.get("ok", False), result.get("error", ""))
        if result.get("files"):
            f = result["files"][0]
            check("js file compiled", f.get("ok", False), f.get("error", ""))
            if f.get("ok"):
                out = Path(f["output_path"])
                check("js output exists", out.exists())
                check("has .mjs extension", out.suffix == ".mjs")

    asyncio.run(_run())


def test_10_self_compile_itself() -> None:
    print("\n═══ Test 10: Compiler Compiles Itself ═══")
    from self_compiler import run_self_compile

    async def _run() -> None:
        result = await run_self_compile(
            source_files=["compiler.nous"],
            target="python",
            output_dir="/tmp/nous_bootstrap",
        )
        check("bootstrap ok", result.get("ok", False), result.get("error", ""))
        if result.get("files"):
            f = result["files"][0]
            check("compiler compiled itself", f.get("ok", False), f.get("error", ""))
            if f.get("ok"):
                out = Path(f["output_path"])
                check("bootstrap output exists", out.exists())
                check("has Soul_Reader in output", "Soul_Reader" in out.read_text())
                check("has Soul_Analyzer in output", "Soul_Analyzer" in out.read_text())
                check("has Soul_Emitter in output", "Soul_Emitter" in out.read_text())

    asyncio.run(_run())


if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  NOUS P28 — Self-Hosting Compiler Tests")
    print("═══════════════════════════════════════════")
    test_1_compiler_senses_registration()
    test_2_file_read_sense()
    test_3_nous_parse_sense()
    test_4_nous_validate_sense()
    test_5_nous_codegen_sense()
    test_6_compiler_nous_parses()
    test_7_compiler_nous_codegen()
    test_8_self_compile_pipeline()
    test_9_self_compile_js_target()
    test_10_self_compile_itself()
    print(f"\n{'═' * 45}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed")
    if FAIL == 0:
        print("  Status: ALL PASS ✓")
    else:
        print(f"  Status: {FAIL} FAILED ✗")
    print(f"{'═' * 45}")
    sys.exit(0 if FAIL == 0 else 1)
