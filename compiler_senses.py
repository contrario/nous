"""
NOUS Compiler Senses — Αισθήσεις Μεταγλωττιστή
==================================================
Standard tool implementations for the self-hosting compiler.
Registers: file_read, file_write, file_list, nous_parse, nous_validate,
nous_typecheck, nous_codegen, nous_codegen_js, nous_format.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("nous.compiler_senses")


async def tool_file_read(path: str = "", **kwargs: Any) -> str:
    p = Path(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}", "ok": False})
    try:
        content = p.read_text(encoding="utf-8")
        return json.dumps({
            "ok": True,
            "path": str(p.resolve()),
            "content": content,
            "lines": len(content.splitlines()),
            "size": len(content),
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_file_write(path: str = "", content: str = "", **kwargs: Any) -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return json.dumps({
            "ok": True,
            "path": str(p.resolve()),
            "lines": len(content.splitlines()),
            "size": len(content),
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_file_list(directory: str = ".", pattern: str = "*.nous", **kwargs: Any) -> str:
    try:
        d = Path(directory)
        if not d.exists():
            return json.dumps({"error": f"Directory not found: {directory}", "ok": False})
        files = sorted(str(f) for f in d.glob(pattern))
        return json.dumps({"ok": True, "files": files, "count": len(files)})
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_nous_parse(source: str = "", path: str = "", **kwargs: Any) -> str:
    try:
        if path and not source:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"File not found: {path}", "ok": False})
            source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        program = parse_nous(source)
        world_name = program.world.name if program.world else "None"
        souls = [s.name for s in program.souls]
        messages = [m.name for m in program.messages]
        imports = len(program.imports)
        has_ns = program.nervous_system is not None
        has_topo = program.topology is not None
        has_evo = program.evolution is not None
        routes = 0
        if program.nervous_system:
            routes = len(program.nervous_system.routes)
        return json.dumps({
            "ok": True,
            "world": world_name,
            "souls": souls,
            "soul_count": len(souls),
            "messages": messages,
            "message_count": len(messages),
            "imports": imports,
            "has_nervous_system": has_ns,
            "route_count": routes,
            "has_topology": has_topo,
            "has_evolution": has_evo,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False, "error_type": "parse"})


async def tool_nous_validate(source: str = "", path: str = "", **kwargs: Any) -> str:
    try:
        if path and not source:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"File not found: {path}", "ok": False})
            source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        from validator import validate_program
        program = parse_nous(source)
        result = validate_program(program)
        return json.dumps({
            "ok": result.ok,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "errors": [{"code": e.code, "message": e.message, "location": e.location} for e in result.errors],
            "warnings": [{"code": w.code, "message": w.message, "location": w.location} for w in result.warnings],
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_nous_typecheck(source: str = "", path: str = "", **kwargs: Any) -> str:
    try:
        if path and not source:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"File not found: {path}", "ok": False})
            source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        from validator import validate_program
        from typechecker import typecheck_program
        program = parse_nous(source)
        vresult = validate_program(program)
        if not vresult.ok:
            return json.dumps({
                "ok": False,
                "stage": "validation",
                "error_count": len(vresult.errors),
                "errors": [{"code": e.code, "message": e.message} for e in vresult.errors],
            })
        tresult = typecheck_program(program)
        return json.dumps({
            "ok": tresult.ok,
            "stage": "typecheck",
            "error_count": len(tresult.errors),
            "warning_count": len(tresult.warnings),
            "errors": [{"code": e.code, "message": e.message} for e in tresult.errors],
            "warnings": [{"code": w.code, "message": w.message} for w in tresult.warnings],
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_nous_codegen(source: str = "", path: str = "", target: str = "python", **kwargs: Any) -> str:
    try:
        if path and not source:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"File not found: {path}", "ok": False})
            source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        from validator import validate_program
        program = parse_nous(source)
        vresult = validate_program(program)
        if not vresult.ok:
            return json.dumps({
                "ok": False,
                "stage": "validation",
                "errors": [{"code": e.code, "message": e.message} for e in vresult.errors],
            })
        if target == "js" or target == "javascript":
            from codegen_js import generate_javascript
            code = generate_javascript(program)
        else:
            from codegen import generate_python
            code = generate_python(program)
        import py_compile
        import tempfile
        import os
        compile_ok = True
        compile_error = ""
        if target == "python":
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
                f.write(code)
                tmp = f.name
            try:
                py_compile.compile(tmp, doraise=True)
            except py_compile.PyCompileError as e:
                compile_ok = False
                compile_error = str(e)
            finally:
                os.unlink(tmp)
        return json.dumps({
            "ok": True,
            "target": target,
            "code": code,
            "lines": len(code.splitlines()),
            "size": len(code),
            "compile_check": compile_ok,
            "compile_error": compile_error,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_nous_format(source: str = "", path: str = "", **kwargs: Any) -> str:
    try:
        if path and not source:
            p = Path(path)
            if not p.exists():
                return json.dumps({"error": f"File not found: {path}", "ok": False})
            source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        from formatter import format_program
        program = parse_nous(source)
        formatted = format_program(program)
        return json.dumps({
            "ok": True,
            "formatted": formatted,
            "lines": len(formatted.splitlines()),
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


async def tool_nous_info(path: str = "", **kwargs: Any) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}", "ok": False})
        source = p.read_text(encoding="utf-8")
        from parser import parse_nous
        program = parse_nous(source)
        soul_details = []
        for soul in program.souls:
            sd = {
                "name": soul.name,
                "mind": f"{soul.mind.model} @ {soul.mind.tier.value}" if soul.mind else "none",
                "senses": soul.senses,
                "memory_fields": len(soul.memory.fields) if soul.memory else 0,
                "has_instinct": soul.instinct is not None,
                "has_heal": soul.heal is not None,
                "has_dna": soul.dna is not None,
                "gene_count": len(soul.dna.genes) if soul.dna else 0,
            }
            soul_details.append(sd)
        return json.dumps({
            "ok": True,
            "path": str(p.resolve()),
            "world": program.world.name if program.world else None,
            "heartbeat": program.world.heartbeat if program.world else None,
            "souls": soul_details,
            "messages": [m.name for m in program.messages],
            "has_topology": program.topology is not None,
            "has_evolution": program.evolution is not None,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ok": False})


COMPILER_SENSES: dict[str, Any] = {
    "file_read": tool_file_read,
    "file_write": tool_file_write,
    "file_list": tool_file_list,
    "nous_parse": tool_nous_parse,
    "nous_validate": tool_nous_validate,
    "nous_typecheck": tool_nous_typecheck,
    "nous_codegen": tool_nous_codegen,
    "nous_format": tool_nous_format,
    "nous_info": tool_nous_info,
}


def register_compiler_senses(runtime: Any) -> list[str]:
    registered = []
    for name, func in COMPILER_SENSES.items():
        runtime.register_sense(name, func)
        registered.append(name)
    log.info(f"Registered {len(registered)} compiler senses: {registered}")
    return registered
