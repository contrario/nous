"""S125 chain + bundle composition (Option 3 of the design freeze).

The current link's coverage may be a Farkas DNF bundle (boolean blocking
net); it is proven by re-derivation from the signed source with zero issuer
trust. Prior links contribute only their SIGNED threshold inequality for
region monotonicity (v1 constraints[0] or bundle threshold_constraint). A
boolean-THRESHOLD bundle carries no single-comparison threshold_constraint:
it is refused at issuance (current link or carried prior) and, defensively,
by the emitted verifier's monotonicity reader.

Structural note for the PASS case: a single-comparison threshold yields a
disjunctive-linear bundle only when a blocking signal carries an AND (its
negation is a disjunction). A primary single-comparison block covers the
threshold (proven); a secondary AND/band block forces the bundle structure.

# __s125_chain_bundle_test_v1__
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import dossier

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

_SCALAR_THRESHOLD = "amount > 4000"
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


def _write(path: Path, cost_cap: str) -> None:
    path.write_text(_SRC.replace("COST_CAP", cost_cap), encoding="utf-8")


def test_chain_bundle_scalar_threshold_e2e_pass(tmp_path: Path) -> None:
    nous = _nous_cli()
    s1 = tmp_path / "s1.nous"
    _write(s1, "0.50")
    m1 = tmp_path / "m1.json"
    r = _run([
        nous, "verify", str(s1), "--smt",
        "--coverage-threshold", _SCALAR_THRESHOLD, "--manifest-out", str(m1),
    ])
    assert r.returncode == 0, r.stderr
    assert "Coverage PROVEN" in r.stdout
    assert "Farkas bundle extracted" in r.stdout

    d1 = tmp_path / "d1"
    r = _run([
        nous, "dossier", str(s1), "--manifest", str(m1), "--output", str(d1),
    ])
    assert r.returncode == 0, r.stderr
    far1 = json.loads((d1 / "coverage.farkas.json").read_text())
    assert far1["fragment"] == "disjunctive-linear-bundle"
    assert isinstance(far1.get("threshold_constraint"), dict)

    s2 = tmp_path / "s2.nous"
    _write(s2, "0.40")
    m2 = tmp_path / "m2.json"
    r = _run([
        nous, "verify", str(s2), "--smt",
        "--coverage-threshold", _SCALAR_THRESHOLD, "--supersedes", str(m1),
        "--manifest-out", str(m2),
    ])
    assert r.returncode == 0, r.stderr

    d2 = tmp_path / "d2"
    r = _run([
        nous, "dossier", str(s2), "--manifest", str(m2),
        "--supersedes", str(d1), "--output", str(d2),
    ])
    assert r.returncode == 0, r.stderr
    vtext = (d2 / "verify_offline.py").read_text(encoding="utf-8")
    assert "__s125_chain_bundle_walk_v1__" in vtext
    assert (d2 / "chain").is_dir()

    r = _run([sys.executable, "verify_offline.py"], cwd=str(d2))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "independently re-derived from the signed source" in r.stdout
    assert "bijection holds" in r.stdout
    assert "chain walk verified" in r.stdout
    assert "coverage-region monotonicity verified" in r.stdout
    assert "VERDICT: PASS" in r.stdout


def test_chain_over_boolean_threshold_prior_refused(tmp_path: Path) -> None:
    nous = _nous_cli()
    s0 = tmp_path / "s0.nous"
    _write(s0, "0.50")
    m0 = tmp_path / "m0.json"
    r = _run([
        nous, "verify", str(s0), "--smt",
        "--coverage-threshold", _BOOL_THRESHOLD, "--manifest-out", str(m0),
    ])
    assert r.returncode == 0, r.stderr
    d0 = tmp_path / "d0"
    r = _run([
        nous, "dossier", str(s0), "--manifest", str(m0), "--output", str(d0),
    ])
    assert r.returncode == 0, r.stderr
    far0 = json.loads((d0 / "coverage.farkas.json").read_text())
    assert far0["fragment"] == "disjunctive-linear-bundle"
    assert far0.get("threshold_constraint") is None

    s2 = tmp_path / "s2.nous"
    _write(s2, "0.40")
    m2 = tmp_path / "m2.json"
    r = _run([
        nous, "verify", str(s2), "--smt",
        "--coverage-threshold", _SCALAR_THRESHOLD, "--supersedes", str(m0),
        "--manifest-out", str(m2),
    ])
    assert r.returncode == 0, r.stderr

    d2 = tmp_path / "d2"
    r = _run([
        nous, "dossier", str(s2), "--manifest", str(m2),
        "--supersedes", str(d0), "--output", str(d2),
    ])
    assert r.returncode != 0
    assert "boolean-threshold Farkas bundle not supported" in (
        r.stdout + r.stderr
    )
    assert "carried prior link" in (r.stdout + r.stderr)


def test_authenticated_threshold_fragment_branch(tmp_path: Path) -> None:
    ns: dict = {
        "__name__": "vcb_unit",
        "__file__": str(tmp_path / "verify_offline.py"),
    }
    exec(
        compile(dossier.VERIFY_OFFLINE_PY_CHAIN_BUNDLE, "<merged>", "exec"),
        ns,
    )
    auth = ns["_authenticated_threshold"]
    chain = tmp_path / "chain"
    chain.mkdir()
    far = chain / "000_coverage.farkas.json"

    def _put(doc: dict) -> str:
        b = json.dumps(doc).encode("utf-8")
        far.write_bytes(b)
        return hashlib.sha256(b).hexdigest()

    tc = {"coeffs": {"amount": "-1", "": "4000"}, "strict": True}
    sha = _put({"fragment": "disjunctive-linear-bundle", "certs": [],
                "threshold_constraint": tc})
    st, val = auth("000_manifest.json", {"coverage_farkas_sha256": sha})
    assert st == "has"
    assert val == tc

    sha = _put({"fragment": "disjunctive-linear-bundle", "certs": []})
    st, _val = auth("000_manifest.json", {"coverage_farkas_sha256": sha})
    assert st == "refuse"

    v1 = {"coeffs": {"x": "1"}, "strict": False}
    sha = _put({"constraints": [v1], "multipliers": ["1"]})
    st, val = auth("000_manifest.json", {"coverage_farkas_sha256": sha})
    assert st == "has"
    assert val == v1
