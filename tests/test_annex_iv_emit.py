"""Integration tests for `nous dossier --annex-iv-map` emit wiring (S135 U3b).

Reuses the test_dossier.py proven_run pattern (cmd_verify mints a signed
manifest from the cost_cap template, then build_dossier). Asserts:
default-off emits nothing new (file-set baseline unchanged); the flag emits
annex_iv_map.json + a standalone verify_annex_iv_map.py; the emitted sidecar
verifies offline (subprocess PASS); and the orthogonal verify_offline.py
still passes (the sidecar does not perturb the cost/coverage verifier).

# __s135_annex_iv_emit_tests_v1__
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from annex_iv_map import verify_annex_iv_map
from cli_verify import cmd_verify
from dossier import build_dossier

TEMPLATE = (
    Path(__file__).parent.parent / "templates" / "cost_cap_with_souls.nous"
)

_BASELINE_FILES = {
    "source.nous",
    "manifest.json",
    "pricing.toml",
    "public_key.b64",
    "README.md",
    "verify_offline.py",
    "cost.farkas.json",  # __s170_leg2b_dossier_goldens_v1__
}


@pytest.fixture
def proven_run(tmp_path):
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
    return src


def _run(script: str, cwd: Path) -> int:
    proc = subprocess.run(
        [sys.executable, script], cwd=str(cwd), capture_output=True
    )
    return proc.returncode


def test_default_off_emits_no_sidecar(proven_run, tmp_path):
    output = tmp_path / "out"
    result = build_dossier(proven_run, output=output)
    assert set(result.files) == _BASELINE_FILES
    assert not (output / "annex_iv_map.json").exists()
    assert not (output / "verify_annex_iv_map.py").exists()


def test_flag_emits_sidecar_and_verifier(proven_run, tmp_path):
    output = tmp_path / "out"
    result = build_dossier(proven_run, output=output, annex_iv_map=True)
    assert set(result.files) == _BASELINE_FILES | {
        "annex_iv_map.json",
        "verify_annex_iv_map.py",
    }
    assert (output / "annex_iv_map.json").is_file()
    verifier = output / "verify_annex_iv_map.py"
    assert verifier.is_file()
    assert os.access(verifier, os.X_OK)
    assert verifier.read_text(encoding="utf-8").startswith(
        "#!/usr/bin/env python3"
    )


def test_emitted_sidecar_module_verify_passes(proven_run, tmp_path):
    output = tmp_path / "out"
    build_dossier(proven_run, output=output, annex_iv_map=True)
    ok, reason = verify_annex_iv_map(output)
    assert ok, reason


def test_emitted_sidecar_subprocess_passes(proven_run, tmp_path):
    output = tmp_path / "out"
    build_dossier(proven_run, output=output, annex_iv_map=True)
    assert _run("verify_annex_iv_map.py", output) == 0


def test_verify_offline_still_passes_with_sidecar(proven_run, tmp_path):
    output = tmp_path / "out"
    build_dossier(proven_run, output=output, annex_iv_map=True)
    assert _run("verify_offline.py", output) == 0


def test_sidecar_tamper_is_caught(proven_run, tmp_path):
    output = tmp_path / "out"
    build_dossier(proven_run, output=output, annex_iv_map=True)
    src_file = output / "source.nous"
    src_file.write_bytes(src_file.read_bytes() + b"\n# tamper\n")
    assert _run("verify_annex_iv_map.py", output) == 1
