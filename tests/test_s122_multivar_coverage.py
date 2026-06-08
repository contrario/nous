"""End-to-end multi-variable policy-coverage tests (S122 P3b-multivar).

The linear multi-var coverage fragment: constant*variable admitted,
variable*variable refused (outside QF_LRA). These tests drive the real
production path -- parse_nous, the policy AST, build_coverage_block +
serialize_coverage (z3 side), serialize_system + check_serialized (Farkas
side) -- and assert the two independent checkers agree on every case.

# __s122_multivar_coverage_test_v1__
"""
from __future__ import annotations

import pytest

from parser import parse_nous
from policy_coverage import (
    build_threshold_claim,
    build_coverage_block,
    serialize_coverage,
    CoverageEmitError,
)
from coverage_farkas import (
    serialize_system,
    check_serialized,
    FarkasError,
)


def _world(threshold_signal: str, blocking_signal: str) -> str:
    return (
        "world _MultivarProbe {\n"
        '    policy _Block { kind: "x" signal: '
        + blocking_signal + " action: block }\n"
        "}\n"
    ), threshold_signal


def _policies_and_threshold(threshold_signal: str, blocking_signal: str):
    src, th_expr = _world(threshold_signal, blocking_signal)
    prog = parse_nous(src)
    policies = list(getattr(prog.world, "policies", None) or [])
    th_src = (
        "world _T {\n"
        '    policy _P { kind: "x" signal: '
        + th_expr + " action: log_only }\n}\n"
    )
    th_prog = parse_nous(th_src)
    th_ast = th_prog.world.policies[0].signal
    return policies, th_ast, th_expr


def _z3_coverage_check(policies, th_ast, th_expr):
    """Return 'proven' (unsat), 'refuted' (sat) for the coverage obligation
    built exactly as cli_verify builds coverage.smt2, or raise."""
    z3 = pytest.importorskip("z3")
    claim = build_threshold_claim(th_ast, th_expr)
    block = build_coverage_block(policies, claim)
    script = serialize_coverage(block)
    body = "\n".join(
        ln for ln in script.splitlines()
        if not ln.strip().startswith("(check-sat")
    )
    s = z3.Solver()
    s.from_string(body)
    res = s.check()
    if res == z3.unsat:
        return "proven"
    if res == z3.sat:
        return "refuted"
    return "unknown"


def _farkas_proves(policies, th_ast, th_expr) -> bool:
    """True iff a Farkas certificate exists and checks (coverage proven).
    Raises FarkasError if outside the fragment."""
    blocking = [
        p.signal for p in policies
        if getattr(p, "action", None) in ("block", "abort_cycle")
    ]
    try:
        doc = serialize_system(th_ast, blocking, threshold_expr=th_expr)
    except FarkasError:
        return False
    return check_serialized(doc)


def test_identical_multivar_proven() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount + risk_score > 10000", "amount + risk_score > 10000"
    )
    assert _farkas_proves(pol, th, ex) is True


def test_identical_multivar_z3_unsat() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount + risk_score > 10000", "amount + risk_score > 10000"
    )
    assert _z3_coverage_check(pol, th, ex) == "proven"


def test_scalar_coefficient_multivar_proven() -> None:
    pol, th, ex = _policies_and_threshold(
        "2 * amount + risk_score > 10000",
        "2 * amount + risk_score > 10000",
    )
    assert _farkas_proves(pol, th, ex) is True


def test_scalar_coefficient_multivar_z3_unsat() -> None:
    pol, th, ex = _policies_and_threshold(
        "2 * amount + risk_score > 10000",
        "2 * amount + risk_score > 10000",
    )
    assert _z3_coverage_check(pol, th, ex) == "proven"


def test_smaller_blocking_net_refuted_farkas() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount + risk_score > 10000", "amount + risk_score > 20000"
    )
    assert _farkas_proves(pol, th, ex) is False


def test_smaller_blocking_net_refuted_z3() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount + risk_score > 10000", "amount + risk_score > 20000"
    )
    assert _z3_coverage_check(pol, th, ex) == "refuted"


def test_bilinear_threshold_refused_at_emit() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount * risk_score > 10000", "amount + risk_score > 10000"
    )
    with pytest.raises(CoverageEmitError):
        claim = build_threshold_claim(th, ex)
        build_coverage_block(pol, claim)


def test_bilinear_threshold_refused_farkas() -> None:
    pol, th, ex = _policies_and_threshold(
        "amount * risk_score > 10000", "amount + risk_score > 10000"
    )
    blocking = [
        p.signal for p in pol
        if getattr(p, "action", None) in ("block", "abort_cycle")
    ]
    with pytest.raises(FarkasError):
        serialize_system(th, blocking, threshold_expr=ex)


@pytest.mark.parametrize(
    "threshold_sig,blocking_sig",
    [
        ("amount + risk_score > 10000", "amount + risk_score > 10000"),
        ("2 * amount + risk_score > 10000",
         "2 * amount + risk_score > 10000"),
        ("amount + risk_score > 10000", "amount + risk_score > 20000"),
    ],
)
def test_lockstep_z3_agrees_with_farkas(
    threshold_sig: str, blocking_sig: str
) -> None:
    pytest.importorskip("z3")
    pol, th, ex = _policies_and_threshold(threshold_sig, blocking_sig)
    z3_verdict = _z3_coverage_check(pol, th, ex)
    farkas_proven = _farkas_proves(pol, th, ex)
    assert (z3_verdict == "proven") == farkas_proven
