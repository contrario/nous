"""S320 P3: every top-level phase definition in scripts/release.py that
passes check=False also decides on a returncode inside that same
definition.

THIS FILE DOES NOT IMPORT scripts/release.py. It parses the source with
ast. The shape therefore verifies position in the source and not runtime
dependence, which is the declaration at line 3066 of
docs/GLM_SUPERSESSION_DESIGN.md, restated whole by D319-6. Because
nothing is imported, the seam question that FG-S317-A names does not
arise here at all.

SET: top-level ast.FunctionDef nodes in scripts/release.py whose name
begins with phase_.

SHAPE: inside one such node, a call carrying a keyword argument named
check whose value is the constant False, and an attribute access whose
attr is returncode.

BLIND TO:
  nested definitions, which ast.walk reaches as part of their enclosing
    top-level node, so a check=False inside a nested def counts toward
    the phase and a returncode inside a different nested def would
    satisfy it;
  module-level code between two definitions, and run() at line 105,
    which is not a phase;
  any invocation that does not spell check=False, including one that
    passes the value through a variable;
  WHETHER THE returncode READ BELONGS TO THE CALL THAT PASSED
    check=False. The rule of D318-4 binds per function, not per call
    site. That is FG-S320-D, recorded in D319-5 and deliberately not
    repaired here. test_n3 below asserts the consequence rather than
    leaving it as prose;
  everything that happens at runtime.

__s320_p3_phase_exit_state_ast_v1__
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RELEASE = _REPO / "scripts" / "release.py"

_MEASURED_CARRIERS = {
    "phase_preflight",
    "phase_pytest",
    "phase_pyflakes",
    "phase_claim_lint",
    "phase_sidecar_integrity",
}


def _source() -> str:
    return _RELEASE.read_text(encoding="utf-8")


def _phase_defs(source: str) -> list[ast.FunctionDef]:
    tree = ast.parse(source)
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("phase_")
    ]


def _passes_check_false(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        for kw in child.keywords:
            if (
                kw.arg == "check"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is False
            ):
                return True
    return False


def _reads_returncode(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(child, ast.Attribute) and child.attr == "returncode"
        for child in ast.walk(node)
    )


def _offenders(source: str) -> list[str]:
    return [
        node.name
        for node in _phase_defs(source)
        if _passes_check_false(node) and not _reads_returncode(node)
    ]


def _carriers(source: str) -> set[str]:
    return {
        node.name
        for node in _phase_defs(source)
        if _passes_check_false(node)
    }


def _elide(source: str, phase: str, limit: int | None = None) -> str:
    """Rename returncode inside one phase. Renaming rather than deleting
    keeps the source parseable, so the mutation changes exactly one
    thing. limit=None renames every occurrence in that phase; limit=1
    renames only the first, which is what test_n3 needs."""
    lines = source.splitlines(True)
    node = next(n for n in _phase_defs(source) if n.name == phase)
    assert node.end_lineno is not None
    hits = 0
    for i in range(node.lineno - 1, node.end_lineno):
        if "returncode" in lines[i]:
            if limit is not None and hits >= limit:
                break
            lines[i] = lines[i].replace("returncode", "rc_elided")
            hits += 1
    assert hits > 0, "no returncode to elide in " + phase
    mutated = "".join(lines)
    ast.parse(mutated)
    return mutated


def test_the_source_is_readable_and_parses():
    source = _source()
    assert source
    assert _phase_defs(source)


def test_the_measured_carriers_are_all_phase_definitions():
    names = {node.name for node in _phase_defs(_source())}
    assert _MEASURED_CARRIERS <= names


def test_no_phase_passes_check_false_without_deciding():
    """D318-4, narrowed and whole. This is the rule."""
    assert _offenders(_source()) == []


def test_the_carriers_are_the_five_measured_in_s320():
    """A review trigger, not a correctness claim. If a sixth phase
    grows a check=False site this fails, and the ledger gets an entry
    before the set moves."""
    assert _carriers(_source()) == _MEASURED_CARRIERS


def _delta(source: str, mutated: str) -> set[str]:
    """What the mutation ADDED to the offender set. Asserting the delta
    rather than the absolute list keeps each negative control from
    firing on an offender it did not create, which is R14: the failing
    sets must be disjoint."""
    return set(_offenders(mutated)) - set(_offenders(source))


def test_n1_negative_control_claim_lint():
    """One mutation. phase_claim_lint carries a single returncode read;
    eliding it makes that phase an offender and nothing else moves."""
    source = _source()
    assert _delta(source, _elide(source, "phase_claim_lint")) == {
        "phase_claim_lint"
    }


def test_n2_negative_control_sidecar_integrity():
    """One mutation, disjoint from N1."""
    source = _source()
    assert _delta(source, _elide(source, "phase_sidecar_integrity")) == {
        "phase_sidecar_integrity"
    }


def test_n3_one_of_two_reads_is_enough_which_is_fg_s320_d():
    """phase_preflight carries two check=False sites and two returncode
    reads. Eliding BOTH makes it an offender; eliding ONE does not,
    because the rule binds per function and not per call site. If the
    second assertion ever fails, the rule was narrowed and D319-5 needs
    an entry."""
    source = _source()
    assert _delta(source, _elide(source, "phase_preflight")) == {
        "phase_preflight"
    }
    assert _delta(source, _elide(source, "phase_preflight", limit=1)) == set()


def test_the_shape_can_see_a_planted_offender():
    """R11. A rule that cannot fire is not a rule. This plants a phase
    that passes check=False and never reads a returncode, in memory."""
    source = _source()
    planted = source + (
        "\n\ndef phase_s320_planted_offender() -> None:\n"
        "    run([\"true\"], check=False)\n"
    )
    assert _delta(source, planted) == {"phase_s320_planted_offender"}


def test_run_is_not_in_the_set():
    """run() at 105 carries check=False at 116 and reads returncode at
    119 and 122, and it is not a phase. The SET excludes it by name."""
    names = {node.name for node in _phase_defs(_source())}
    assert "run" not in names


@pytest.mark.parametrize("phase", sorted(_MEASURED_CARRIERS))
def test_each_carrier_decides_individually(phase):
    node = next(n for n in _phase_defs(_source()) if n.name == phase)
    assert _passes_check_false(node)
    assert _reads_returncode(node)
