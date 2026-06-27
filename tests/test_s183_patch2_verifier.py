from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from continuity_checkpoint import (
    build_continuity_checkpoint,
    build_continuity_proof,
)
from continuity_verifier import emit_continuity_verifier
from test_s178_checkpoint_leg import _build_priced_ledger, _keys

_CAPS9 = ["0.10", "0.11", "0.12", "0.13", "0.14",
          "0.15", "0.16", "0.17", "0.18"]

_EVIDENCES = (
    "EVIDENCES: Cryptographic consistency proof verified. The ledger is "
    "append-only between tree size 5 and 9. No retroactive rollback, "
    "rewrite, or truncation occurred."
)


def _ledger9(tmp_path: Path) -> Path:
    op, cp = _keys(tmp_path)
    return _build_priced_ledger(tmp_path, op, cp, _CAPS9)


def _prefix_dir(tmp_path: Path, ledger: Path, k: int, name: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    for i in range(k):
        leaf = str(i).zfill(3)
        shutil.copytree(ledger / leaf, d / leaf)
    return d


def _rail_checkpoint(tmp_path: Path, ledger_dir: Path, tag: str) -> Path:
    build_continuity_checkpoint(
        ledger_dir, log_key_path=tmp_path / (tag + "_log.pem")
    )
    return ledger_dir / "checkpoint.note"


def _emit(tmp_path: Path) -> Path:
    out = tmp_path / "verifier"
    out.mkdir()
    return emit_continuity_verifier(out)


def _run(script: Path, ledger: Path, prior: Path):
    return subprocess.run(
        [sys.executable, str(script), str(ledger),
         "--prior-checkpoint", str(prior)],
        capture_output=True, text=True,
    )


def test_appendonly_evidences_rc0(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    prior = _rail_checkpoint(tmp_path, prior_dir, "p5")
    build_continuity_proof(ledger, prior, ledger / "continuity.proof")
    script = _emit(tmp_path)
    r = _run(script, ledger, prior)
    assert r.returncode == 0, r.stderr + r.stdout
    assert _EVIDENCES in r.stdout


def test_priced_prior_refused(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    build_continuity_checkpoint(
        prior_dir, log_key_path=tmp_path / "priced_log.pem", budget="9.99"
    )
    priced = prior_dir / "checkpoint.note"
    script = _emit(tmp_path)
    r = _run(script, ledger, priced)
    assert r.returncode == 1
    assert "rail-only" in (r.stderr + r.stdout)
    assert _EVIDENCES not in r.stdout


def test_missing_proof_refused(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    prior = _rail_checkpoint(tmp_path, prior_dir, "p5")
    script = _emit(tmp_path)
    r = _run(script, ledger, prior)
    assert r.returncode == 1
    assert "continuity.proof not" in (r.stderr + r.stdout)
    assert _EVIDENCES not in r.stdout
