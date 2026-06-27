from __future__ import annotations

import shutil
from pathlib import Path

from continuity_checkpoint import (
    build_continuity_checkpoint,
    build_continuity_proof,
)
from test_s177_cli_continuity import _run
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


def _prior(tmp_path: Path, ledger: Path) -> Path:
    pdir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    build_continuity_checkpoint(pdir, log_key_path=tmp_path / "p5_log.pem")
    return pdir / "checkpoint.note"


def test_cli_verify_prior_checkpoint_evidences(tmp_path, capsys) -> None:
    ledger = _ledger9(tmp_path)
    prior = _prior(tmp_path, ledger)
    build_continuity_proof(ledger, prior, ledger / "continuity.proof")
    rc = _run(["continuity", "verify", "--ledger", str(ledger),
               "--prior-checkpoint", str(prior)])
    out = capsys.readouterr().out
    assert rc == 0
    assert _EVIDENCES in out


def test_cli_verify_prior_checkpoint_missing_proof_refused(
    tmp_path, capsys
) -> None:
    ledger = _ledger9(tmp_path)
    prior = _prior(tmp_path, ledger)
    rc = _run(["continuity", "verify", "--ledger", str(ledger),
               "--prior-checkpoint", str(prior)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "continuity.proof not" in (captured.out + captured.err)
    assert _EVIDENCES not in captured.out
