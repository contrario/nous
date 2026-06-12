"""S134 2c-3b: `nous verify --gap-witness` issuance.

Drives the real cmd_verify through signing on the AML governance source with a
coverage threshold the blocking net does NOT cover, so the coverage obligation
is refuted and a coverage-gap-witness (refutation) dossier is issued instead of
the fail-closed refusal: a signed manifest with source_kind == "gap-witness"
and a sha-bound coverage.gapwitness.json beside it. Also pins the two
admission refusals (flag without a threshold; flag with --no-manifest).

The blocking net of the AML source is amount > 50000 (block) and
amount > 10000 (abort_cycle); the effective blocked region is amount > 10000.
Threshold "amount > 5000" leaves 5000 < amount <= 10000 uncovered -- a real
gap -- so find_gap_witness_point returns a point and the witness is genuine.

BOUNDARY: a gap-witness proves a coverage gap EXISTS at the carried point; it
is NOT a compliance pass, NOT evidence the agent misbehaves, NOT a claim the
gap is unique or maximal. These tests assert issuance behaviour only.
# __s134_gapw_issue_test_v1__
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cli_verify import cmd_verify

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


def _args(tmp_path: Path, **over: object) -> _Args:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    base = dict(
        file=str(src),
        manifest_out=str(tmp_path / "source.manifest.json"),
        key_path=str(tmp_path / "signing.key"),
    )
    base.update(over)
    return _Args(**base)


def test_gap_witness_issued_when_coverage_refuted(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    args = _args(
        tmp_path,
        coverage_threshold=UNCOVERED_THRESHOLD,
        gap_witness=True,
    )
    rc = cmd_verify(args)
    assert rc == 0
    mout = Path(args.manifest_out)
    assert mout.is_file()
    gw_path = mout.parent / "coverage.gapwitness.json"
    assert gw_path.is_file()

    doc = json.loads(mout.read_text(encoding="utf-8"))
    assert doc.get("source_kind") == "gap-witness"
    gw_sha = doc.get("gap_witness_sha256")
    assert isinstance(gw_sha, str) and len(gw_sha) == 64
    assert all(c in "0123456789abcdef" for c in gw_sha)
    assert "coverage_farkas_sha256" not in doc
    assert "coverage_smt2_sha256" not in doc
    assert "policy_coverage_sha256" not in doc

    file_sha = hashlib.sha256(gw_path.read_bytes()).hexdigest()
    assert file_sha == gw_sha

    gw_doc = json.loads(gw_path.read_text(encoding="utf-8"))
    assert gw_doc.get("fragment") == "coverage-gap-witness"
    assert gw_doc.get("threshold_expr") == UNCOVERED_THRESHOLD
    assert isinstance(gw_doc.get("point"), dict)


def test_gap_witness_requires_coverage_threshold(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    args = _args(tmp_path, coverage_threshold=None, gap_witness=True)
    assert cmd_verify(args) == 1
    assert not Path(args.manifest_out).is_file()


def test_gap_witness_incompatible_with_no_manifest(tmp_path: Path) -> None:
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    args = _args(
        tmp_path,
        coverage_threshold=UNCOVERED_THRESHOLD,
        gap_witness=True,
        no_manifest=True,
    )
    assert cmd_verify(args) == 1
