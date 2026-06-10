"""S124 Farkas DNF bundle regression (P3b-bool parity).

Two-sided pins for the disjunctive-linear bundle path:
  - serialize_auto keeps the v1 single-system certificate byte-identical
    for v1-fragment obligations and dispatches boolean structure to the
    DNF bundle (one Farkas certificate per disjunct of the gap negation
    T && !B; PROVEN iff every disjunct is refuted).
  - check_serialized_bundle re-derives the disjunct set from the supplied
    ASTs and requires a bijection; omission, surplus, duplicate,
    substitution, and forged-multiplier bundles all FAIL even when the
    enclosing manifest signature is valid (zero issuer trust).
  - coverage_minilang re-derives the same disjunct set from source TEXT
    (string-aware scanner + grammar-mirroring parser); issuance-time
    cross-derivation gating and the emitted offline verifier both rest
    on this parity.
  - DNF expansion is bounded (DISJUNCT_BOUND) with a typed REFUSE;
    var*var stays REFUSED (bilinear, outside QF_LRA).
  - chain + bundle composition is REFUSED at dossier build (honest
    boundary; S124 carry-forward).

# __s124_bundle_test_v1__
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from parser import parse_nous
from coverage_farkas import (
    BUNDLE_FRAGMENT,
    DISJUNCT_BOUND,
    FarkasError,
    check_serialized_bundle,
    serialize_auto,
    serialize_bundle,
    serialize_system,
)
from coverage_minilang import (
    MinilangError,
    bundle_cert_keys,
    derive_disjunct_constraints,
    ml_scan_blocking_signals,
)


def _policies(blocking_signal: str):
    src = (
        "world _S124Probe {\n"
        '    policy _Block { kind: "x" signal: '
        + blocking_signal + " action: block }\n"
        "}\n"
    )
    return list(parse_nous(src).world.policies)


def _threshold_ast(threshold_signal: str):
    src = (
        "world _S124T {\n"
        '    policy _P { kind: "x" signal: '
        + threshold_signal + " action: log_only }\n}\n"
    )
    return parse_nous(src).world.policies[0].signal


def _bundle(threshold: str, blocking: str) -> dict:
    th = _threshold_ast(threshold)
    sigs = [p.signal for p in _policies(blocking)]
    return serialize_bundle(th, sigs, threshold_expr=threshold)


def _check(doc: dict, threshold: str, blocking: str) -> bool:
    th = _threshold_ast(threshold)
    sigs = [p.signal for p in _policies(blocking)]
    return check_serialized_bundle(doc, th, sigs)


def test_conjunctive_no_gap_bundle_proven() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    assert doc["fragment"] == BUNDLE_FRAGMENT
    assert doc["disjunct_count"] == 2
    assert _check(doc, t, t) is True


def test_conjunctive_known_gap_refused() -> None:
    with pytest.raises(FarkasError):
        _bundle("amount > 5000", "amount > 5000 && risk_score > 30")


def test_disjunctive_threshold_no_gap_bundle_proven() -> None:
    t = "amount > 5000 || risk_score > 30"
    doc = _bundle(t, t)
    assert doc["fragment"] == BUNDLE_FRAGMENT
    assert _check(doc, t, t) is True


def test_disjunctive_threshold_known_gap_refused() -> None:
    with pytest.raises(FarkasError):
        _bundle("amount > 5000 || risk_score > 30", "amount > 5000")


def test_negated_blocking_no_gap_bundle_proven() -> None:
    doc = _bundle("amount > 5000", "!(amount <= 4000)")
    assert doc["fragment"] == BUNDLE_FRAGMENT
    assert _check(doc, "amount > 5000", "!(amount <= 4000)") is True


def test_omission_attack_fails() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    assert doc["disjunct_count"] >= 2
    forged = copy.deepcopy(doc)
    forged["certs"] = forged["certs"][:1]
    forged["disjunct_count"] = 1
    assert _check(forged, t, t) is False


def test_forged_multiplier_fails() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    forged = copy.deepcopy(doc)
    forged["certs"][0]["multipliers"] = ["0"] * len(
        forged["certs"][0]["multipliers"]
    )
    assert _check(forged, t, t) is False


def test_substituted_constraint_fails() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    forged = copy.deepcopy(doc)
    cons0 = forged["certs"][0]["constraints"][0]
    key = next(k for k in cons0["coeffs"] if k != "")
    cons0["coeffs"][key] = "999"
    assert _check(forged, t, t) is False


def test_duplicate_cert_fails() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    forged = copy.deepcopy(doc)
    forged["certs"].append(copy.deepcopy(forged["certs"][0]))
    assert _check(forged, t, t) is False


def test_dnf_bound_overflow_refused() -> None:
    th = _threshold_ast("t0 > 0")
    sigs = []
    for i in range(7):
        sigs.extend(
            p.signal
            for p in _policies(f"a{i} > 0 && b{i} > 0")
        )
    with pytest.raises(FarkasError, match="bound"):
        serialize_bundle(th, sigs, threshold_expr="t0 > 0")


def test_bilinear_inside_boolean_refused() -> None:
    with pytest.raises(FarkasError, match="bilinear"):
        _bundle("x > 0", "x * y > 5 && x > 0")


def test_auto_v1_fragment_byte_identical() -> None:
    t = "2 * amount + risk_score > 10000"
    b = "2 * amount + risk_score > 8000"
    th = _threshold_ast(t)
    sigs = [p.signal for p in _policies(b)]
    v1 = serialize_system(th, sigs, threshold_expr=t)
    auto = serialize_auto(th, sigs, threshold_expr=t)
    assert auto["fragment"] == "linear-real-single-comparison"
    assert json.dumps(v1, sort_keys=True) == json.dumps(
        auto, sort_keys=True
    )


def test_auto_boolean_dispatches_to_bundle() -> None:
    t = "amount > 5000 && risk_score > 30"
    th = _threshold_ast(t)
    sigs = [p.signal for p in _policies(t)]
    auto = serialize_auto(th, sigs, threshold_expr=t)
    assert auto["fragment"] == BUNDLE_FRAGMENT


_SCANNER_WORLD = """world _S124Scan {
    policy _Risky {
        kind: "loan.decision"
        description: "see policy { docs } # not a comment"
        signal: amount > 4000 && risk_score > 2000
        weight: 10.0
        action: block
    }
    policy _Log {
        kind: "loan.decision"
        signal: true
        weight: 1.0
        action: log_only
    }
}
"""


def test_minilang_scanner_blocking_only_string_aware() -> None:
    sigs = ml_scan_blocking_signals(_SCANNER_WORLD)
    assert len(sigs) == 1
    assert sigs[0]["op"] == "&&"


def test_minilang_cross_derivation_parity() -> None:
    threshold = "amount > 4000 && risk_score > 2000"
    th = _threshold_ast(threshold)
    blocking = [
        p.signal
        for p in parse_nous(_SCANNER_WORLD).world.policies
        if getattr(p, "action", None) in ("block", "abort_cycle")
    ]
    doc = serialize_bundle(th, blocking, threshold_expr=threshold)
    derived = derive_disjunct_constraints(_SCANNER_WORLD, threshold)
    assert set(derived) == bundle_cert_keys(doc)


def test_bundle_against_wrong_source_fails() -> None:
    t = "amount > 5000 && risk_score > 30"
    doc = _bundle(t, t)
    assert _check(doc, t, "amount > 4999 && risk_score > 30") is False


_BOOL_NOUS = """world BoolLoanGovernance {
    law CostCeiling = $0.50 per cycle
    heartbeat = 10s
    cost_cap: COST_CAP USD
    max_ticks: 1
    policy BlockRisky {
        kind: "loan.decision"
        signal: amount > 4000 && risk_score > 2000
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

_BOOL_THRESHOLD = "amount > 4000 && risk_score > 2000"


def _nous_cli() -> str:
    exe = shutil.which("nous")
    if exe is None:
        pytest.skip("nous CLI not on PATH")
    return exe


def _run(args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120
    )


def _write_bool_nous(path: Path, cost_cap: str) -> None:
    path.write_text(
        _BOOL_NOUS.replace("COST_CAP", cost_cap), encoding="utf-8"
    )


def test_bool_dossier_e2e_offline_bundle_pass(tmp_path: Path) -> None:
    nous = _nous_cli()
    src = tmp_path / "bool.nous"
    _write_bool_nous(src, "0.50")
    man = tmp_path / "manifest.json"
    r = _run([
        nous, "verify", str(src), "--smt",
        "--coverage-threshold", _BOOL_THRESHOLD,
        "--manifest-out", str(man),
    ])
    assert r.returncode == 0, r.stderr
    assert "Coverage PROVEN" in r.stdout
    assert "Farkas bundle extracted" in r.stdout

    dossier = tmp_path / "dossier"
    r = _run([
        nous, "dossier", str(src), "--manifest", str(man),
        "--output", str(dossier),
    ])
    assert r.returncode == 0, r.stderr
    assert (dossier / "coverage.farkas.json").is_file()
    doc = json.loads(
        (dossier / "coverage.farkas.json").read_text(encoding="utf-8")
    )
    assert doc["fragment"] == BUNDLE_FRAGMENT

    r = _run([sys.executable, "verify_offline.py"], cwd=str(dossier))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "independently re-derived from the signed source" in r.stdout
    assert "bijection holds" in r.stdout
    assert "VERDICT: PASS" in r.stdout


def test_bool_chain_plus_bundle_e2e_pass(tmp_path: Path) -> None:  # __s126_realign_v1__
    nous = _nous_cli()
    src1 = tmp_path / "b1.nous"
    _write_bool_nous(src1, "0.50")
    man1 = tmp_path / "m1.json"
    r = _run([
        nous, "verify", str(src1), "--smt",
        "--coverage-threshold", _BOOL_THRESHOLD,
        "--manifest-out", str(man1),
    ])
    assert r.returncode == 0, r.stderr
    dossier1 = tmp_path / "d1"
    r = _run([
        nous, "dossier", str(src1), "--manifest", str(man1),
        "--output", str(dossier1),
    ])
    assert r.returncode == 0, r.stderr

    src2 = tmp_path / "b2.nous"
    _write_bool_nous(src2, "0.40")
    man2 = tmp_path / "m2.json"
    r = _run([
        nous, "verify", str(src2), "--smt",
        "--coverage-threshold", _BOOL_THRESHOLD,
        "--supersedes", str(man1),
        "--manifest-out", str(man2),
    ])
    assert r.returncode == 0, r.stderr

    dossier2 = tmp_path / "d2"
    r = _run([
        nous, "dossier", str(src2), "--manifest", str(man2),
        "--supersedes", str(dossier1), "--output", str(dossier2),
    ])
    assert r.returncode == 0, r.stderr
    assert (dossier2 / "chain" / "000_hop.farkas.json").is_file()
    r = _run([sys.executable, "verify_offline.py"], cwd=str(dossier2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hop containment verified" in r.stdout
    assert "VERDICT: PASS" in r.stdout
