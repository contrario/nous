#!/usr/bin/env python3
"""
POLICY GRAMMAR E2E TEST — Phase G Layer 2
==========================================

10 tests covering parse -> AST -> validate -> codegen -> exec -> RiskRule.
Run with: python3 tests/test_policy_grammar.py

# __policy_grammar_tests_v1__
"""
from __future__ import annotations

import ast as _ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parser import parse_nous  # noqa: E402
from validator import validate_program  # noqa: E402
from codegen import generate_python  # noqa: E402
from ast_nodes import PolicyNode, NousProgram, WorldNode  # noqa: E402
from risk_engine import RiskRule  # noqa: E402


# __policy_grammar_tests_fix_v1__
SAMPLE_SRC: str = """
world TestWorld {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 1s

    policy HighCost {
        kind: "llm.response"
        signal: cost > 0.05
        weight: 3.0
        window: 0
        action: log_only
        description: "Cost ceiling breach"
    }

    policy ErrorSpike {
        kind: "sense.error"
        signal: true
        weight: 2.0
        action: intervene
    }
}

soul Alpha {
    mind: deepseek-r1 @ Tier1
    senses: [http_get]

    memory {
        x: int = 0
    }

    instinct {
        let y = x + 1
        remember x = y
    }

    heal {
        on timeout => retry(2, timeout)
    }
}
"""


def _extract_top_level_namespace(py_code: str) -> dict:
    tree = _ast.parse(py_code)
    top = []
    for n in tree.body:
        if isinstance(n, (_ast.ClassDef, _ast.FunctionDef, _ast.AsyncFunctionDef)):
            break
        top.append(n)
    src_top = _ast.unparse(_ast.Module(body=top, type_ignores=[]))
    ns: dict = {}
    exec(src_top, ns)
    return ns


def test_01_parse_policy_block() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    assert prog.world is not None
    assert len(prog.world.policies) == 2
    names = {p.name for p in prog.world.policies}
    assert names == {"HighCost", "ErrorSpike"}, f"got {names}"
    return True


def test_02_policy_fields_typed() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    hc = next(p for p in prog.world.policies if p.name == "HighCost")
    assert isinstance(hc, PolicyNode)
    assert hc.kind == "llm.response"
    assert hc.weight == 3.0
    assert hc.window == 0
    assert hc.action == "log_only"
    assert hc.description == "Cost ceiling breach"
    assert isinstance(hc.signal, dict)
    assert hc.signal.get("kind") == "binop"
    assert hc.signal.get("op") == ">"
    return True


def test_03_policy_defaults_applied() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    es = next(p for p in prog.world.policies if p.name == "ErrorSpike")
    assert es.window == 0
    assert es.description == ""
    assert es.action == "intervene"
    return True


def test_04_validator_accepts_valid() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    r = validate_program(prog)
    policy_errs = [e for e in r.errors if e.code.startswith("PL")]
    assert policy_errs == [], f"unexpected policy errors: {policy_errs}"
    return True


def test_05_validator_rejects_invalid_weight() -> bool:
    p = PolicyNode(name="Bad", signal=True, weight=0.0)
    prog = NousProgram(
        world=WorldNode(name="W", policies=[p]),
        souls=[],
        messages=[],
    )
    r = validate_program(prog)
    codes = {e.code for e in r.errors}
    assert "PL003" in codes, f"expected PL003 in {codes}"
    return True


def test_06_validator_rejects_duplicate_name() -> bool:
    p1 = PolicyNode(name="Dup", signal=True, weight=1.0)
    p2 = PolicyNode(name="Dup", signal=True, weight=1.0)
    prog = NousProgram(
        world=WorldNode(name="W", policies=[p1, p2]),
        souls=[],
        messages=[],
    )
    r = validate_program(prog)
    codes = {e.code for e in r.errors}
    assert "PL001" in codes, f"expected PL001 in {codes}"
    return True


def test_07_codegen_emits_policies_constant() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    py_code = generate_python(prog)
    assert "_POLICIES: list[RiskRule] = [" in py_code
    assert "from risk_engine import RiskRule" in py_code
    assert "_POLICY_ACTIONS: dict[str, str]" in py_code
    return True


def test_08_codegen_zero_output_when_no_policies() -> bool:
    src_nopol = """
world Empty {
    law cost_ceiling = $1.00 per cycle
    heartbeat = 1s
}

soul Beta {
    mind: deepseek-r1 @ Tier1
    senses: [http_get]

    memory {
        x: int = 0
    }

    instinct {
        let y = x + 1
        remember x = y
    }

    heal {
        on timeout => retry(2, timeout)
    }
}
"""
    prog = parse_nous(src_nopol)
    py_code = generate_python(prog)
    assert "_POLICIES" not in py_code
    assert "from risk_engine import RiskRule" not in py_code
    return True


def test_09_generated_runtime_loads_risk_rules() -> bool:
    prog = parse_nous(SAMPLE_SRC)
    py_code = generate_python(prog)
    ns = _extract_top_level_namespace(py_code)
    policies = ns.get("_POLICIES")
    actions = ns.get("_POLICY_ACTIONS")
    assert policies is not None and len(policies) == 2
    for p in policies:
        assert isinstance(p, RiskRule), f"not RiskRule: {type(p)}"
    names = {p.name for p in policies}
    assert names == {"HighCost", "ErrorSpike"}
    assert actions == {"HighCost": "log_only", "ErrorSpike": "intervene"}
    hc = next(p for p in policies if p.name == "HighCost")
    assert hc.predicate == "(cost > 0.05)"
    assert hc.weight == 3.0
    assert hc.action == "log_only"
    assert hc.kind_filter == ("llm.response",)
    return True


def test_10_generated_py_compiles() -> bool:
    import py_compile
    import tempfile
    prog = parse_nous(SAMPLE_SRC)
    py_code = generate_python(prog)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(py_code)
        path = f.name
    try:
        py_compile.compile(path, doraise=True)
    finally:
        Path(path).unlink(missing_ok=True)
    return True


TESTS = [
    ("policy block parses into PolicyNode instances", test_01_parse_policy_block),
    ("policy fields carry correct types", test_02_policy_fields_typed),
    ("policy defaults applied when clauses omitted", test_03_policy_defaults_applied),
    ("validator accepts valid policies", test_04_validator_accepts_valid),
    ("validator rejects invalid weight (PL003)", test_05_validator_rejects_invalid_weight),
    ("validator rejects duplicate name (PL001)", test_06_validator_rejects_duplicate_name),
    ("codegen emits _POLICIES constant + import", test_07_codegen_emits_policies_constant),
    ("codegen emits zero output when no policies", test_08_codegen_zero_output_when_no_policies),
    ("generated _POLICIES instantiates as RiskRule", test_09_generated_runtime_loads_risk_rules),
    ("generated Python compiles cleanly", test_10_generated_py_compiles),
]


def main() -> int:
    print("=" * 56)
    print("POLICY GRAMMAR E2E TESTS — PHASE G LAYER 2")
    print("=" * 56)
    passed = 0
    failed = 0
    for idx, (name, fn) in enumerate(TESTS, 1):
        try:
            fn()
            print(f"  {idx:2d}. ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  {idx:2d}. ✗ {name}")
            print(f"      FAIL: {type(e).__name__}: {e}")
            failed += 1
    print("=" * 56)
    if failed == 0:
        print(f"POLICY GRAMMAR TESTS — ALL GREEN ({passed}/{len(TESTS)})")
        print("=" * 56)
        return 0
    print(f"POLICY GRAMMAR TESTS — FAILED ({failed}/{len(TESTS)})")
    print("=" * 56)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
