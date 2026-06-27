from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest

import rekor_v2_offline as rkt
from continuity_checkpoint import (
    ContinuityCheckpointError,
    build_continuity_checkpoint,
    build_continuity_proof,
)
from rekor_checkpoint import parse_checkpoint
from test_s178_checkpoint_leg import _build_priced_ledger, _keys

_CAPS9 = ["0.10", "0.11", "0.12", "0.13", "0.14",
          "0.15", "0.16", "0.17", "0.18"]


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


def test_happy_5_to_9_emits_verifiable_proof(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    prior_note = _rail_checkpoint(tmp_path, prior_dir, "p5")
    out = tmp_path / "continuity.proof"
    doc = build_continuity_proof(ledger, prior_note, out)
    assert doc["prior_tree_size"] == 5
    assert doc["current_tree_size"] == 9
    assert doc["kind"] == "nous.continuity.consistency.v1"
    assert doc["proof"]
    rkt.verify_consistency(
        doc["prior_tree_size"], doc["current_tree_size"],
        base64.b64decode(doc["prior_root_b64"]),
        base64.b64decode(doc["current_root_b64"]),
        [base64.b64decode(h) for h in doc["proof"]],
    )
    assert out.is_file()


def test_rollback_refuses(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 9, "prior9")
    prior_note = _rail_checkpoint(tmp_path, prior_dir, "p9")
    current5 = _prefix_dir(tmp_path, ledger, 5, "current5")
    with pytest.raises(ContinuityCheckpointError, match="rollback"):
        build_continuity_proof(current5, prior_note, tmp_path / "x.proof")


def test_rewrite_refuses(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    prior_note = _rail_checkpoint(tmp_path, prior_dir, "p5")
    lines = prior_note.read_text(encoding="utf-8").split("\n")
    bogus = base64.b64encode(rkt._naive_root([b"different"])).decode("ascii")
    lines[2] = bogus
    prior_note.write_text("\n".join(lines), encoding="utf-8")
    assert parse_checkpoint(
        prior_note.read_text(encoding="utf-8")
    ).tree_size == 5
    with pytest.raises(ContinuityCheckpointError, match="rewrite"):
        build_continuity_proof(ledger, prior_note, tmp_path / "x.proof")


def test_priced_prior_refuses_rail_only(tmp_path) -> None:
    ledger = _ledger9(tmp_path)
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    build_continuity_checkpoint(
        prior_dir, log_key_path=tmp_path / "priced_log.pem", budget="9.99"
    )
    priced_note = prior_dir / "checkpoint.note"
    assert parse_checkpoint(
        priced_note.read_text(encoding="utf-8")
    ).extensions
    with pytest.raises(ContinuityCheckpointError, match="rail-only"):
        build_continuity_proof(ledger, priced_note, tmp_path / "x.proof")
