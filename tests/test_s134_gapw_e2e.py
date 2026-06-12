"""S134 2c-3a end-to-end: produce -> package -> verify a gap-witness dossier.

The full loop with zero issuer trust:
  1. `nous verify --gap-witness` on the AML governance source with a coverage
     threshold the blocking net does NOT cover (amount > 5000 against a net
     whose effective blocked region is amount > 10000) -> coverage refuted ->
     a signed gap-witness manifest + sha-bound coverage.gapwitness.json.
  2. build_dossier packages it: the witness sidecar is carried under its sha
     gate and the emitted verify_offline.py is the gap-witness verifier
     (selected by the SIGNED source_kind discriminator, axiom 8).
  3. The emitted verifier is run as a SUBPROCESS in the dossier directory --
     no NOUS install on its path -- and must exit 0 with VERDICT: REFUTATION,
     re-deriving the gap from the signed source by rational arithmetic alone.

Plus the two dossier-level refusals (gap-witness + prior_digest; gap-witness
+ rekor anchor) and sidecar-tamper detection at package time.

BOUNDARY: a verified gap-witness proves a coverage gap EXISTS at the carried
point; it is NOT a compliance pass, NOT misbehavior, NOT unique or maximal.
# __s134_gapw_e2e_test_v1__
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier, DossierError

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)

UNCOVERED_THRESHOLD = "amount > 5000"


class _Args:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None
    supersedes = None
    chain_coverage = None
    gap_witness = False
    coverage_threshold = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _issue(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    mout = tmp_path / "source.manifest.json"
    args = _Args(
        file=str(src),
        manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        coverage_threshold=UNCOVERED_THRESHOLD,
        gap_witness=True,
    )
    assert cmd_verify(args) == 0
    assert mout.is_file()
    assert (tmp_path / "coverage.gapwitness.json").is_file()
    return src


def test_gap_witness_dossier_verifies_offline(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    out = tmp_path / "out"
    result = build_dossier(
        src, manifest=tmp_path / "source.manifest.json", output=out
    )

    assert "coverage.gapwitness.json" in result.files
    assert "coverage.farkas.json" not in result.files
    assert "coverage.smt2" not in result.files

    vtext = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert "gap-witness" in vtext
    assert "REFUTATION" in vtext

    proc = subprocess.run(
        [sys.executable, str(out / "verify_offline.py")],
        capture_output=True,
        text=True,
        cwd=str(out),
    )
    assert proc.returncode == 0, (
        "stdout=" + proc.stdout + " stderr=" + proc.stderr
    )
    assert "VERDICT: REFUTATION" in proc.stdout
    assert "result: gap-demonstrated" in proc.stdout


def test_gap_witness_verifier_rejects_tampered_witness(
    tmp_path: Path,
) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    out = tmp_path / "out"
    build_dossier(
        src, manifest=tmp_path / "source.manifest.json", output=out
    )
    gw = out / "coverage.gapwitness.json"
    doc = json.loads(gw.read_text(encoding="utf-8"))
    doc["point"] = {"amount": "999999999"}
    gw.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n",
                  encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(out / "verify_offline.py")],
        capture_output=True,
        text=True,
        cwd=str(out),
    )
    assert proc.returncode == 1


def test_build_dossier_refuses_tampered_gapwitness(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    (tmp_path / "coverage.gapwitness.json").write_text(
        "// tampered\n", encoding="utf-8"
    )
    with pytest.raises(DossierError):
        build_dossier(
            src, manifest=tmp_path / "source.manifest.json",
            output=tmp_path / "out",
        )


def test_build_dossier_refuses_gapwitness_with_anchor(
    tmp_path: Path,
) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _issue(tmp_path)
    with pytest.raises(DossierError):
        build_dossier(
            src, manifest=tmp_path / "source.manifest.json",
            output=tmp_path / "out", anchor="rekor",
        )
