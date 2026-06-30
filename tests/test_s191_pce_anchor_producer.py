"""S191 4b: producer functional test -- `nous verify --pce ... --pce-anchor`.

Binds a pre-commitment receipt (pce.anchor.json) into the SIGNED manifest as
pce_anchor_sha256 and writes it as a dossier sidecar. The bind validates the
receipt anchored_pce_sha256 == the bound envelope sha256 (the receipt must
anchor THIS envelope). DARK: no network; the receipt is a fixture, never a live
anchor. The bind is absolute (pre-commitment-in-time); ordering is the
verifier's relational job (4d), not asserted here.

  - valid anchor   -> rc 0, manifest carries pce_anchor_sha256, pce.anchor.json
                      written next to the manifest (== the input receipt bytes).
  - sha mismatch   -> REFUSED (receipt anchors a different envelope), no manifest.
  - --pce-anchor without --pce -> REFUSED, no manifest.
  - omitted        -> no pce_anchor_sha256, no pce.anchor.json (pce still bound).

# __s191_pce_anchor_producer_v1__
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

cmd_verify = pytest.importorskip("cli_verify").cmd_verify
pytest.importorskip("envelope")

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "aml_transaction_governance.nous"
)
_DISC = "not a legal substantiality determination"


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
    pce = None
    pce_baseline = None
    pce_anchor = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _env_doc(base_sha: str) -> dict:
    return {
        "pce_schema_version": 1,
        "baseline_canon_sha256": base_sha,
        "per_step": {
            "SA": {"mutable": True},
            "GA": {"may_add": True, "may_remove": ["transfer"]},
            "GQ": {"may_add": True, "may_remove": False,
                   "quorum_bounds": {"approve": {"min": 2, "max": None}}},
        },
        "basis": "membership against a pre-committed envelope; " + _DISC,
        "declared_utc": "2026-06-29T00:00:00+00:00",
    }


def _anchor_doc(anchored_sha: str) -> dict:
    return {
        "pce_anchor_schema_version": 1,
        "anchored_pce_sha256": anchored_sha,
        "basis": "pre-commitment-in-time; " + _DISC,
        "rekor_v2": {
            "rekor_api_version": 2, "log_id": "log2025-1", "log_index": 0,
            "body_b64": "e30=", "checkpoint_envelope": "o\n0\nr\n",
            "inclusion_proof_hashes": [],
        },
        "pce_rfc3161_token_b64": "AAAA",
    }


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    return src


def _env(tmp_path: Path):
    base_f = tmp_path / "baseline.canon"
    base_f.write_text("NV:0", encoding="utf-8")
    env = _env_doc(hashlib.sha256(b"NV:0").hexdigest())
    pce_f = tmp_path / "envelope.json"
    pce_bytes = json.dumps(env).encode("utf-8")
    pce_f.write_bytes(pce_bytes)
    return base_f, pce_f, pce_bytes


def test_anchor_bind_writes_field_and_sidecar(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    base_f, pce_f, pce_bytes = _env(tmp_path)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(_anchor_doc(hashlib.sha256(pce_bytes).hexdigest())),
        encoding="utf-8",
    )
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f), pce_baseline=str(base_f), pce_anchor=str(receipt),
    ))
    assert rc == 0
    sidecar = tmp_path / "pce.anchor.json"
    assert sidecar.is_file()
    assert sidecar.read_bytes() == receipt.read_bytes()
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert m.get("pce_anchor_sha256") == hashlib.sha256(
        receipt.read_bytes()
    ).hexdigest()


def test_anchor_mismatch_refused(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    base_f, pce_f, pce_bytes = _env(tmp_path)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_anchor_doc("d" * 64)), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f), pce_baseline=str(base_f), pce_anchor=str(receipt),
    ))
    assert rc == 1
    assert not mout.is_file()
    assert not (tmp_path / "pce.anchor.json").is_file()


def test_anchor_requires_pce(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_anchor_doc("e" * 64)), encoding="utf-8")
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce_anchor=str(receipt),
    ))
    assert rc == 1
    assert not mout.is_file()


def test_anchor_omitted_byte_identical(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    base_f, pce_f, _ = _env(tmp_path)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"),
        pce=str(pce_f), pce_baseline=str(base_f),
    ))
    assert rc == 0
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert "pce_anchor_sha256" not in m
    assert not (tmp_path / "pce.anchor.json").is_file()
    assert (tmp_path / "pce.json").is_file()
