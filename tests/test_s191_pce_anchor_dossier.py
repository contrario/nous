"""S191 4c: dossier carry of the pre-commitment receipt (pce.anchor.json).

build_dossier reads pce.anchor.json next to the signed manifest, sha-gates it
against the signed pce_anchor_sha256, and re-emits it as a dossier sidecar.
Carried only when the manifest declares pce_anchor_sha256 (drop-when-None ->
byte-identical otherwise). 4c carries; Rekor/TSA/ordering verification is 4d.
DARK: the receipt is a fixture; no network.

  - anchor bound   -> pce.anchor.json carried, sha == manifest.pce_anchor_sha256.
  - tampered sidecar -> DossierError (fail-closed).
  - no anchor      -> no pce.anchor.json in the dossier (pce.json still carried).

# __s191_pce_anchor_carry_read_v1__
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

cmd_verify = pytest.importorskip("cli_verify").cmd_verify
_dossier = pytest.importorskip("dossier")
build_dossier = _dossier.build_dossier
DossierError = _dossier.DossierError
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
        "cumulative": {
            "SA": {"mutable": True},
            "GA": {"total_removable": ["transfer"], "total_addable": None},
            "GQ": {"quorum_drift_budget": {"approve": 5}},
        },
    }


def _anchor_doc(anchored_sha: str) -> dict:
    return {
        "pce_anchor_schema_version": 1,
        "anchored_pce_sha256": anchored_sha,
        "basis": "pre-commitment-in-time; " + _DISC,
        "rekor_v2": {"rekor_api_version": 2, "log_id": "log2025-1",
                     "log_index": 0, "body_b64": "e30=",
                     "checkpoint_envelope": "o\n0\nr\n",
                     "inclusion_proof_hashes": []},
        "pce_rfc3161_token_b64": "AAAA",
    }


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    return src


def _bind(tmp_path: Path, src: Path, *, with_anchor: bool) -> Path:
    base_f = tmp_path / "baseline.canon"
    base_f.write_text("NV:0", encoding="utf-8")
    env = _env_doc(hashlib.sha256(b"NV:0").hexdigest())
    pce_f = tmp_path / "envelope.json"
    pce_bytes = json.dumps(env).encode("utf-8")
    pce_f.write_bytes(pce_bytes)
    kw: dict = dict(pce=str(pce_f), pce_baseline=str(base_f))
    if with_anchor:
        receipt = tmp_path / "receipt.json"
        receipt.write_text(
            json.dumps(_anchor_doc(hashlib.sha256(pce_bytes).hexdigest())),
            encoding="utf-8",
        )
        kw["pce_anchor"] = str(receipt)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"), **kw,
    ))
    assert rc == 0
    return mout


def test_dossier_carries_anchor_receipt(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_anchor=True)
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert m.get("pce_anchor_sha256")
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    carried = out / "pce.anchor.json"
    assert carried.is_file()
    assert hashlib.sha256(carried.read_bytes()).hexdigest() == m[
        "pce_anchor_sha256"
    ]


def test_dossier_tampered_anchor_refused(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_anchor=True)
    (tmp_path / "pce.anchor.json").write_bytes(b'{"tampered":true}')
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=mout, output=out)


def test_dossier_no_anchor_absent(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_anchor=False)
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert "pce_anchor_sha256" not in m
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    assert not (out / "pce.anchor.json").is_file()
    assert (out / "pce.json").is_file()
