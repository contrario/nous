"""S194 Inc C: dossier carry of the envelope witness quorum sidecar.

build_dossier reads envelope.witness.json next to the signed manifest, sha-gates
it against the signed envelope_witness_sha256, and re-emits it as a dossier
sidecar. Carried only when the manifest declares envelope_witness_sha256
(drop-when-None -> byte-identical otherwise). Carry only; the k-of-n cosignature
quorum verify is the embedded offline verifier's job, validated separately.
Independent of --pce.

  - witness bound    -> envelope.witness.json carried, sha == manifest field.
  - tampered sidecar -> DossierError (fail-closed).
  - no witness       -> no envelope.witness.json in the dossier.

# __s194_envelope_witness_carry_read_v1__
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

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "aml_transaction_governance.nous"
)


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
    witness = None

    def __init__(self, **over: object) -> None:
        for k, v in over.items():
            setattr(self, k, v)


def _witness_doc() -> dict:
    return {
        "witness_schema_version": 1,
        "checkpoint_note": "nous.envelope.v0\n0\n" + "A" * 43 + "=\n",
        "fan": [],
        "threshold": 1,
        "witnesses": [],
    }


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "source.nous"
    src.write_bytes(TEMPLATE.read_bytes())
    return src


def _bind(tmp_path: Path, src: Path, *, with_witness: bool) -> Path:
    kw: dict = {}
    if with_witness:
        wfile = tmp_path / "witness.json"
        wfile.write_text(json.dumps(_witness_doc()), encoding="utf-8")
        kw["witness"] = str(wfile)
    mout = tmp_path / "source.manifest.json"
    rc = cmd_verify(_Args(
        file=str(src), manifest_out=str(mout),
        key_path=str(tmp_path / "signing.key"), **kw,
    ))
    assert rc == 0
    return mout


def test_dossier_carries_witness_sidecar(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_witness=True)
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert m.get("envelope_witness_sha256")
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    carried = out / "envelope.witness.json"
    assert carried.is_file()
    assert hashlib.sha256(carried.read_bytes()).hexdigest() == m[
        "envelope_witness_sha256"
    ]


def test_dossier_tampered_witness_refused(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_witness=True)
    (tmp_path / "envelope.witness.json").write_bytes(b'{"tampered":true}')
    out = tmp_path / "out"
    with pytest.raises(DossierError):
        build_dossier(src, manifest=mout, output=out)


def test_dossier_no_witness_absent(tmp_path):
    if not TEMPLATE.is_file():
        pytest.skip("aml demo source not present")
    src = _src(tmp_path)
    mout = _bind(tmp_path, src, with_witness=False)
    m = json.loads(mout.read_text(encoding="utf-8"))
    assert "envelope_witness_sha256" not in m
    out = tmp_path / "out"
    build_dossier(src, manifest=mout, output=out)
    assert not (out / "envelope.witness.json").is_file()
