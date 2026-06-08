"""S121 monotonicity verifier end-to-end tests.  __s121_monotonicity_verifier_test_v1__

Drives the real producer + build_dossier on a custom two-axis fixture and
runs the EMITTED verify_offline.py as a subprocess, asserting the
coverage-region monotonicity verdicts. Zero issuer trust: the verifier
re-derives containment from the two authenticated endpoint
coverage.farkas.json certs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier, VERIFY_OFFLINE_PY_CHAIN
import coverage_farkas

FIXTURE = """world TwoAxisGovernance {
    law CostCeiling = $0.50 per cycle
    heartbeat = 10s
    cost_cap: 0.50 USD
    max_ticks: 1
    policy BlockLargeAmount {
        kind: "transaction.screen"
        signal: amount > 10000
        weight: 10.0
        action: block
    }
    policy BlockHighRisk {
        kind: "transaction.screen"
        signal: risk_score > 0.8
        weight: 9.0
        action: block
    }
    policy LogAllScreens {
        kind: "transaction.screen"
        signal: true
        weight: 1.0
        action: log_only
    }
}
message Transaction {
    transaction_id: string
    amount: float
    risk_score: float
    country: string
}
message ScreenResult {
    transaction_id: string
    decision: string
    reason: string
    source: SoulRef
}
soul Screener {
    mind: claude-haiku-4-5 @ Tier0A
    tokens: input = 500 output = 200
    senses: [http_get]
    memory {
        screened: int = 0
    }
    instinct {
        let txn = listen Intake::Transaction
        guard txn != null else sleep 5s
        speak ScreenResult(transaction_id: txn.transaction_id, decision: "screened", reason: "evaluated", source: self)
        remember screened = screened + 1
    }
    heal {
        on timeout => retry(2, timeout)
        on api_error => retry(2, api_error)
    }
}
"""


def _produce(
    tmp_path: Path,
    *,
    marker: bytes,
    threshold,
    supersedes=None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "source.nous"
    src.write_bytes(FIXTURE.encode("utf-8") + marker)
    mout = tmp_path / "source.manifest.json"

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(mout)
        key_path = str(tmp_path / "signing.key")
        smt_margin = 0
        coverage_threshold = threshold
        no_lint = True
        lint_strict = False
        lint_error_on = None

    Args.supersedes = supersedes
    rc = cmd_verify(Args())
    assert rc == 0, "producer failed (rc=" + str(rc) + ") for " + str(tmp_path)
    return src, mout


def _run_verifier(dossier_dir):
    return subprocess.run(
        [sys.executable, str(dossier_dir / "verify_offline.py")],
        capture_output=True,
        text=True,
        cwd=str(dossier_dir),
    )


def _chain(tmp_path, thresholds, markers):
    outs = []
    prev_mout = None
    prev_out = None
    for i, (thr, mk) in enumerate(zip(thresholds, markers)):
        src, mout = _produce(
            tmp_path / ("p" + str(i)),
            marker=mk,
            threshold=thr,
            supersedes=(str(prev_mout) if prev_mout is not None else None),
        )
        out = tmp_path / ("d" + str(i))
        build_dossier(
            src, manifest=mout, output=out,
            supersedes=(prev_out if prev_out is not None else None),
        )
        outs.append(out)
        prev_mout = mout
        prev_out = out
    return outs


def test_monotonic_pass(tmp_path: Path) -> None:
    outs = _chain(
        tmp_path,
        ["amount > 15000", "amount > 10000"],
        [b"\x0a# g\x0a", b"\x0a# v1 loosen\x0a"],
    )
    proc = _run_verifier(outs[-1])
    assert proc.returncode == 0, "stdout=" + proc.stdout + " stderr=" + proc.stderr
    assert "monotonicity verified" in proc.stdout


def test_region_regression_caught(tmp_path: Path) -> None:
    outs = _chain(
        tmp_path,
        ["amount > 10000", "amount > 15000"],
        [b"\x0a# g\x0a", b"\x0a# v1 tighten\x0a"],
    )
    proc = _run_verifier(outs[-1])
    assert proc.returncode == 1
    assert "REGION REGRESSION" in proc.stderr


def test_incomparable_caught(tmp_path: Path) -> None:
    outs = _chain(
        tmp_path,
        ["amount > 15000", "risk_score > 0.9"],
        [b"\x0a# g\x0a", b"\x0a# v1 axis\x0a"],
    )
    proc = _run_verifier(outs[-1])
    assert proc.returncode == 1
    assert "INCOMPARABLE" in proc.stderr


def test_coverage_vanished_caught(tmp_path: Path) -> None:
    gsrc, gmout = _produce(
        tmp_path / "g", marker=b"\x0a# g\x0a", threshold="amount > 10000"
    )
    out0 = tmp_path / "d0"
    build_dossier(gsrc, manifest=gmout, output=out0)

    c = tmp_path / "c"
    c.mkdir()
    csrc = c / "source.nous"
    csrc.write_bytes(FIXTURE.encode("utf-8") + b"\x0a# v1 nocov\x0a")
    cmout = c / "source.manifest.json"

    class Args:
        file = str(csrc)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = str(cmout)
        key_path = str(c / "signing.key")
        smt_margin = 0
        coverage_threshold = None
        no_lint = True
        lint_strict = False
        lint_error_on = None
        supersedes = str(gmout)

    assert cmd_verify(Args()) == 0
    out1 = tmp_path / "d1"
    build_dossier(csrc, manifest=cmout, output=out1, supersedes=out0)

    proc = _run_verifier(out1)
    assert proc.returncode == 1
    assert "VANISHED" in proc.stderr


def test_farkas_tamper_caught(tmp_path: Path) -> None:
    outs = _chain(
        tmp_path,
        ["amount > 15000", "amount > 10000"],
        [b"\x0a# g\x0a", b"\x0a# v1\x0a"],
    )
    far = outs[-1] / "chain" / "000_coverage.farkas.json"
    doc = json.loads(far.read_text(encoding="utf-8"))
    doc["constraints"][0]["coeffs"][""] = "999999"
    far.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    proc = _run_verifier(outs[-1])
    assert proc.returncode == 1
    assert "sha256 does not match" in proc.stderr


def test_embedded_region_contains_matches_module() -> None:
    import inspect

    mod_src = inspect.getsource(coverage_farkas.region_contains)
    for token in (
        "var_union = sorted(",
        "if (av == 0) != (bv == 0):",
        "t = _f(cb, pivot) / _f(ca, pivot)",
        "if t <= 0:",
        "if _f(cb, v) != t * _f(ca, v):",
        "if const_b > scaled_a:",
        "if const_b == scaled_a and (sa is False) and (sb is True):",
    ):
        assert token in mod_src, "module missing invariant: " + token
        assert token in VERIFY_OFFLINE_PY_CHAIN, (
            "emitted template missing invariant: " + token
        )
