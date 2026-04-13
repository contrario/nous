"""
NOUS Test Runner v2 — Δοκιμή (Dokimi)
========================================
Executes test blocks from .nous files.
Evaluates assertions, reports pass/fail with details.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ast_nodes import (
    NousProgram, TestNode, TestAssertNode, TestSetupNode,
    LawCost, LawDuration, LawBool, LawInt, LawConstitutional,
)


@dataclass
class AssertResult:
    passed: bool
    expr_repr: str
    actual: Any = None
    message: str = ""


@dataclass
class TestResult:
    name: str
    assertions: list[AssertResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        return all(a.passed for a in self.assertions)

    @property
    def pass_count(self) -> int:
        return sum(1 for a in self.assertions if a.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for a in self.assertions if not a.passed)


@dataclass
class TestSuiteResult:
    results: list[TestResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def passed_tests(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_tests(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total_assertions(self) -> int:
        return sum(len(r.assertions) for r in self.results)

    @property
    def passed_assertions(self) -> int:
        return sum(r.pass_count for r in self.results)

    @property
    def ok(self) -> bool:
        return self.failed_tests == 0


class TestEnv:
    """Evaluation environment for test assertions."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program
        self.variables: dict[str, Any] = {}
        self._build_context()

    def _build_context(self) -> None:
        if self.program.world:
            w = self.program.world
            self.variables["world_name"] = w.name
            self.variables["world_heartbeat"] = w.heartbeat
            self.variables["soul_count"] = len(self.program.souls)
            self.variables["message_count"] = len(self.program.messages)
            for law in w.laws:
                key = f"law_{law.name}"
                if isinstance(law.expr, LawCost):
                    self.variables[key] = law.expr.amount
                elif isinstance(law.expr, LawDuration):
                    self.variables[key] = law.expr.value
                elif isinstance(law.expr, LawBool):
                    self.variables[key] = law.expr.value
                elif isinstance(law.expr, LawInt):
                    self.variables[key] = law.expr.value
                elif isinstance(law.expr, LawConstitutional):
                    self.variables[key] = law.expr.count

        for soul in self.program.souls:
            self.variables[f"soul_{soul.name}_exists"] = True
            if soul.mind:
                self.variables[f"soul_{soul.name}_model"] = soul.mind.model
                self.variables[f"soul_{soul.name}_tier"] = soul.mind.tier.value
            self.variables[f"soul_{soul.name}_senses"] = soul.senses
            self.variables[f"soul_{soul.name}_sense_count"] = len(soul.senses)
            if soul.memory:
                self.variables[f"soul_{soul.name}_memory_count"] = len(soul.memory.fields)
                for f in soul.memory.fields:
                    self.variables[f"soul_{soul.name}_mem_{f.name}"] = f.default
            if soul.dna:
                self.variables[f"soul_{soul.name}_gene_count"] = len(soul.dna.genes)
                for g in soul.dna.genes:
                    self.variables[f"soul_{soul.name}_dna_{g.name}"] = g.value
            if soul.heal:
                self.variables[f"soul_{soul.name}_heal_count"] = len(soul.heal.rules)
            if soul.instinct:
                self.variables[f"soul_{soul.name}_stmt_count"] = len(soul.instinct.statements)

        for msg in self.program.messages:
            self.variables[f"msg_{msg.name}_exists"] = True
            self.variables[f"msg_{msg.name}_field_count"] = len(msg.fields)
            for f in msg.fields:
                self.variables[f"msg_{msg.name}_has_{f.name}"] = True
                self.variables[f"msg_{msg.name}_type_{f.name}"] = f.type_expr

        if self.program.nervous_system:
            self.variables["route_count"] = len(self.program.nervous_system.routes)
        if self.program.evolution:
            self.variables["mutation_count"] = len(self.program.evolution.mutations)
        if self.program.perception:
            self.variables["perception_count"] = len(self.program.perception.rules)

        self.variables["validation_pass"] = self._run_validation()
        self.variables["typecheck_pass"] = self._run_typecheck()

    def _run_validation(self) -> bool:
        try:
            from validator import validate_program
            return validate_program(self.program).ok
        except Exception:
            return False

    def _run_typecheck(self) -> bool:
        try:
            from typechecker import typecheck_program
            return typecheck_program(self.program).ok
        except Exception:
            return False

    def bind(self, name: str, value: Any) -> None:
        self.variables[name] = value

    def eval_expr(self, expr: Any) -> Any:
        if expr is None:
            return None
        if isinstance(expr, bool):
            return expr
        if isinstance(expr, (int, float)):
            return expr
        if isinstance(expr, str):
            if expr == "true":
                return True
            if expr == "false":
                return False
            if expr in self.variables:
                return self.variables[expr]
            return expr
        if isinstance(expr, list):
            return [self.eval_expr(e) for e in expr]
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                return self._eval_binop(expr)
            elif kind == "not":
                return not self.eval_expr(expr.get("operand"))
            elif kind == "attr":
                obj = self.eval_expr(expr.get("obj"))
                attr = expr.get("attr", "")
                if isinstance(obj, dict):
                    return obj.get(attr)
                lookup = f"{obj}_{attr}" if isinstance(obj, str) else f"_{attr}"
                return self.variables.get(lookup)
            elif kind == "func_call":
                func = expr.get("func", "")
                args = expr.get("args", {})
                return self._eval_func(func, args)
            elif kind == "method_call":
                obj = self.eval_expr(expr.get("obj"))
                method = expr.get("method", "")
                return self._eval_method(obj, method, expr.get("args", {}))
        return expr

    def _eval_binop(self, expr: dict) -> Any:
        op = expr.get("op", "")
        left = self.eval_expr(expr.get("left"))
        right = self.eval_expr(expr.get("right"))
        try:
            if op == "==":
                return left == right
            elif op == "!=":
                return left != right
            elif op == ">":
                return left > right
            elif op == "<":
                return left < right
            elif op == ">=":
                return left >= right
            elif op == "<=":
                return left <= right
            elif op == "&&":
                return bool(left) and bool(right)
            elif op == "||":
                return bool(left) or bool(right)
            elif op == "+":
                return left + right
            elif op == "-":
                return left - right
            elif op == "*":
                return left * right
            elif op == "/":
                return left / right if right else 0
            elif op == "%":
                return left % right if right else 0
        except (TypeError, ValueError):
            pass
        return False

    def _eval_func(self, func: str, args: dict) -> Any:
        if func == "len":
            val = self.eval_expr(args.get("_pos_0"))
            if isinstance(val, (list, str, dict)):
                return len(val)
            return 0
        if func == "contains":
            collection = self.eval_expr(args.get("_pos_0"))
            item = self.eval_expr(args.get("_pos_1"))
            if isinstance(collection, (list, str)):
                return item in collection
            return False
        if func == "type_of":
            val = self.eval_expr(args.get("_pos_0"))
            return type(val).__name__
        return None

    def _eval_method(self, obj: Any, method: str, args: dict) -> Any:
        if isinstance(obj, list):
            if method == "len" or method == "count":
                return len(obj)
            if method == "contains":
                item = self.eval_expr(args.get("_pos_0"))
                return item in obj
        if isinstance(obj, str):
            if method == "len":
                return len(obj)
        return None

    def expr_to_str(self, expr: Any) -> str:
        if expr is None:
            return "None"
        if isinstance(expr, (int, float, bool)):
            return str(expr)
        if isinstance(expr, str):
            return expr
        if isinstance(expr, dict):
            kind = expr.get("kind", "")
            if kind == "binop":
                l = self.expr_to_str(expr.get("left"))
                r = self.expr_to_str(expr.get("right"))
                return f"{l} {expr.get('op')} {r}"
            elif kind == "not":
                return f"!{self.expr_to_str(expr.get('operand'))}"
            elif kind == "attr":
                return f"{self.expr_to_str(expr.get('obj'))}.{expr.get('attr')}"
            elif kind == "func_call":
                return f"{expr.get('func')}(...)"
            elif kind == "method_call":
                return f"{self.expr_to_str(expr.get('obj'))}.{expr.get('method')}(...)"
        return str(expr)


