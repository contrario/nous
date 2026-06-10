"""S126 hop-containment adversarial e2e tests.

A chained bundle dossier carries one unsigned, self-certifying hop bundle
per (has, has) hop. The obligation T_prev AND NOT(T_cur) is re-derived by
the emitted verifier from the two sha-gated threshold expressions, never
from the hop bundle itself. These tests prove the fail-closed surface:
region regression refuses at ISSUANCE; a deleted hop file fails offline;
a forged multiplier fails arithmetic; an unexpected hop file refuses; and
tampering the hop doc's own expression fields changes NOTHING (zero hop-doc
authority -- the positive control of the trust model).

# __s126_hop_e2e_test_v1__
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = """world ScalarThreshBoolNet {
    law CostCeiling = $0.50 per cycle
    heartbeat = 10s
    cost_cap: COST_CAP USD
    max_ticks: 1
    policy BlockHighAmount {
        kind: "loan.decision"
        signal: amount > 4000
        weight: 10.0
        action: block
    }
    policy BlockRiskBand {
        kind: "loan.decision"
        signal: risk_score > 2000 && risk_score < 9000
        weight: 8.0
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

_THRESHOLD = "amount > 4000"


def _nous_cli() -> str:
    exe = shutil.which("nous")
    if exe is None:
        pytest.skip("nous CLI not on PATH")
    return exe


def _run(args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120
    )


def _write(path: Path, cost_cap: str) -> None:
    path.write_text(_SRC.replace("COST_CAP", cost_cap), encoding="utf-8")


def _build_link(
    nous: str,
    tmp: Path,
    name: str,
    cost_cap: str,
    threshold: "str | None",
    prev_manifest: "Path | None",
    prev_dossier: "Path | None",
) -> "tuple[Path, Path]":
    src = tmp / (name + ".nous")
    _write(src, cost_cap)
    man = tmp / (name + ".json")
    vargs = [nous, "verify", str(src), "--smt", "--manifest-out", str(man)]
    if threshold is not None:
        vargs += ["--coverage-threshold", threshold]
    if prev_manifest is not None:
        vargs += ["--supersedes", str(prev_manifest)]
    r = _run(vargs)
    assert r.returncode == 0, r.stderr
    dout = tmp / (name + "_d")
    dargs = [nous, "dossier", str(src), "--manifest", str(man),
             "--output", str(dout)]
    if prev_dossier is not None:
        dargs += ["--supersedes", str(prev_dossier)]
    r = _run(dargs)
    assert r.returncode == 0, r.stderr
    return man, dout


def _build_pass_chain(nous: str, tmp: Path) -> Path:
    m1, d1 = _build_link(nous, tmp, "s1", "0.50", _THRESHOLD, None, None)
    _m2, d2 = _build_link(nous, tmp, "s2", "0.40", _THRESHOLD, m1, d1)
    assert (d2 / "chain" / "000_hop.farkas.json").is_file()
    return d2


def test_hop_regression_refused_at_issuance(tmp_path: Path) -> None:
    nous = _nous_cli()
    m1, d1 = _build_link(
        nous, tmp_path, "s1", "0.50", "amount > 4000", None, None
    )
    src2 = tmp_path / "s2.nous"
    _write(src2, "0.40")
    m2 = tmp_path / "m2.json"
    r = _run([
        nous, "verify", str(src2), "--smt",
        "--coverage-threshold", "amount > 5000",
        "--supersedes", str(m1), "--manifest-out", str(m2),
    ])
    assert r.returncode == 0, r.stderr
    d2 = tmp_path / "d2"
    r = _run([
        nous, "dossier", str(src2), "--manifest", str(m2),
        "--supersedes", str(d1), "--output", str(d2),
    ])
    assert r.returncode != 0
    assert "hop containment REFUSED" in (r.stdout + r.stderr)


def test_hop_file_deleted_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_pass_chain(nous, tmp_path)
    (d2 / "chain" / "000_hop.farkas.json").unlink()
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "hop containment bundle missing" in (r.stdout + r.stderr)


def test_hop_multiplier_forged_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_pass_chain(nous, tmp_path)
    hop_path = d2 / "chain" / "000_hop.farkas.json"
    doc = json.loads(hop_path.read_text(encoding="utf-8"))
    doc["certs"][0]["multipliers"][0] = "-1"
    hop_path.write_text(json.dumps(doc), encoding="utf-8")
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "REGION REGRESSION or invalid hop proof" in (
        r.stdout + r.stderr
    )


def test_unexpected_hop_file_fails_offline(tmp_path: Path) -> None:
    nous = _nous_cli()
    m1, d1 = _build_link(nous, tmp_path, "s1", "0.50", None, None, None)
    _m2, d2 = _build_link(
        nous, tmp_path, "s2", "0.40", _THRESHOLD, m1, d1
    )
    hop_path = d2 / "chain" / "000_hop.farkas.json"
    assert not hop_path.is_file()
    hop_path.write_text("{}", encoding="utf-8")
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode != 0
    assert "unexpected hop bundle" in (r.stdout + r.stderr)


def test_hop_doc_expr_fields_carry_no_authority(tmp_path: Path) -> None:
    nous = _nous_cli()
    d2 = _build_pass_chain(nous, tmp_path)
    hop_path = d2 / "chain" / "000_hop.farkas.json"
    doc = json.loads(hop_path.read_text(encoding="utf-8"))
    doc["prev_threshold_expr"] = "amount > 999999"
    doc["cur_threshold_expr"] = "risk_score < 1"
    hop_path.write_text(json.dumps(doc), encoding="utf-8")
    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hop containment verified" in r.stdout
    assert "VERDICT: PASS" in r.stdout
