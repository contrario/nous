"""
NOUS Type Checker v2 — Τύπος (Typos)
======================================
Full type inference across soul instinct blocks.
Tracks message field types through listen/speak.
Catches mismatches at compile time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ast_nodes import (
    NousProgram, SoulNode, MessageNode, MessageFieldNode,
    LetNode, RememberNode, SpeakNode, GuardNode, SenseCallNode,
    SleepNode, IfNode, ForNode, FieldDeclNode,
)


class NousType:
    """Base type in the NOUS type system."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NousType):
            return False
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return self.name

    def is_numeric(self) -> bool:
        return self.name in ("int", "float", "currency")

    def is_assignable_from(self, other: NousType) -> bool:
        if self == other:
            return True
        if self == T_ANY or other == T_ANY:
            return True
        if self == T_UNKNOWN or other == T_UNKNOWN:
            return True
        if isinstance(self, OptionalType):
            if other == T_NONE:
                return True
            return self.inner.is_assignable_from(other)
        if isinstance(other, OptionalType):
            return self.is_assignable_from(other.inner)
        if self.name == "float" and other.name == "int":
            return True
        if self.name == "float" and other.name == "currency":
            return True
        if self.name == "string" and other.name == "SoulRef":
            return True
        return False


class ListType(NousType):
    def __init__(self, elem: NousType) -> None:
        super().__init__(f"[{elem.name}]")
        self.elem = elem


class MapType(NousType):
    def __init__(self, key: NousType, val: NousType) -> None:
        super().__init__(f"{{{key.name}:{val.name}}}")
        self.key = key
        self.val = val


class OptionalType(NousType):
    def __init__(self, inner: NousType) -> None:
        super().__init__(f"{inner.name}?")
        self.inner = inner


class MessageType(NousType):
    def __init__(self, name: str, fields: dict[str, NousType]) -> None:
        super().__init__(name)
        self.fields = fields


T_INT = NousType("int")
T_FLOAT = NousType("float")
T_STRING = NousType("string")
T_BOOL = NousType("bool")
T_NONE = NousType("none")
T_ANY = NousType("any")
T_UNKNOWN = NousType("unknown")
T_CURRENCY = NousType("currency")
T_DURATION = NousType("duration")
T_TIMESTAMP = NousType("timestamp")
T_SOULREF = NousType("SoulRef")
T_TOOLREF = NousType("ToolRef")

PRIMITIVE_MAP: dict[str, NousType] = {
    "int": T_INT,
    "float": T_FLOAT,
    "string": T_STRING,
    "bool": T_BOOL,
    "timestamp": T_TIMESTAMP,
    "duration": T_DURATION,
    "currency": T_CURRENCY,
    "SoulRef": T_SOULREF,
    "ToolRef": T_TOOLREF,
}


def parse_type_expr(type_str: str) -> NousType:
    if type_str.endswith("?"):
        return OptionalType(parse_type_expr(type_str[:-1]))
    if type_str.startswith("[") and type_str.endswith("]"):
        return ListType(parse_type_expr(type_str[1:-1]))
    if type_str.startswith("{") and type_str.endswith("}"):
        inner = type_str[1:-1]
        colon_idx = inner.index(":")
        return MapType(parse_type_expr(inner[:colon_idx].strip()), parse_type_expr(inner[colon_idx + 1:].strip()))
    if type_str in PRIMITIVE_MAP:
        return PRIMITIVE_MAP[type_str]
    return NousType(type_str)


@dataclass
class TypeError:
    severity: str
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        prefix = f"[{self.severity}] {self.code}"
        if self.location:
            prefix += f" @ {self.location}"
        return f"{prefix}: {self.message}"


@dataclass
class TypeCheckResult:
    errors: list[TypeError] = field(default_factory=list)
    warnings: list[TypeError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, code: str, message: str, location: str = "") -> None:
        self.errors.append(TypeError("ERROR", code, message, location))

    def warn(self, code: str, message: str, location: str = "") -> None:
        self.warnings.append(TypeError("WARN", code, message, location))

    def summary(self) -> str:
        lines = []
        for e in self.errors:
            lines.append(str(e))
        for w in self.warnings:
            lines.append(str(w))
        status = "PASS" if self.ok else "FAIL"
        lines.append(f"\nType check {status}: {len(self.errors)} errors, {len(self.warnings)} warnings")
        return "\n".join(lines)


