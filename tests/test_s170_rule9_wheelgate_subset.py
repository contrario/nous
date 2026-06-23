"""
S170 Leg 7 -- Rule 9 pre-release consistency guard.

A new top-level module must be registered in BOTH pyproject.toml py-modules
(so the wheel ships it) AND, when release-critical, the wheel content gate's
`required` list in scripts/release.py (so the release pipeline verifies it
shipped). The wheel gate is a deliberately curated subset of py-modules, so
the only always-true invariant is the subset direction: every .py module the
gate REQUIRES must be a declared py-module. A gate entry absent from
py-modules is latent: the wheel build would be asked to verify a module that
was never packaged, failing confusingly at release phase 7 instead of here.

This test turns that drift into a clear failure at `pytest` time. It parses
pyproject.toml with tomllib (it is TOML) and scripts/release.py with ast
(the `required` list is a function-local, not importable), so it reads the
real structures rather than mirroring them by hand.

# __s170_leg7_rule9_subset_v1__
"""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_RELEASE = _REPO / "scripts" / "release.py"
_PYPROJECT = _REPO / "pyproject.toml"

_COST_CAP_MODULES = ("cost_farkas", "cli_verify_cost", "coverage_farkas")


def _pyproject_py_modules() -> set[str]:
    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    mods = data["tool"]["setuptools"]["py-modules"]
    return {str(m) for m in mods}


def _wheel_gate_py_stems() -> set[str]:
    tree = ast.parse(_RELEASE.read_text(encoding="utf-8"))
    stems: set[str] = set()
    for node in ast.walk(tree):
        target_name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target_name = node.targets[0].id
            value = node.value
        if target_name != "required" or not isinstance(value, ast.List):
            continue
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                if elt.value.endswith(".py"):
                    stems.add(elt.value[:-3])
    return stems


def test_wheel_gate_parsed_nonempty() -> None:
    gate = _wheel_gate_py_stems()
    assert len(gate) >= 40, (
        "wheel-gate `required` list parse looks broken: found only "
        f"{len(gate)} .py stems (expected the curated critical subset)"
    )


def test_wheel_gate_py_modules_subset_of_pyproject() -> None:
    gate = _wheel_gate_py_stems()
    declared = _pyproject_py_modules()
    orphans = sorted(gate - declared)
    assert not orphans, (
        "wheel-gate requires .py modules not declared in pyproject "
        f"py-modules (Rule 9 drift -- add them to py-modules): {orphans}"
    )


def test_cost_cap_modules_registered_in_both() -> None:
    gate = _wheel_gate_py_stems()
    declared = _pyproject_py_modules()
    for mod in _COST_CAP_MODULES:
        assert mod in declared, f"{mod} missing from pyproject py-modules"
        assert mod in gate, f"{mod} missing from wheel-gate `required` list"
