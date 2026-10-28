"""NT-GATE-1 V1-B: certify emits obligations_canon whenever the manifest
declares a cost proof (operator ruling, 2026-10-27). Predictions:
V1B_PREDICTIONS.md, sha256 35c88be9...

# __nt_v1b_certify_canon_tests_v1__
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import cli_conformance
import conformance
import cost_farkas as cf
import test_s97_certificate as s97
from conformance import load_certificate
from nous_trace import TraceEnvelope, sign_trace
from manifest import (
    load_or_create_keypair,
    manifest_from_verify,
    manifest_json,
    sign_manifest,
)
from parser import parse_nous
from smt_emit import emit_smt
from smt_verify import VerifyResult

pricing = s97.pricing


def _material(pricing, tmp_path, with_cost: bool):
    program = parse_nous(s97._SOULED_SOURCE)
    spec = emit_smt(
        program, pricing, source_text=s97._SOULED_SOURCE, today=s97.TODAY
    )
    man = manifest_from_verify(
        VerifyResult(
            verdict="proven", spec=spec, solver_name="z3",
            solver_version="z3 4.16.0", elapsed_ms=11,
            timestamp_utc="2026-05-26T00:00:00+00:00",
        ),
        nous_version="5.13.1",
    )
    if with_cost:
        doc = cf.cost_certificate_from_smtspec(spec)
        assert doc is not None
        man = dataclasses.replace(
            man, cost_farkas_sha256=cf.cost_farkas_sha256(doc)
        )
    env = TraceEnvelope(
        nous_version="5.13.1",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[
            s97._event(0, 0, "Analyst", it=900, ot=400),
            s97._event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    tr = sign_trace(env, Ed25519PrivateKey.generate())
    src_p = tmp_path / "source.nous"
    src_p.write_text(s97._SOULED_SOURCE, encoding="utf-8")
    prices_p = tmp_path / "pricing.toml"
    prices_p.write_text(s97.PRICING_TOML, encoding="utf-8")
    trace_p = tmp_path / "trace.json"
    trace_p.write_text(s97._trace_json(tr), encoding="utf-8")
    priv, pub, _ = load_or_create_keypair(tmp_path / "m.key")
    man_p = tmp_path / "manifest.json"
    man_p.write_text(
        manifest_json(man, sign_manifest(man, priv), pub), encoding="utf-8"
    )
    return spec, man, src_p, prices_p, trace_p, man_p


def _certify(tmp_path, src_p, prices_p, trace_p, man_p, flag: bool):
    out_p = tmp_path / "conformance.json"
    ns = argparse.Namespace(
        command="conformance", conformance_cmd="certify",
        trace=str(trace_p), manifest=str(man_p), prices=str(prices_p),
        source=str(src_p), out=str(out_p),
        key_path=str(tmp_path / "cert.key"),
        issued_utc="2026-05-26T00:00:00Z", anchor=None,
        emit_obligations_canon=flag,
    )
    assert cli_conformance.cmd_conformance(ns) == 0
    return load_certificate(str(out_p))


def test_c1_cost_proof_present_emits_canon(pricing, tmp_path):
    spec, man, *paths = _material(pricing, tmp_path, with_cost=True)
    cert = _certify(tmp_path, *paths, flag=False)
    assert cert.obligations_canon == spec.canonical_str()
    assert hashlib.sha256(
        cert.obligations_canon.encode("utf-8")
    ).hexdigest() == man.smt_spec_sha256


def test_c2_no_cost_proof_no_flag_no_canon(pricing, tmp_path):
    _spec, _man, *paths = _material(pricing, tmp_path, with_cost=False)
    cert = _certify(tmp_path, *paths, flag=False)
    assert cert.obligations_canon is None


def test_c3_flag_still_forces_canon(pricing, tmp_path):
    spec, _man, *paths = _material(pricing, tmp_path, with_cost=False)
    cert = _certify(tmp_path, *paths, flag=True)
    assert cert.obligations_canon == spec.canonical_str()


def test_c4_rule_in_one_place(pricing, tmp_path):
    assert hasattr(conformance, "obligations_canon_for")
    rule = conformance.obligations_canon_for
    spec, man_cost, *_ = _material(pricing, tmp_path, with_cost=True)
    man_none = dataclasses.replace(man_cost, cost_farkas_sha256=None)
    assert rule(man_cost, spec) == spec.canonical_str()
    assert rule(man_none, spec) is None
    assert rule(man_none, spec, emit=True) == spec.canonical_str()


def test_c5_flag_help_states_the_rule():
    text = open(cli_conformance.__file__, encoding="utf-8").read()
    assert "off by default to keep certificates byte-identical" not in text
    assert "cost proof" in text


def test_c6_certify_help_states_what_is_signed():
    # V1-D (operator ruling A, 2026-10-27): the user who runs
    # `certify --help` learns what the signed certificate discloses.
    p = argparse.ArgumentParser(prog="nous")
    sub = p.add_subparsers(dest="command")
    cli_conformance.build_conformance_parser(sub)
    certify = None
    for action in p._subparsers._group_actions:
        conf = action.choices["conformance"]
        for a2 in conf._subparsers._group_actions:
            certify = a2.choices["certify"]
    assert certify is not None
    text = " ".join(certify.format_help().split())
    for word in ("obligations_canon", "part of the signed certificate",
                 "rates", "token",
                 "currency", "NV", "GA", "GQ", "SA", "DE"):
        assert word in text, word