class TypeEnv:
    """Type environment for a scope (soul instinct block)."""

    def __init__(self, parent: Optional[TypeEnv] = None) -> None:
        self._bindings: dict[str, NousType] = {}
        self._parent = parent

    def bind(self, name: str, typ: NousType) -> None:
        self._bindings[name] = typ

    def lookup(self, name: str) -> Optional[NousType]:
        if name in self._bindings:
            return self._bindings[name]
        if self._parent:
            return self._parent.lookup(name)
        return None

    def child(self) -> TypeEnv:
        return TypeEnv(parent=self)


class NousTypeChecker:
    """Type checks a validated NousProgram."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.result = TypeCheckResult()
        self.message_types: dict[str, MessageType] = {}
        self.soul_memory_types: dict[str, dict[str, NousType]] = {}

    def check(self) -> TypeCheckResult:
        self._register_messages()
        self._register_soul_memories()
        for soul in self.program.souls:
            self._check_soul(soul)
        return self.result

    def _register_messages(self) -> None:
        for msg in self.program.messages:
            fields: dict[str, NousType] = {}
            for f in msg.fields:
                fields[f.name] = parse_type_expr(f.type_expr)
            self.message_types[msg.name] = MessageType(msg.name, fields)

    def _register_soul_memories(self) -> None:
        for soul in self.program.souls:
            mem_types: dict[str, NousType] = {}
            if soul.memory:
                for f in soul.memory.fields:
                    mem_types[f.name] = parse_type_expr(f.type_expr)
            self.soul_memory_types[soul.name] = mem_types

    def _check_soul(self, soul: SoulNode) -> None:
        if soul.instinct is None:
            return
        env = TypeEnv()
        mem_types = self.soul_memory_types.get(soul.name, {})
        for name, typ in mem_types.items():
            env.bind(name, typ)
        loc_prefix = f"soul {soul.name} > instinct"
        for stmt in soul.instinct.statements:
            self._check_statement(stmt, env, soul.name, loc_prefix)

    def _check_statement(self, stmt: Any, env: TypeEnv, soul_name: str, loc: str) -> None:
        if isinstance(stmt, LetNode):
            self._check_let(stmt, env, soul_name, loc)
        elif isinstance(stmt, RememberNode):
            self._check_remember(stmt, env, soul_name, loc)
        elif isinstance(stmt, SpeakNode):
            self._check_speak(stmt, env, soul_name, loc)
        elif isinstance(stmt, GuardNode):
            self._check_guard(stmt, env, soul_name, loc)
        elif isinstance(stmt, IfNode):
            self._check_if(stmt, env, soul_name, loc)
        elif isinstance(stmt, ForNode):
            self._check_for(stmt, env, soul_name, loc)

    def _check_let(self, stmt: LetNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        inferred = self._infer_expr(stmt.value, env, soul_name, loc)
        env.bind(stmt.name, inferred)

    def _check_remember(self, stmt: RememberNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        mem_types = self.soul_memory_types.get(soul_name, {})
        if stmt.name not in mem_types:
            self.result.error("TC001", f"remember references undefined memory field: {stmt.name}", loc)
            return
        expected = mem_types[stmt.name]
        actual = self._infer_expr(stmt.value, env, soul_name, loc)
        if stmt.op == "+=":
            if not expected.is_numeric() and not isinstance(expected, ListType):
                self.result.error(
                    "TC002",
                    f"remember += on non-numeric/non-list field '{stmt.name}' (type: {expected})",
                    loc,
                )
        else:
            if not expected.is_assignable_from(actual) and actual != T_UNKNOWN:
                self.result.warn(
                    "TC003",
                    f"type mismatch: memory '{stmt.name}' expects {expected}, got {actual}",
                    loc,
                )

    def _check_speak(self, stmt: SpeakNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        msg_type = self.message_types.get(stmt.message_type)
        if msg_type is None:
            return
        required_fields: set[str] = set()
        for fname, ftype in msg_type.fields.items():
            if not isinstance(ftype, OptionalType):
                msg_node = next((m for m in self.program.messages if m.name == stmt.message_type), None)
                if msg_node:
                    field_node = next((f for f in msg_node.fields if f.name == fname), None)
                    if field_node and field_node.default is None:
                        required_fields.add(fname)
        provided_fields = set(stmt.args.keys()) if isinstance(stmt.args, dict) else set()
        missing = required_fields - provided_fields
        if missing:
            self.result.error(
                "TC004",
                f"speak {stmt.message_type} missing required fields: {', '.join(sorted(missing))}",
                loc,
            )
        for field_name, field_val in (stmt.args.items() if isinstance(stmt.args, dict) else []):
            if field_name not in msg_type.fields:
                self.result.error(
                    "TC005",
                    f"speak {stmt.message_type} provides unknown field: {field_name}",
                    loc,
                )
                continue
            expected_type = msg_type.fields[field_name]
            actual_type = self._infer_expr(field_val, env, soul_name, loc)
            if not expected_type.is_assignable_from(actual_type) and actual_type != T_UNKNOWN:
                self.result.warn(
                    "TC006",
                    f"speak {stmt.message_type}.{field_name}: expected {expected_type}, got {actual_type}",
                    loc,
                )

    def _check_guard(self, stmt: GuardNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        cond_type = self._infer_expr(stmt.condition, env, soul_name, loc)
        if cond_type != T_BOOL and cond_type != T_UNKNOWN and cond_type != T_ANY:
            self.result.warn("TC007", f"guard condition has type {cond_type}, expected bool", loc)

    def _check_if(self, stmt: IfNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        cond_type = self._infer_expr(stmt.condition, env, soul_name, loc)
        if cond_type != T_BOOL and cond_type != T_UNKNOWN and cond_type != T_ANY:
            self.result.warn("TC008", f"if condition has type {cond_type}, expected bool", loc)
        then_env = env.child()
        for s in stmt.then_body:
            self._check_statement(s, then_env, soul_name, loc)
        if stmt.else_body:
            else_env = env.child()
            for s in stmt.else_body:
                self._check_statement(s, else_env, soul_name, loc)

    def _check_for(self, stmt: ForNode, env: TypeEnv, soul_name: str, loc: str) -> None:
        iter_type = self._infer_expr(stmt.iterable, env, soul_name, loc)
        body_env = env.child()
        if isinstance(iter_type, ListType):
            body_env.bind(stmt.var_name, iter_type.elem)
        else:
            body_env.bind(stmt.var_name, T_ANY)
        for s in stmt.body:
            self._check_statement(s, body_env, soul_name, loc)

    def _infer_expr(self, expr: Any, env: TypeEnv, soul_name: str, loc: str) -> NousType:
        if expr is None:
            return T_NONE
        if isinstance(expr, bool):
            return T_BOOL
        if isinstance(expr, int):
            return T_INT
        if isinstance(expr, float):
            return T_FLOAT
        if isinstance(expr, str):
            if expr == "self":
                return T_SOULREF
            if expr == "now()":
                return T_TIMESTAMP
            looked = env.lookup(expr)
            if looked is not None:
                return looked
            mem_types = self.soul_memory_types.get(soul_name, {})
            if expr in mem_types:
                return mem_types[expr]
            if expr.replace("_", "").replace(".", "").isalnum() and len(expr) > 0 and expr[0].isalpha():
                return T_UNKNOWN
            return T_STRING
        if isinstance(expr, list):
            if not expr:
                return ListType(T_ANY)
            elem_type = self._infer_expr(expr[0], env, soul_name, loc)
            return ListType(elem_type)
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                return self._infer_binop(expr, env, soul_name, loc)
            elif kind == "not":
                return T_BOOL
            elif kind == "neg":
                return self._infer_expr(expr.get("operand"), env, soul_name, loc)
            elif kind == "attr":
                return self._infer_attr(expr, env, soul_name, loc)
            elif kind == "method_call":
                return self._infer_method_call(expr, env, soul_name, loc)
            elif kind == "func_call":
                return self._infer_func_call(expr, env, soul_name, loc)
            elif kind == "message_construct":
                msg_name = expr.get("type", "")
                if msg_name in self.message_types:
                    return self.message_types[msg_name]
                return T_UNKNOWN
            elif kind == "listen":
                msg_type_name = expr.get("type", "")
                if msg_type_name in self.message_types:
                    return self.message_types[msg_type_name]
                return T_UNKNOWN
            elif kind == "sense_call":
                return T_ANY
            elif kind == "world_ref":
                return T_ANY
            elif kind == "soul_field":
                target_soul = expr.get("soul", "")
                field_name = expr.get("field", "")
                target_mem = self.soul_memory_types.get(target_soul, {})
                if field_name in target_mem:
                    return target_mem[field_name]
                return T_UNKNOWN
            elif kind == "inline_if":
                then_type = self._infer_expr(expr.get("then"), env, soul_name, loc)
                else_type = self._infer_expr(expr.get("else"), env, soul_name, loc)
                if then_type == else_type:
                    return then_type
                if then_type.is_numeric() and else_type.is_numeric():
                    return T_FLOAT
                return T_ANY
            if "currency" in expr:
                return T_CURRENCY
        return T_UNKNOWN

    def _infer_binop(self, expr: dict, env: TypeEnv, soul_name: str, loc: str) -> NousType:
        op = expr.get("op", "")
        left = self._infer_expr(expr.get("left"), env, soul_name, loc)
        right = self._infer_expr(expr.get("right"), env, soul_name, loc)
        if op in ("==", "!=", ">", "<", ">=", "<="):
            return T_BOOL
        if op in ("&&", "||"):
            return T_BOOL
        if op in ("+", "-", "*", "/", "%"):
            if left == T_INT and right == T_INT:
                if op == "/":
                    return T_FLOAT
                return T_INT
            if left.is_numeric() and right.is_numeric():
                return T_FLOAT
            if op == "+" and (left == T_STRING or right == T_STRING):
                return T_STRING
            return T_ANY
        return T_UNKNOWN

    def _infer_attr(self, expr: dict, env: TypeEnv, soul_name: str, loc: str) -> NousType:
        obj_type = self._infer_expr(expr.get("obj"), env, soul_name, loc)
        attr_name = expr.get("attr", "")
        if isinstance(obj_type, MessageType):
            if attr_name in obj_type.fields:
                return obj_type.fields[attr_name]
            self.result.warn(
                "TC009",
                f"field '{attr_name}' not found on message type {obj_type.name}",
                loc,
            )
            return T_UNKNOWN
        return T_UNKNOWN

    def _infer_method_call(self, expr: dict, env: TypeEnv, soul_name: str, loc: str) -> NousType:
        obj_type = self._infer_expr(expr.get("obj"), env, soul_name, loc)
        method = expr.get("method", "")
        if isinstance(obj_type, ListType):
            if method == "where" or method == "filter":
                return obj_type
            if method == "map":
                return ListType(T_ANY)
            if method == "len" or method == "count":
                return T_INT
            if method == "first":
                return obj_type.elem
            if method == "last":
                return obj_type.elem
            if method == "append" or method == "push":
                return T_NONE
            if method == "sort":
                return obj_type
        if obj_type == T_STRING:
            if method in ("upper", "lower", "strip", "trim"):
                return T_STRING
            if method == "len":
                return T_INT
            if method == "split":
                return ListType(T_STRING)
            if method == "contains":
                return T_BOOL
        return T_UNKNOWN

    def _infer_func_call(self, expr: dict, env: TypeEnv, soul_name: str, loc: str) -> NousType:
        func = expr.get("func", "")
        if isinstance(func, str):
            if func in self.message_types:
                return self.message_types[func]
            if func == "len":
                return T_INT
            if func == "str":
                return T_STRING
            if func == "int":
                return T_INT
            if func == "float":
                return T_FLOAT
            if func == "abs":
                return T_FLOAT
            if func == "max" or func == "min":
                return T_FLOAT
        return T_UNKNOWN


def typecheck_program(program: NousProgram) -> TypeCheckResult:
    """Type check a validated NousProgram."""
    checker = NousTypeChecker(program)
    return checker.check()
