"""
NOUS Plugin System — Εργαλεία (Ergaleia)
==========================================
Custom tool registration, auto-discovery, signature validation.
Verifies sense calls against registered tool signatures at compile time.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Callable


@dataclass
class ToolParam:
    name: str
    type: str
    required: bool = True
    default: Optional[Any] = None

    def __str__(self) -> str:
        suffix = "" if self.required else f" = {self.default}"
        return f"{self.name}: {self.type}{suffix}"


@dataclass
class ToolSignature:
    name: str
    params: list[ToolParam] = field(default_factory=list)
    returns: str = "any"
    description: str = ""
    source: str = ""
    callable: Optional[Callable] = None

    def __str__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"{self.name}({params_str}) -> {self.returns}"


@dataclass
class PluginError:
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        prefix = f"[PLUGIN] {self.code}"
        if self.location:
            prefix += f" @ {self.location}"
        return f"{prefix}: {self.message}"


@dataclass
class PluginValidationResult:
    errors: list[PluginError] = field(default_factory=list)
    warnings: list[PluginError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, code: str, message: str, location: str = "") -> None:
        self.errors.append(PluginError(code, message, location))

    def warn(self, code: str, message: str, location: str = "") -> None:
        self.warnings.append(PluginError(code, message, location))


TOOLS_DIR = Path.home() / ".nous" / "tools"

TYPE_MAP: dict[str, str] = {
    "str": "string",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "list": "[any]",
    "dict": "{string:any}",
    "None": "none",
    "Any": "any",
}


def _python_type_to_nous(type_hint: Any) -> str:
    if type_hint is None or type_hint is inspect.Parameter.empty:
        return "any"
    name = getattr(type_hint, "__name__", str(type_hint))
    return TYPE_MAP.get(name, "any")


class PluginRegistry:
    """Central registry for all tools available to sense calls."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSignature] = {}

    def register(self, sig: ToolSignature) -> None:
        self._tools[sig.name] = sig

    def get(self, name: str) -> Optional[ToolSignature]:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def all_tools(self) -> dict[str, ToolSignature]:
        return dict(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def register_from_toml(self, toml_path: Path) -> list[str]:
        if not toml_path.exists():
            return []
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        tools_section = data.get("tools", {})
        registered: list[str] = []
        for tool_name, tool_def in tools_section.items():
            params: list[ToolParam] = []
            for param_def in tool_def.get("params", []):
                if isinstance(param_def, dict):
                    params.append(ToolParam(
                        name=param_def.get("name", ""),
                        type=param_def.get("type", "any"),
                        required=param_def.get("required", True),
                        default=param_def.get("default"),
                    ))
                elif isinstance(param_def, str):
                    parts = param_def.split(":")
                    pname = parts[0].strip()
                    ptype = parts[1].strip() if len(parts) > 1 else "any"
                    params.append(ToolParam(name=pname, type=ptype))
            sig = ToolSignature(
                name=tool_name,
                params=params,
                returns=tool_def.get("returns", "any"),
                description=tool_def.get("description", ""),
                source=str(toml_path),
            )
            self.register(sig)
            registered.append(tool_name)
        return registered

    def register_from_python(self, module_path: Path) -> list[str]:
        if not module_path.exists():
            return []
        registered: list[str] = []
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            return []
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            return []
        for name, obj in inspect.getmembers(module):
            if not inspect.isfunction(obj):
                continue
            if name.startswith("_"):
                continue
            if not getattr(obj, "_nous_tool", False) and not name.startswith("tool_"):
                continue
            sig_params: list[ToolParam] = []
            py_sig = inspect.signature(obj)
            for pname, param in py_sig.parameters.items():
                if pname in ("self", "cls"):
                    continue
                sig_params.append(ToolParam(
                    name=pname,
                    type=_python_type_to_nous(param.annotation),
                    required=param.default is inspect.Parameter.empty,
                    default=param.default if param.default is not inspect.Parameter.empty else None,
                ))
            tool_name = name.removeprefix("tool_") if name.startswith("tool_") else name
            ret_type = _python_type_to_nous(py_sig.return_annotation)
            sig = ToolSignature(
                name=tool_name,
                params=sig_params,
                returns=ret_type,
                description=obj.__doc__ or "",
                source=str(module_path),
                callable=obj,
            )
            self.register(sig)
            registered.append(tool_name)
        return registered

    def discover_tools_dir(self, tools_dir: Optional[Path] = None) -> list[str]:
        d = tools_dir or TOOLS_DIR
        if not d.exists():
            return []
        registered: list[str] = []
        for item in sorted(d.iterdir()):
            if item.suffix == ".py":
                registered.extend(self.register_from_python(item))
            elif item.is_dir():
                toml = item / "nous.toml"
                if toml.exists():
                    registered.extend(self.register_from_toml(toml))
                init = item / "__init__.py"
                if init.exists():
                    registered.extend(self.register_from_python(init))
        return registered


def validate_sense_calls(program: Any, registry: PluginRegistry) -> PluginValidationResult:
    from ast_nodes import SoulNode, LetNode, SenseCallNode
    result = PluginValidationResult()
    all_senses: set[str] = set()
    for soul in program.souls:
        all_senses.update(soul.senses)
        if soul.instinct is None:
            continue
        _walk_stmts_for_sense(soul.instinct.statements, soul.name, registry, result)
    for sense_name in all_senses:
        if not registry.has(sense_name):
            result.warn("PL001", f"sense '{sense_name}' declared but no plugin registered", "senses")
    return result


def _walk_stmts_for_sense(stmts: list, soul_name: str, registry: PluginRegistry, result: PluginValidationResult) -> None:
    from ast_nodes import LetNode, SenseCallNode, IfNode, ForNode
    for stmt in stmts:
        if isinstance(stmt, SenseCallNode):
            _check_sense_call(stmt.tool_name, stmt.args, soul_name, registry, result)
        elif isinstance(stmt, LetNode):
            if isinstance(stmt.value, dict) and stmt.value.get("kind") == "sense_call":
                tool = stmt.value.get("tool", "")
                args = stmt.value.get("args", {})
                _check_sense_call(tool, args, soul_name, registry, result)
        elif isinstance(stmt, IfNode):
            _walk_stmts_for_sense(stmt.then_body, soul_name, registry, result)
            _walk_stmts_for_sense(stmt.else_body, soul_name, registry, result)
        elif isinstance(stmt, ForNode):
            _walk_stmts_for_sense(stmt.body, soul_name, registry, result)


def _check_sense_call(tool_name: str, args: Any, soul_name: str, registry: PluginRegistry, result: PluginValidationResult) -> None:
    loc = f"soul {soul_name} > instinct"
    sig = registry.get(tool_name)
    if sig is None:
        return
    if not isinstance(args, dict):
        return
    provided_names: set[str] = set()
    positional_count = 0
    for k in args:
        if k.startswith("_pos_"):
            positional_count += 1
        else:
            provided_names.add(k)
    for param in sig.params:
        if param.required and param.name not in provided_names and positional_count == 0:
            result.error(
                "PL002",
                f"sense {tool_name}() missing required param: {param.name}",
                loc,
            )
    for name in provided_names:
        if not any(p.name == name for p in sig.params):
            result.warn(
                "PL003",
                f"sense {tool_name}() unknown param: {name}",
                loc,
            )


def build_registry(project_toml: Optional[Path] = None, tools_dir: Optional[Path] = None) -> PluginRegistry:
    registry = PluginRegistry()
    if project_toml and project_toml.exists():
        registry.register_from_toml(project_toml)
    registry.discover_tools_dir(tools_dir)
    return registry


def cmd_plugins(args: list[str]) -> int:
    if not args:
        args = ["list"]
    subcmd = args[0]
    if subcmd == "list":
        registry = build_registry(
            project_toml=Path("nous.toml"),
            tools_dir=TOOLS_DIR,
        )
        tools = registry.all_tools()
        if not tools:
            print("No plugins registered.")
            print(f"  Add [tools] to nous.toml or place .py files in {TOOLS_DIR}")
            return 0
        print(f"Registered tools ({len(tools)}):")
        for name, sig in sorted(tools.items()):
            print(f"  {sig}")
            if sig.description:
                desc = sig.description.split("\n")[0].strip()
                print(f"    {desc}")
            if sig.source:
                print(f"    source: {sig.source}")
        return 0
    elif subcmd == "check":
        if len(args) < 2:
            print("Usage: nous plugins check <file.nous>")
            return 1
        from parser import parse_nous_file
        from validator import validate_program
        source = Path(args[1])
        if not source.exists():
            print(f"Error: file not found: {source}")
            return 1
        program = parse_nous_file(source)
        vr = validate_program(program)
        if not vr.ok:
            print("Validation failed")
            return 1
        toml_path = source.parent / "nous.toml"
        registry = build_registry(project_toml=toml_path, tools_dir=TOOLS_DIR)
        result = validate_sense_calls(program, registry)
        for e in result.errors:
            print(f"  {e}")
        for w in result.warnings:
            print(f"  {w}")
        status = "PASS" if result.ok else "FAIL"
        print(f"\nPlugin check {status}: {len(result.errors)} errors, {len(result.warnings)} warnings")
        return 0 if result.ok else 1
    else:
        print(f"Unknown subcommand: {subcmd}")
        return 1
