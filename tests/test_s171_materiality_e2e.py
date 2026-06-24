"""S171 Leg 4d end-to-end: package a materiality classification into a
dossier and run the emitted verifier as a subprocess.

The honest gradient travels with the dossier:
  1. A normal signed manifest is produced (cmd_verify, with a proven
     coverage claim so the selected verifier is the Farkas/bundle template).
  2. A materiality.json classification is attached: written next to the
     manifest, sha-pinned into a re-signed manifest field (materiality_sha256,
     S171 Leg 4a), using the SAME key so the verifier's canonical-body
     re-derivation still authenticates the signature.
  3. build_dossier carries materiality.json under its sha gate (Leg 4b) and
     splices _check_materiality into the emitted verifier (Leg 4c-2).
  4. The verifier is run as a SUBPROCESS in the dossier directory -- no NOUS
     install on its path -- and must authenticate the classification (sha
     gate + schema) and print the honest route. It PROVES NOTHING about
     materiality; the verdict is a classification, the route points at the
     proof leg (or its absence).

Refusals covered:
  - tampering materiality.json after signing is caught at package time
    (build_dossier, Leg 4b sha gate) and at verify time (the spliced check).
  - a gap-witness (refutation) dossier that declares materiality_sha256 is
    refused at package time (Leg 4c-1 refuse-gate; incoherent over a
    refutation artifact).

# __s171_materiality_e2e_v1__
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier, DossierError
from manifest import (
    load_or_create_keypair,
    manifest_json,
    parse_manifest_json,
    sign_manifest,
)

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)

COVERED_THRESHOLD = "amount > 10000"
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


def _materiality_doc(verdict: str) -> bytes:
    return json.dumps(
        {
            "verdict": verdict,
            "threshold_pct": 10.0,
            "cost_delta_pct": 25.0 if verdict == "material" else 0.0,
            "reasons": (
                ["cost delta +25.0% exceeds threshold 10.0%"]
                if verdict == "material"
                else []
            ),
            "route": "informational",
            "basis": (
                "classification, not proof; not an Article 25 determination"
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _proven_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    mout = tmp_path / "source.manifest.json"
    key_path = tmp_path / "signing.key"
    args = _Args(
        file=str(src),
        manifest_out=str(mout),
        key_path=str(key_path),
        coverage_threshold=COVERED_THRESHOLD,
    )
    assert cmd_verify(args) == 0
    assert mout.is_file()
    return src, mout, key_path


def _attach_materiality(
    mout: Path, key_path: Path, verdict: str
) -> bytes:
    mat_bytes = _materiality_doc(verdict)
    (mout.parent / "materiality.json").write_bytes(mat_bytes)
    mat_sha = hashlib.sha256(mat_bytes).hexdigest()
    manifest, _sig, _pub = parse_manifest_json(mout.read_text())
    manifest = dataclasses.replace(manifest, materiality_sha256=mat_sha)
    private, public, _path = load_or_create_keypair(key_path)
    sig = sign_manifest(manifest, private)
    mout.write_text(manifest_json(manifest, sig, public))
    return mat_bytes


def _gap_witness_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    mout = tmp_path / "source.manifest.json"
    key_path = tmp_path / "signing.key"
    args = _Args(
        file=str(src),
        manifest_out=str(mout),
        key_path=str(key_path),
        coverage_threshold=UNCOVERED_THRESHOLD,
        gap_witness=True,
    )
    assert cmd_verify(args) == 0
    assert mout.is_file()
    return src, mout, key_path


def _run_verifier(out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(out / "verify_offline.py")],
        capture_output=True,
        text=True,
    )


def test_material_dossier_verifier_authenticates_and_routes(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key_path = _proven_manifest(tmp_path)
    mat_bytes = _attach_materiality(mout, key_path, "material")
    out = tmp_path / "out"
    result = build_dossier(src, manifest=mout, output=out)

    assert "materiality.json" in result.files
    carried = (out / "materiality.json").read_bytes()
    assert carried == mat_bytes
    doc = json.loads((out / "manifest.json").read_text())
    assert (
        hashlib.sha256(carried).hexdigest() == doc["materiality_sha256"]
    )

    vtext = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert "_check_materiality" in vtext
    assert "CLASSIFICATION, not a proof" in vtext

    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "materiality classification authenticated" in proc.stdout
    assert "MATERIAL change" in proc.stdout
    # non-chain dossier: no envelope-binding proof leg is carried
    assert "supersedes" in proc.stdout


def test_minor_dossier_verifier_routes_to_article_12(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key_path = _proven_manifest(tmp_path)
    _attach_materiality(mout, key_path, "minor")
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)

    proc = _run_verifier(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "MINOR revision" in proc.stdout
    assert "Article 12" in proc.stdout


def test_tampered_materiality_refused_at_package_time(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key_path = _proven_manifest(tmp_path)
    _attach_materiality(mout, key_path, "material")
    # tamper the sidecar AFTER it was sha-pinned into the signed manifest
    (mout.parent / "materiality.json").write_bytes(b'{"verdict":"minor"}')
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=mout, output=out)


def test_verifier_detects_tampered_materiality_post_package(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key_path = _proven_manifest(tmp_path)
    _attach_materiality(mout, key_path, "material")
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    # tamper the carried sidecar in the packaged dossier
    (out / "materiality.json").write_bytes(b'{"verdict":"minor"}')
    proc = _run_verifier(out)
    assert proc.returncode == 1
    assert "does not match" in proc.stdout + proc.stderr


def test_no_materiality_verifier_has_no_check(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, _key = _proven_manifest(tmp_path)
    out = tmp_path / "out"
    result = build_dossier(src, manifest=mout, output=out)
    assert "materiality.json" not in result.files
    vtext = (out / "verify_offline.py").read_text(encoding="utf-8")
    assert "_check_materiality" not in vtext


def test_gap_witness_with_materiality_refused(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, mout, key_path = _gap_witness_manifest(tmp_path)
    mat_bytes = _materiality_doc("material")
    (mout.parent / "materiality.json").write_bytes(mat_bytes)
    mat_sha = hashlib.sha256(mat_bytes).hexdigest()
    manifest, _sig, _pub = parse_manifest_json(mout.read_text())
    assert manifest.source_kind == "gap-witness"
    manifest = dataclasses.replace(manifest, materiality_sha256=mat_sha)
    private, public, _path = load_or_create_keypair(key_path)
    sig = sign_manifest(manifest, private)
    mout.write_text(manifest_json(manifest, sig, public))
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=mout, output=out)