class NousTestRunner:
    """Executes test blocks from a NousProgram."""

    def __init__(self, program: NousProgram) -> None:
        self.program = program

    def run_all(self) -> TestSuiteResult:
        suite = TestSuiteResult()
        t0 = time.perf_counter()
        for test in self.program.tests:
            result = self._run_test(test)
            suite.results.append(result)
        suite.duration_ms = (time.perf_counter() - t0) * 1000
        return suite

    def run_by_name(self, name: str) -> Optional[TestResult]:
        for test in self.program.tests:
            if test.name == name:
                return self._run_test(test)
        return None

    def _run_test(self, test: TestNode) -> TestResult:
        result = TestResult(name=test.name)
        t0 = time.perf_counter()
        env = TestEnv(self.program)
        try:
            for item in test.body:
                if isinstance(item, TestSetupNode):
                    val = env.eval_expr(item.value)
                    env.bind(item.name, val)
                elif isinstance(item, TestAssertNode):
                    expr_str = env.expr_to_str(item.expr)
                    try:
                        val = env.eval_expr(item.expr)
                        passed = bool(val)
                        result.assertions.append(AssertResult(
                            passed=passed,
                            expr_repr=expr_str,
                            actual=val,
                            message="" if passed else f"evaluated to {val}",
                        ))
                    except Exception as e:
                        result.assertions.append(AssertResult(
                            passed=False,
                            expr_repr=expr_str,
                            actual=None,
                            message=f"error: {e}",
                        ))
        except Exception as e:
            result.error = str(e)
        result.duration_ms = (time.perf_counter() - t0) * 1000
        return result


