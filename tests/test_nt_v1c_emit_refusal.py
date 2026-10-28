"""NT-GATE-1 V1-C: vsa emit refuses a cost-bearing bundle the offline
verifier would reject (operator point 1, 2026-10-27). Predictions:
V1C_PREDICTIONS.md, sha256 292fb376...; material rebuilt under
V1E_PREDICTIONS.md, sha256 6b6f2ada... (the published v1 vector is
frozen without obligations_canon, ruling (i), so it is not used here).

Material: test_nt_v1b's manifest, trace and source, with a cost proof,
certified by `nous conformance certify` (which embeds the canon).

# __nt_v1c_emit_refusal_tests_v1__
"""
from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import cli_vsa
import cost_farkas as cf
import test_nt_v1b_certify_canon as v1b
from conformance import certificate_json, load_certificate, sign_certificate

pricing = v1b.pricing


def _bundle_inputs(pricing, tmp_path: Path):
    spec, _man, src_p, prices_p, trace_p, man_p = v1b._material(
        pricing, tmp_path, with_cost=True
    )
    cert = v1b._certify(tmp_path, src_p, prices_p, trace_p, man_p,
                        flag=False)
    assert cert.obligations_canon == spec.canonical_str()
    cost_p = tmp_path / "cost.farkas.json"
    cost_p.write_bytes(
        cf.cost_farkas_json_bytes(cf.cost_certificate_from_smtspec(spec))
    )
    return trace_p, man_p, tmp_path / "conformance.json", cost_p


def _cert_variant(tmp_path: Path, cert_p: Path, canon_edit) -> Path:
    cert = load_certificate(str(cert_p))
    new = cert.model_copy(update={
        "obligations_canon": canon_edit(cert.obligations_canon),
        "signature": None,
    })
    signed = sign_certificate(new, Ed25519PrivateKey.generate())
    p = tmp_path / "cert_variant.json"
    p.write_text(certificate_json(signed), encoding="utf-8")
    return p


def _emit(tmp_path, trace_p, man_p, cert_p, cost_p):
    key = tmp_path / "vsa.key"
    key.write_bytes(bytes(range(96, 128)))
    out = tmp_path / "bundle"
    ns = argparse.Namespace(
        command="vsa", vsa_command="emit",
        trace=str(trace_p), manifest=str(man_p), cert=str(cert_p),
        coverage=None, cost=(str(cost_p) if cost_p else None),
        out=str(out), key_path=str(key), no_inline_pin=False,
    )
    return cli_vsa.cmd_vsa(ns), out


def test_e1_cost_without_canon_refused(pricing, tmp_path, capsys):
    trace_p, man_p, cert_p, cost_p = _bundle_inputs(pricing, tmp_path)
    cert = _cert_variant(tmp_path, cert_p, lambda c: None)
    rc, out = _emit(tmp_path, trace_p, man_p, cert, cost_p)
    err = capsys.readouterr().err
    assert rc == 2, (rc, err)
    assert "no spec canon" in err
    assert not (out / "vsa.intoto.json").exists()


def test_e2_cost_with_canon_emits(pricing, tmp_path):
    trace_p, man_p, cert_p, cost_p = _bundle_inputs(pricing, tmp_path)
    rc, out = _emit(tmp_path, trace_p, man_p, cert_p, cost_p)
    assert rc == 0
    assert (out / "vsa.intoto.json").is_file()


def test_e3_cost_with_unbound_canon_refused(pricing, tmp_path, capsys):
    trace_p, man_p, cert_p, cost_p = _bundle_inputs(pricing, tmp_path)
    cert = _cert_variant(tmp_path, cert_p, lambda c: c + "\n")
    rc, out = _emit(tmp_path, trace_p, man_p, cert, cost_p)
    err = capsys.readouterr().err
    assert rc == 2, (rc, err)
    assert "smt_spec_sha256" in err
    assert not (out / "vsa.intoto.json").exists()


def test_e4_no_cost_needs_no_canon(pricing, tmp_path):
    trace_p, man_p, cert_p, _cost_p = _bundle_inputs(pricing, tmp_path)
    cert = _cert_variant(tmp_path, cert_p, lambda c: None)
    rc, out = _emit(tmp_path, trace_p, man_p, cert, None)
    assert rc == 0
    assert (out / "vsa.intoto.json").is_file()
