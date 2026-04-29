"""
Tests for `nous dossier` command (v4.14.0).

# __session64_dossier_v1__
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from cli_verify import cmd_verify
from dossier import DossierError, build_dossier


TEMPLATE = (
    Path(__file__).parent.parent
    / "templates"
    / "cost_cap_with_souls.nous"
)


@pytest.fixture
def proven_run(tmp_path):
    """Fresh tmp_path with source.nous + signed manifest."""
    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = None
        key_path = None
        smt_margin = 0
        no_lint = True
        lint_strict = False
        lint_error_on = None

    rc = cmd_verify(Args())
    assert rc == 0
    manifest = src.with_suffix(".manifest.json")
    assert manifest.is_file()
    return src, manifest


def test_build_dossier_happy_path(proven_run, tmp_path):
    src, _ = proven_run
    output = tmp_path / "out"
    result = build_dossier(src, output=output)
    assert result.output_dir == output.resolve()
    expected = {
        "source.nous",
        "manifest.json",
        "pricing.toml",
        "public_key.b64",
        "README.md",
        "verify_offline.py",
    }
    assert set(result.files) == expected
    for f in expected:
        assert (output / f).is_file()


def test_dossier_readme_has_annex_iv_mapping(proven_run, tmp_path):
    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(src, output=output)
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "Annex IV" in readme
    assert "Article 9" in readme
    assert "Ed25519" in readme
    assert "verify_offline.py" in readme
    assert "1. General description" in readme
    assert "9. Post-market monitoring" in readme


def test_dossier_verify_script_is_executable(proven_run, tmp_path):
    src, _ = proven_run
    output = tmp_path / "out"
    build_dossier(src, output=output)
    verify = output / "verify_offline.py"
    assert os.access(verify, os.X_OK)
    text = verify.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "Ed25519PublicKey" in text


def test_dossier_refuses_tampered_source(proven_run, tmp_path):
    src, manifest = proven_run
    src.write_text(
        src.read_text(encoding="utf-8") + "// tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(DossierError, match="source.sha256 mismatch"):
        build_dossier(src, output=tmp_path / "out")


def test_dossier_refuses_tampered_manifest(proven_run, tmp_path):
    src, manifest = proven_run
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["world_name"] = "Tampered"
    manifest.write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    with pytest.raises(DossierError, match="signature does NOT"):
        build_dossier(src, output=tmp_path / "out")


def test_dossier_refuses_nonempty_output(proven_run, tmp_path):
    src, _ = proven_run
    output = tmp_path / "out"
    output.mkdir()
    (output / "stale_file").write_text("x")
    with pytest.raises(DossierError, match="not empty"):
        build_dossier(src, output=output)