def run_tests(program: NousProgram) -> TestSuiteResult:
    runner = NousTestRunner(program)
    return runner.run_all()


def print_results(suite: TestSuiteResult) -> None:
    for result in suite.results:
        status = "PASS" if result.passed else "FAIL"
        icon = "✓" if result.passed else "✗"
        print(f"\n  {icon} {result.name} [{status}] ({result.duration_ms:.1f}ms)")
        if result.error:
            print(f"    ERROR: {result.error}")
        for a in result.assertions:
            icon_a = "✓" if a.passed else "✗"
            print(f"    {icon_a} assert {a.expr_repr}")
            if not a.passed and a.message:
                print(f"      → {a.message}")

    print(f"\n{'═' * 50}")
    print(f"  Tests:      {suite.passed_tests}/{suite.total_tests} passed")
    print(f"  Assertions: {suite.passed_assertions}/{suite.total_assertions} passed")
    print(f"  Duration:   {suite.duration_ms:.1f}ms")
    status = "PASS" if suite.ok else "FAIL"
    print(f"  Result:     {status}")


def cmd_test(file_path: str) -> int:
    from parser import parse_nous_file
    from validator import validate_program
    source = Path(file_path)
    if not source.exists():
        print(f"Error: file not found: {source}")
        return 1
    try:
        program = parse_nous_file(source)
    except Exception as e:
        print(f"Parse error: {e}")
        return 1
    vr = validate_program(program)
    if not vr.ok:
        print("Validation FAILED:")
        for e in vr.errors:
            print(f"  {e}")
        return 1
    if not program.tests:
        print(f"No test blocks found in {source.name}")
        return 0
    world_name = program.world.name if program.world else "Unknown"
    print(f"═══ NOUS Test Runner — {world_name} ═══")
    print(f"File: {source.name} | {len(program.tests)} test blocks")
    suite = run_tests(program)
    print_results(suite)
    return 0 if suite.ok else 1
