"""
NOUS Test Runner — Δοκιμή (Dokimi)
====================================
Parses .nous files, extracts test blocks, mocks tools, runs assertions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, TestNode, TestAssertNode, TestMockNode, TestRunNode,
    SoulNode,
)
from parser import parse_nous_file
from validator import validate_program
from codegen import generate_python

log = logging.getLogger("nous.test")


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float = 0.0
    assertions: int = 0
    failures: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class TestSuiteResult:
    file: str
    results: list[TestResult] = field(default_factory=list)
    parse_ok: bool = True
    validate_ok: bool = True
    compile_ok: bool = True
    parse_error: str = ""
    validate_errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def ok(self) -> bool:
        return self.parse_ok and self.validate_ok and self.compile_ok and self.failed == 0


class MockToolRegistry:
    def __init__(self) -> None:
        self._mocks: dict[str, Any] = {}

    def register(self, tool_name: str, returns: Any) -> None:
        self._mocks[tool_name] = returns

    def get(self, tool_name: str) -> Any:
        return self._mocks.get(tool_name)

    def has(self, tool_name: str) -> bool:
        return tool_name in self._mocks

    def clear(self) -> None:
        self._mocks.clear()


class SoulState:
    def __init__(self, soul: SoulNode) -> None:
        self.soul = soul
        self.name = soul.name
        self.memory: dict[str, Any] = {}
        self.spoke: list[str] = []
        self.cycle_count = 0

        if soul.memory:
            for f in soul.memory.fields:
                self.memory[f.name] = f.default

    def get_field(self, field_name: str) -> Any:
        return self.memory.get(field_name)


class TestExecutor:
    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.mocks = MockToolRegistry()
        self.soul_states: dict[str, SoulState] = {}
        self._spoke_messages: list[str] = []

        for soul in program.souls:
            self.soul_states[soul.name] = SoulState(soul)

    def run_test(self, test: TestNode) -> TestResult:
        t0 = time.perf_counter()
        result = TestResult(name=test.description, passed=True)
        self.mocks.clear()
        self._spoke_messages.clear()

        for soul_name, state in self.soul_states.items():
            soul = next((s for s in self.program.souls if s.name == soul_name), None)
            if soul:
                self.soul_states[soul_name] = SoulState(soul)

        try:
            for stmt in test.stmts:
                if isinstance(stmt, TestMockNode):
                    self.mocks.register(stmt.tool_name, stmt.returns)

                elif isinstance(stmt, TestRunNode):
                    self._simulate_soul(stmt.soul_name)

                elif isinstance(stmt, TestAssertNode):
                    result.assertions += 1
                    ok, msg = self._check_assert(stmt)
                    if not ok:
                        result.passed = False
                        result.failures.append(msg)

        except Exception as e:
            result.passed = False
            result.error = str(e)

        result.duration = time.perf_counter() - t0
        return result

    def _simulate_soul(self, soul_name: str) -> None:
        state = self.soul_states.get(soul_name)
        if not state:
            raise ValueError(f"Unknown soul: {soul_name}")

        soul = state.soul
        if not soul.instinct:
            return

        from ast_nodes import (
            LetNode, RememberNode, SpeakNode, SenseCallNode,
            IfNode, ForNode, GuardNode,
        )

        for stmt in soul.instinct.statements:
            self._exec_stmt(stmt, state)

        state.cycle_count += 1

    def _exec_stmt(self, stmt: Any, state: SoulState) -> None:
        from ast_nodes import (
            LetNode, RememberNode, SpeakNode, SenseCallNode,
            IfNode, ForNode, GuardNode,
        )

        if isinstance(stmt, LetNode):
            if isinstance(stmt.value, dict):
                kind = stmt.value.get("kind", "")
                if kind == "sense_call":
                    tool = stmt.value.get("tool", "")
                    if self.mocks.has(tool):
                        state.memory[stmt.name] = self.mocks.get(tool)
                    else:
                        state.memory[stmt.name] = None
                elif kind == "listen":
                    state.memory[stmt.name] = None
                else:
                    state.memory[stmt.name] = self._eval_expr(stmt.value, state)
            else:
                state.memory[stmt.name] = self._eval_expr(stmt.value, state)

        elif isinstance(stmt, RememberNode):
            val = self._eval_expr(stmt.value, state)
            if stmt.op == "+=":
                old = state.memory.get(stmt.name, 0)
                state.memory[stmt.name] = old + val if isinstance(old, (int, float)) else val
            else:
                state.memory[stmt.name] = val

        elif isinstance(stmt, SpeakNode):
            state.spoke.append(stmt.message_type)
            self._spoke_messages.append(stmt.message_type)

        elif isinstance(stmt, SenseCallNode):
            if self.mocks.has(stmt.tool_name):
                result = self.mocks.get(stmt.tool_name)
                if stmt.bind_name:
                    state.memory[stmt.bind_name] = result

        elif isinstance(stmt, IfNode):
            cond = self._eval_expr(stmt.condition, state)
            if cond:
                for s in stmt.then_body:
                    self._exec_stmt(s, state)
            else:
                for s in stmt.else_body:
                    self._exec_stmt(s, state)

        elif isinstance(stmt, ForNode):
            iterable = self._eval_expr(stmt.iterable, state)
            if isinstance(iterable, list):
                for item in iterable:
                    state.memory[stmt.var_name] = item
                    for s in stmt.body:
                        self._exec_stmt(s, state)

    def _eval_expr(self, expr: Any, state: SoulState) -> Any:
        if expr is None:
            return None
        if isinstance(expr, (int, float, bool)):
            return expr
        if isinstance(expr, str):
            if expr == "self":
                return state.name
            if expr == "now()":
                return time.time()
            if expr in state.memory:
                return state.memory[expr]
            return expr
        if isinstance(expr, list):
            return [self._eval_expr(e, state) for e in expr]
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                left = self._eval_expr(expr["left"], state)
                right = self._eval_expr(expr["right"], state)
                op = expr["op"]
                if op == "+":
                    return (left or 0) + (right or 0)
                elif op == "-":
                    return (left or 0) - (right or 0)
                elif op == "*":
                    return (left or 0) * (right or 0)
                elif op == "<":
                    return (left or 0) < (right or 0)
                elif op == ">":
                    return (left or 0) > (right or 0)
                elif op == "==":
                    return left == right
                elif op == "!=":
                    return left != right
                elif op == ">=":
                    return (left or 0) >= (right or 0)
                elif op == "<=":
                    return (left or 0) <= (right or 0)
                elif op == "&&":
                    return left and right
                elif op == "||":
                    return left or right
            elif kind == "attr":
                obj = self._eval_expr(expr["obj"], state)
                attr = expr["attr"]
                if isinstance(obj, dict):
                    return obj.get(attr)
                if hasattr(obj, attr):
                    return getattr(obj, attr)
                return None
            elif kind == "not":
                return not self._eval_expr(expr["operand"], state)
            elif kind == "neg":
                return -(self._eval_expr(expr["operand"], state) or 0)
            elif kind == "inline_if":
                cond = self._eval_expr(expr["condition"], state)
                return self._eval_expr(expr["then"], state) if cond else self._eval_expr(expr["else"], state)
            elif kind == "message_construct":
                return {"_type": expr.get("type", ""), **{k: self._eval_expr(v, state) for k, v in expr.get("args", {}).items()}}
            elif kind == "sense_call":
                tool = expr.get("tool", "")
                if self.mocks.has(tool):
                    return self.mocks.get(tool)
                return None
        return expr

    def _check_assert(self, assertion: TestAssertNode) -> tuple[bool, str]:
        if assertion.kind == "expr":
            val = self._eval_expr_global(assertion.expr)
            if val:
                return True, ""
            return False, f"assert failed: {assertion.expr}"

        elif assertion.kind == "field":
            soul_name = assertion.soul
            field_name = assertion.field
            state = self.soul_states.get(soul_name)
            if not state:
                return False, f"unknown soul: {soul_name}"
            actual = state.memory.get(field_name)
            expected = assertion.expected
            if isinstance(expected, str) and expected in state.memory:
                expected = state.memory[expected]
            op = assertion.op or "=="
            ok = self._compare(actual, op, expected)
            if ok:
                return True, ""
            return False, f"{soul_name}.{field_name} {op} {expected} (actual: {actual})"

        elif assertion.kind == "spoke":
            msg_type = assertion.message_type
            if msg_type in self._spoke_messages:
                return True, ""
            return False, f"expected spoke {msg_type}, but messages were: {self._spoke_messages}"

        return False, f"unknown assertion kind: {assertion.kind}"

    def _eval_expr_global(self, expr: Any) -> Any:
        dummy = SoulState(self.program.souls[0]) if self.program.souls else None
        if dummy:
            dummy.memory.update({name: s.memory for name, s in self.soul_states.items()})
            return self._eval_expr(expr, dummy)
        return None

    def _compare(self, actual: Any, op: str, expected: Any) -> bool:
        try:
            if op == "==":
                return actual == expected
            elif op == "!=":
                return actual != expected
            elif op == ">":
                return actual > expected
            elif op == "<":
                return actual < expected
            elif op == ">=":
                return actual >= expected
            elif op == "<=":
                return actual <= expected
        except TypeError:
            return False
        return False


def run_tests(source_path: str, verbose: bool = False) -> TestSuiteResult:
    path = Path(source_path)
    suite = TestSuiteResult(file=str(path))

    try:
        program = parse_nous_file(path)
    except Exception as e:
        suite.parse_ok = False
        suite.parse_error = str(e)
        return suite

    result = validate_program(program)
    if not result.ok:
        suite.validate_ok = False
        suite.validate_errors = [str(e) for e in result.errors]

    try:
        code = generate_python(program)
        import py_compile
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            py_compile.compile(tmp, doraise=True)
        finally:
            os.unlink(tmp)
    except Exception as e:
        suite.compile_ok = False

    if not program.tests:
        return suite

    executor = TestExecutor(program)
    for test in program.tests:
        test_result = executor.run_test(test)
        suite.results.append(test_result)

    return suite


def print_results(suite: TestSuiteResult) -> None:
    C_RESET = "\033[0m"
    C_GREEN = "\033[92m"
    C_RED = "\033[91m"
    C_YELLOW = "\033[93m"
    C_CYAN = "\033[96m"
    C_DIM = "\033[2m"
    C_BOLD = "\033[1m"

    if not sys.stdout.isatty():
        C_RESET = C_GREEN = C_RED = C_YELLOW = C_CYAN = C_DIM = C_BOLD = ""

    print(f"\n{C_BOLD}═══ NOUS Test Runner ═══{C_RESET}")
    print(f"File: {C_CYAN}{suite.file}{C_RESET}\n")

    if not suite.parse_ok:
        print(f"{C_RED}✗ Parse FAILED:{C_RESET} {suite.parse_error}")
        return

    if not suite.validate_ok:
        print(f"{C_YELLOW}⚠ Validation warnings:{C_RESET}")
        for e in suite.validate_errors:
            print(f"  {e}")
        print()

    if not suite.compile_ok:
        print(f"{C_RED}✗ Compile FAILED{C_RESET}")
        return

    if not suite.results:
        print(f"{C_DIM}No test blocks found.{C_RESET}")
        return

    for r in suite.results:
        icon = f"{C_GREEN}✓{C_RESET}" if r.passed else f"{C_RED}✗{C_RESET}"
        dur = f"{C_DIM}{r.duration*1000:.1f}ms{C_RESET}"
        print(f"  {icon} {r.name} {dur} ({r.assertions} assertions)")
        for f in r.failures:
            print(f"    {C_RED}FAIL:{C_RESET} {f}")
        if r.error:
            print(f"    {C_RED}ERROR:{C_RESET} {r.error}")

    print(f"\n{C_BOLD}Results:{C_RESET} {C_GREEN}{suite.passed} passed{C_RESET}, ", end="")
    if suite.failed:
        print(f"{C_RED}{suite.failed} failed{C_RESET}, ", end="")
    print(f"{suite.total} total")
    total_time = sum(r.duration for r in suite.results)
    print(f"{C_DIM}Time: {total_time*1000:.1f}ms{C_RESET}\n")
