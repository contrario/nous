"""S171 Leg 6b: producer functional test -- `nous verify --materiality-against`.

Exercises the wired producer end to end through the real cmd_verify:
  - --materiality-against PRIOR classifies the current build vs PRIOR and emits
    a sha-pinned materiality.json next to the manifest; build_dossier carries
    it and the emitted verifier authenticates the verdict and routes it.
  - minor (identical prior, default threshold) -> Article 12 route.
  - material (identical prior, threshold 0.0 so cost delta 0.0 >= 0.0) ->
    supersedes route.
  - --materiality-against + --gap-witness -> refused, no manifest written.
  - omitted -> no materiality.json, no manifest field (byte-identical path).

# __s171_materiality_producer_v1__
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier

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
    materiality_against = None
    materiality_threshold_pct = 10.0

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _prior_and_current(tmp_path: Path) -> tuple[Path, Path]:
    prior = tmp_path / "prior.nous"
    prior.write_bytes(TEMPLATE.read_bytes())
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    return prior, src


def _run_verifier(out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(out / "verify_offline.py")],
        capture_output=True,
        text=True,
    )


def test_producer_minor_emits_and_dossier_routes_article_12(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    prior, src = _prior_and_current(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(
        _Args(
            file=str(src),
            manifest_out=str(mout),
            key_path=str(tmp_path / "signing.key"),
            materiality_against=str(prior),
        )
    )
    assert rc == 0
    mat = tmp_path / "materiality.json"
    assert mat.is_file()
    verdict = json.loads(mat.read_text())
    assert verdict["verdict"] == "minor"
    doc = json.loads(mout.read_text())
    assert (
        hashlib.sha256(mat.read_bytes()).hexdigest()
        == doc["materiality_sha256"]
    )

    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "materiality classification authenticated" in proc.stdout
    assert "Article 12" in proc.stdout


def test_producer_material_via_zero_threshold_routes_supersedes(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    prior, src = _prior_and_current(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(
        _Args(
            file=str(src),
            manifest_out=str(mout),
            key_path=str(tmp_path / "signing.key"),
            materiality_against=str(prior),
            materiality_threshold_pct=0.0,
        )
    )
    assert rc == 0
    verdict = json.loads((tmp_path / "materiality.json").read_text())
    assert verdict["verdict"] == "material"

    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "MATERIAL change" in proc.stdout
    assert "supersedes" in proc.stdout


def test_producer_refused_with_gap_witness(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    prior, src = _prior_and_current(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(
        _Args(
            file=str(src),
            manifest_out=str(mout),
            key_path=str(tmp_path / "signing.key"),
            coverage_threshold=UNCOVERED_THRESHOLD,
            gap_witness=True,
            materiality_against=str(prior),
        )
    )
    assert rc == 1
    assert not (tmp_path / "materiality.json").is_file()


def test_producer_omitted_is_byte_identical_path(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    _prior, src = _prior_and_current(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(
        _Args(
            file=str(src),
            manifest_out=str(mout),
            key_path=str(tmp_path / "signing.key"),
        )
    )
    assert rc == 0
    assert not (tmp_path / "materiality.json").is_file()
    doc = json.loads(mout.read_text())
    assert "materiality_sha256" not in doc
