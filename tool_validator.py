#!/usr/bin/env python3
"""
NOUS Tool Argument Validator
=============================
Scans tool execute() signatures and validates sense call args at compile time.
"""
from __future__ import annotations

import ast
import inspect
import importlib.util
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path("/opt/aetherlang_agents/tools")


def get_tool_signatures(tools_dir: Path = TOOLS_DIR) -> dict[str, set[str]]:
    """Extract parameter names from each tool's execute() function."""
    sigs: dict[str, set[str]] = {}
    if not tools_dir.exists():
        return sigs

    for py_file in tools_dir.glob("*.py"):
        tool_name = py_file.stem
        if tool_name.startswith("_") or tool_name == "base":
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == "execute":
                        params = set()
                        for arg in node.args.args:
                            if arg.arg not in ("self", "cls"):
                                params.add(arg.arg)
                        if node.args.kwonlyargs:
                            for arg in node.args.kwonlyargs:
                                params.add(arg.arg)
                        has_kwargs = node.args.kwarg is not None
                        has_varargs = node.args.vararg is not None
                        if has_kwargs or has_varargs:
                            sigs[tool_name] = set()
                        else:
                            sigs[tool_name] = params
                        break
        except Exception:
            continue

    return sigs


def validate_sense_args(program: Any, tools_dir: Path = TOOLS_DIR) -> list[str]:
    """Validate sense call arguments against tool signatures."""
    from ast_nodes import SenseCallNode, IfNode, ForNode

    sigs = get_tool_signatures(tools_dir)
    if not sigs:
        return []

    errors: list[str] = []

    def check_stmts(stmts: list[Any], soul_name: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, SenseCallNode):
                tool = stmt.tool_name
                if tool not in sigs:
                    continue
                expected = sigs[tool]
                if not expected:
                    continue
                if isinstance(stmt.args, dict):
                    for key in stmt.args:
                        if key.startswith("_pos_"):
                            continue
                        if key not in expected:
                            errors.append(
                                f"[WARN] T002 @ soul {soul_name}: "
                                f"sense {tool}() got unexpected argument '{key}'. "
                                f"Valid args: {', '.join(sorted(expected))}"
                            )
            elif hasattr(stmt, 'name') and hasattr(stmt, 'value'):
                val = getattr(stmt, 'value', None)
                if isinstance(val, dict) and val.get("kind") == "sense_call":
                    tool = val.get("tool", "")
                    if tool in sigs and sigs[tool]:
                        args = val.get("args", {})
                        if isinstance(args, dict):
                            for key in args:
                                if key.startswith("_pos_"):
                                    continue
                                if key not in sigs[tool]:
                                    errors.append(
                                        f"[WARN] T002 @ soul {soul_name}: "
                                        f"sense {tool}() got unexpected argument '{key}'. "
                                        f"Valid args: {', '.join(sorted(sigs[tool]))}"
                                    )
            if isinstance(stmt, IfNode):
                check_stmts(stmt.then_body, soul_name)
                check_stmts(stmt.else_body, soul_name)
            elif isinstance(stmt, ForNode):
                check_stmts(stmt.body, soul_name)

    for soul in program.souls:
        if soul.instinct and soul.instinct.statements:
            check_stmts(soul.instinct.statements, soul.name)

    return errors


if __name__ == "__main__":
    sigs = get_tool_signatures()
    print(f"Found {len(sigs)} tools with signatures:")
    for name, params in sorted(sigs.items()):
        if params:
            print(f"  {name}({', '.join(sorted(params))})")
        else:
            print(f"  {name}(*args, **kwargs)")
