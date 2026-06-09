"""S123 boundary + multi-var dossier e2e regression (P3b-bool boundary pin).

Freezes the sound-but-ahead state surfaced in S123:
  - z3-side coverage proves/refutes boolean (AND/OR) blocking and threshold
    nets correctly (native SMT boolean structure).
  - The stdlib Farkas extractor is BEHIND: it raises a typed FarkasError on
    boolean structure (only a single comparison or a flat OR of comparisons
    is supported), never a false PROVEN.
  - A multi-variable LINEAR coverage region travels end-to-end through a real
    nous verify + nous dossier to a PROVEN dossier whose emitted
    verify_offline.py passes offline, including the S121 coverage-region
    monotonicity check across a supersession hop.

This is a regression FREEZE, not a feature. The Farkas DNF bundle (S124) will
lift Farkas to parity; until then these tests pin that boolean nets are
z3-checkable-only, and that no boolean net is ever signed as Farkas-proven.

# __s123_boundary_pin_test_v1__
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from parser import parse_nous
from policy_coverage import (
    build_threshold_claim,
    build_coverage_block,
    serialize_coverage,
)
from coverage_farkas import serialize_system, FarkasError


def _policies(blocking_signal: str):
    src = (
        "world _S123Probe {\n"
        '    policy _Block { kind: "x" signal: '
        + blocking_signal + " action: block }\n"
        "}\n"
    )
    return list(parse_nous(src).world.policies)


def _threshold_ast(threshold_signal: str):
    src = (
        "world _S123T {\n"
        '    policy _P { kind: "x" signal: '
        + threshold_signal + " action: log_only }\n}\n"
    )
    return parse_nous(src).world.policies[0].signal


def _z3_verdict(threshold_signal: str, blocking_signal: str) -> str:
    z3 = pytest.importorskip("z3")
    pol = _policies(blocking_signal)
    th = _threshold_ast(threshold_signal)
    claim = build_threshold_claim(th, threshold_signal)
    script = serialize_coverage(build_coverage_block(pol, claim))
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


def _farkas_raises(threshold_signal: str, blocking_signal: str) -> bool:
    pol = _policies(blocking_signal)
    th = _threshold_ast(threshold_signal)
    blocking = [p.signal for p in pol]
    try:
        serialize_system(th, blocking, threshold_expr=threshold_signal)
        return False
    except FarkasError:
        return True


def test_conjunctive_blocking_no_gap_z3_proven() -> None:
    assert _z3_verdict(
        "amount > 5000 && risk_score > 30",
        "amount > 5000 && risk_score > 30",
    ) == "proven"


def test_conjunctive_blocking_known_gap_z3_refuted() -> None:
    assert _z3_verdict(
        "amount > 5000", "amount > 5000 && risk_score > 30"
    ) == "refuted"


def test_disjunctive_threshold_no_gap_z3_proven() -> None:
    assert _z3_verdict(
        "amount > 5000 || risk_score > 30",
        "amount > 5000 || risk_score > 30",
    ) == "proven"


def test_disjunctive_threshold_known_gap_z3_refuted() -> None:
    assert _z3_verdict(
        "amount > 5000 || risk_score > 30", "amount > 5000"
    ) == "refuted"


def test_conjunctive_blocking_farkas_refuses_typed() -> None:
    assert _farkas_raises(
        "amount > 5000 && risk_score > 30",
        "amount > 5000 && risk_score > 30",
    ) is True


def test_disjunctive_threshold_farkas_refuses_typed() -> None:
    assert _farkas_raises(
        "amount > 5000 || risk_score > 30",
        "amount > 5000 || risk_score > 30",
    ) is True


def test_negation_signal_farkas_refuses_typed() -> None:
    assert _farkas_raises("!(amount > 5000)", "amount > 5000") is True


_MULTIVAR_NOUS = """world MultivarLoanGovernance {
    law CostCeiling = $0.50 per cycle
    heartbeat = 10s
    cost_cap: COST_CAP USD
    max_ticks: 1
    policy BlockHighWeightedExposure {
        kind: "loan.decision"
        signal: 2 * amount + risk_score > THRESHOLD
        weight: 10.0
        action: block
    }
    policy LogAllDecisions {
        kind: "loan.decision"
        signal: true
        weight: 1.0
        action: log_only
    }
}
message LoanApplication {
    application_id: string
    amount: float
    risk_score: float
}
soul Underwriter {
    mind: claude-haiku-4-5 @ Tier0A
    tokens: input = 500 output = 200
    senses: [http_get]
    memory {
        evaluated: int = 0
    }
    instinct {
        let app = listen Intake::LoanApplication
        guard app != null else sleep 5s
        speak LoanApplication(application_id: app.application_id, amount: app.amount, risk_score: app.risk_score)
        remember evaluated = evaluated + 1
    }
    heal {
        on timeout => retry(2, timeout)
    }
}
"""


def _nous_cli() -> str:
    exe = shutil.which("nous")
    if exe is None:
        pytest.skip("nous CLI not on PATH")
    return exe


def _run(args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120
    )


def _write_nous(path: Path, cost_cap: str, threshold: str) -> None:
    path.write_text(
        _MULTIVAR_NOUS.replace("COST_CAP", cost_cap).replace(
            "THRESHOLD", threshold
        ),
        encoding="utf-8",
    )


def test_multivar_dossier_e2e_single_link(tmp_path: Path) -> None:
    nous = _nous_cli()
    src = tmp_path / "mv.nous"
    _write_nous(src, "0.50", "10000")
    man = tmp_path / "manifest.json"
    r = _run([
        nous, "verify", str(src), "--smt",
        "--coverage-threshold", "2 * amount + risk_score > 10000",
        "--manifest-out", str(man),
    ])
    assert r.returncode == 0, r.stderr
    assert "Coverage PROVEN" in r.stdout
    assert "Farkas certificate extracted" in r.stdout

    dossier = tmp_path / "dossier"
    r = _run([
        nous, "dossier", str(src), "--manifest", str(man),
        "--output", str(dossier),
    ])
    assert r.returncode == 0, r.stderr
    assert (dossier / "coverage.smt2").is_file()
    assert (dossier / "coverage.farkas.json").is_file()

    r = _run([sys.executable, "verify_offline.py"], cwd=str(dossier))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Farkas certificate verified by rational arithmetic" in r.stdout
    assert "VERDICT: PASS" in r.stdout


def test_multivar_dossier_e2e_chain_monotonicity(tmp_path: Path) -> None:
    nous = _nous_cli()
    src1 = tmp_path / "mv1.nous"
    _write_nous(src1, "0.50", "10000")
    man1 = tmp_path / "m1.json"
    r = _run([
        nous, "verify", str(src1), "--smt",
        "--coverage-threshold", "2 * amount + risk_score > 10000",
        "--manifest-out", str(man1),
    ])
    assert r.returncode == 0, r.stderr
    dossier1 = tmp_path / "d1"
    r = _run([
        nous, "dossier", str(src1), "--manifest", str(man1),
        "--output", str(dossier1),
    ])
    assert r.returncode == 0, r.stderr

    src2 = tmp_path / "mv2.nous"
    _write_nous(src2, "0.40", "8000")
    man2 = tmp_path / "m2.json"
    r = _run([
        nous, "verify", str(src2), "--smt",
        "--coverage-threshold", "2 * amount + risk_score > 8000",
        "--supersedes", str(man1),
        "--manifest-out", str(man2),
    ])
    assert r.returncode == 0, r.stderr
    assert "Re-binding: supersedes" in r.stdout

    dossier2 = tmp_path / "d2"
    r = _run([
        nous, "dossier", str(src2), "--manifest", str(man2),
        "--supersedes", str(dossier1), "--output", str(dossier2),
    ])
    assert r.returncode == 0, r.stderr
    assert (dossier2 / "chain").is_dir()

    r = _run([sys.executable, "verify_offline.py"], cwd=str(dossier2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "coverage-region monotonicity verified across 1 hop" in r.stdout
    assert "VERDICT: PASS" in r.stdout
