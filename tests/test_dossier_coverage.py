"""Coverage-in-dossier tests (S115 P3a). 7 files; file-sha gate; unsat."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import build_dossier, DossierError

TEMPLATE = Path(__file__).resolve().parent.parent / (
    "aml_transaction_governance.nous"
)


def _proven_coverage_run(tmp_path: Path):
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
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
        coverage_threshold = "amount > 10000"
        no_lint = True
        lint_strict = False
        lint_error_on = None

    rc = cmd_verify(Args())
    assert rc == 0
    assert mout.is_file()
    assert (tmp_path / "coverage.smt2").is_file()
    return src, mout


def test_dossier_with_coverage_has_eight_files(tmp_path):  # __s116_dossier_farkas_v1__
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    out = tmp_path / "out"
    result = build_dossier(src, manifest=manifest_out, output=out)
    expected = {
        "source.nous", "manifest.json", "pricing.toml",
        "public_key.b64", "README.md", "verify_offline.py",
        "coverage.smt2", "coverage.farkas.json",
    }
    assert set(result.files) == expected
    for f in expected:
        assert (out / f).is_file()


def test_dossier_smt2_sha_matches_manifest(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    out = tmp_path / "out"
    build_dossier(src, manifest=manifest_out, output=out)
    doc = json.loads((out / "manifest.json").read_text())
    file_sha = hashlib.sha256(
        (out / "coverage.smt2").read_bytes()
    ).hexdigest()
    assert file_sha == doc["coverage_smt2_sha256"]


def test_dossier_rejects_tampered_coverage(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    tampered = tmp_path / "coverage.smt2"
    tampered.write_text("(assert false)\n(check-sat)\n", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=manifest_out, output=out)


def test_coverage_verifier_template_selected(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    out = tmp_path / "out"
    build_dossier(src, manifest=manifest_out, output=out)
    vtext = (out / "verify_offline.py").read_text()
    assert "coverage.smt2 sha256" in vtext  # __s116_dossier_farkas_v1__
    assert "Farkas certificate verified by rational arithmetic" in vtext


def test_dossier_farkas_sha_matches_manifest(tmp_path):  # __s116_dossier_farkas_v1__
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    out = tmp_path / "out"
    build_dossier(src, manifest=manifest_out, output=out)
    doc = json.loads((out / "manifest.json").read_text())
    file_sha = hashlib.sha256(
        (out / "coverage.farkas.json").read_bytes()
    ).hexdigest()
    assert file_sha == doc["coverage_farkas_sha256"]


def test_dossier_rejects_tampered_farkas(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    tampered = tmp_path / "coverage.farkas.json"
    tampered.write_text('{"constraints": [], "multipliers": []}\n',
                        encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=manifest_out, output=out)


def test_farkas_verifier_is_stdlib_arithmetic(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src, manifest_out = _proven_coverage_run(tmp_path)
    out = tmp_path / "out"
    build_dossier(src, manifest=manifest_out, output=out)
    vtext = (out / "verify_offline.py").read_text()
    assert "from fractions import Fraction" in vtext
    assert "_check_serialized" in vtext
    assert "coverage.farkas.json sha256" in vtext
