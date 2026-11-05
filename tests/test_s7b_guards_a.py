"""S7b slice A: each library writer re-reads, with the strict region,
the bytes it is about to sign or hash, and refuses before the
signature (S7B_A_PREDICTIONS.txt 9f0d752c, amendments 1 2c47e110
and 2 46927959).
Every key is made in memory; no test touches the default key path.
"""
from __future__ import annotations

import base64
import copy
import json
import re

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

import annex_iv_map
import attest_apr
import build_vsa
import conformance
import continuity_ledger
import guardrails_adapter
import llm_guard_adapter
import manifest
import ndec
import nous_trace
import provenance
import santander_adapter
import verifier_registry
import vsa
from conformance_verifier import StrictJsonError

NAN = float("nan")
SUR = "x\ud800"
NONCHAR = "x\ufffe"
H = "0" * 64
TS = "2026-11-04T00:00:00Z"


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _refused(label: str):
    return pytest.raises(StrictJsonError, match=re.escape(label))


def _manifest(**kw) -> manifest.Manifest:
    base = dict(
        schema_version="1", nous_version="0", smt_emit_version="0",
        source_sha256=H, pricing_sha256=H, smt_spec_sha256=H,
        world_name="W", cost_cap_usd="0.10", max_ticks=1,
        verdict="proven", solver_name="z3", solver_version="z",
        elapsed_ms=1, timestamp_utc=TS,
    )
    base.update(kw)
    return manifest.Manifest(**base)


def test_g1_sign_manifest():
    with _refused("[js:w.man.1]"):
        manifest.sign_manifest(_manifest(world_name=SUR), _key())


def test_g2_sign_certificate():
    cert = conformance.ConformanceCertificate(
        nous_version="0", world_name=NONCHAR, issued_utc=TS,
        source_sha256=H, smt_spec_sha256=H, pricing_sha256=H,
        trace_sha256=H, binding_ok=True, surface_ok=True,
        assumption_discharge_ok=True, bound_transfer_ok=True,
        authorization_ok=True, trace_signature_ok=True, conformant=True,
        realized_total="0", cost_cap="1", cost_currency="USD",
    )
    with _refused("[js:w.cert.1]"):
        conformance.sign_certificate(cert, _key())


def test_g3_sign_trace():
    env = nous_trace.TraceEnvelope(
        nous_version="0", world_name=NONCHAR, source_sha256=H,
        smt_spec_sha256=H, pricing_sha256=H, events=[],
    )
    with _refused("[js:w.trace.1]"):
        nous_trace.sign_trace(env, _key())


def test_g4_sign_apr():
    enc = _key()
    pub = base64.b64encode(enc.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode("ascii")
    apr = attest_apr.AttestationPinningRecord(
        scheme="pinned_tee_key_v1", enclave_key_id="enc-1",
        enclave_pubkey=pub, pubkey_alg="ed25519", measurement="ab",
        vendor=NONCHAR, model_id="m", tcb_level="t", verified_by="v",
        verified_at=TS, is_test=True,
    )
    with _refused("[js:w.apr.1]"):
        attest_apr.sign_apr(apr, _key())


def test_g5_sign_envelope():
    with _refused("[js:w.ndec.1]"):
        ndec.sign_envelope(statement={"x": NAN}, private_key=_key())


def test_g6_sign_build_vsa():
    with _refused("[js:w.bvsa.1]"):
        build_vsa.sign_build_vsa({"x": NAN}, bytes(range(32)))


def test_g7_sign_provenance():
    with _refused("[js:w.prv.1]"):
        provenance.sign_provenance({"x": NAN}, _key())


def test_g8_sign_registry():
    with _refused("[js:w.reg.1]"):
        verifier_registry.sign_registry({"x": NAN}, _key())


def test_g9_sign_vsa():
    with _refused("[js:w.vsa.1]"):
        vsa.sign_vsa({"x": NAN}, _key())


def _annex_dir(tmp_path, manifest_text: str):
    (tmp_path / "manifest.json").write_text(manifest_text, encoding="utf-8")
    (tmp_path / "source.nous").write_text("world W {}\n", encoding="utf-8")
    return tmp_path


def test_g10_annex_manifest_body(tmp_path):
    d = _annex_dir(tmp_path, '{"world_name": NaN}')
    with _refused("[js:w.aiv.1]"):
        annex_iv_map.build_annex_iv_map(d, _key())


def test_g11_annex_map_body(tmp_path, monkeypatch):
    d = _annex_dir(tmp_path, '{"world_name": "W"}')
    items = list(annex_iv_map.ANNEX_IV_ITEMS)
    first = items[0]
    items[0] = (first[0], SUR, first[2], first[3])
    monkeypatch.setattr(annex_iv_map, "ANNEX_IV_ITEMS", tuple(items))
    with _refused("[js:w.aiv.2]"):
        annex_iv_map.build_annex_iv_map(d, _key())


def _receipt_inputs():
    trace = {
        "world_name": "W",
        "memory_consultation": {
            "world_sha256": "a" * 64, "producing_soul_sha256": "b" * 64,
            "consulted_chain_head": "c" * 64, "consulted_seq_count": 1,
        },
    }
    cert = {"certificate_schema_version": 2, "conformant": True,
            "trace_sha256": H}
    return dict(cert=cert, trace=trace,
                counterparty_signing_key=_key(), counterparty_kid="cp-1",
                issuer="https://cp.example", audience="aud",
                prev_run_digest=H, issued_at=1)


def test_g12_receipt_protected():
    kw = _receipt_inputs()
    kw["counterparty_kid"] = SUR
    with _refused("[js:w.rcp.1]"):
        continuity_ledger.build_counterparty_receipt(**kw)


def test_g13_receipt_claims():
    kw = _receipt_inputs()
    kw["issuer"] = SUR
    with _refused("[js:w.rcp.2]"):
        continuity_ledger.build_counterparty_receipt(**kw)


def test_g24_receipt_certificate():
    kw = _receipt_inputs()
    kw["cert"] = dict(kw["cert"], extra=NAN)
    with _refused("[js:w.rcp.3]"):
        continuity_ledger.build_counterparty_receipt(**kw)


def test_g14_authorization_protected():
    with _refused("[js:w.auth.1]"):
        continuity_ledger.build_authorization_receipt(
            run_digest=H, authorizer_signing_key=_key(),
            authorizer_kid=SUR)


def _grd_record(**kw):
    rec = {"validation_passed": True,
           "validator_results": [{"name": "v", "passed": True}],
           "call_id": "c1"}
    rec.update(kw)
    return rec


def test_g15_guardrails_payload():
    with _refused("[js:w.grd.1]"):
        guardrails_adapter.build_dossier(
            _grd_record(call_id=NAN), _key(), TS, "0")


def test_g16_guardrails_record():
    with _refused("[js:w.grd.2]"):
        guardrails_adapter.build_dossier(
            _grd_record(zz_extra=NAN), _key(), TS, "0")


def test_g17_guardrails_manifest():
    with _refused("[js:w.grd.3]"):
        guardrails_adapter.build_dossier(_grd_record(), _key(), SUR, "0")


def _llg_record(**kw):
    rec = {"results_valid": {"s": True}, "results_score": {"s": 0.5}}
    rec.update(kw)
    return rec


def test_g18_llm_guard_payload():
    with _refused("[js:w.llg.1]"):
        llm_guard_adapter.build_dossier(
            _llg_record(results_score={"s": NAN}), _key(), TS, "0")


def test_g19_llm_guard_record():
    with _refused("[js:w.llg.2]"):
        llm_guard_adapter.build_dossier(
            _llg_record(zz_extra=NAN), _key(), TS, "0")


def test_g20_llm_guard_manifest():
    with _refused("[js:w.llg.3]"):
        llm_guard_adapter.build_dossier(_llg_record(), _key(), SUR, "0")


def _snt():
    import test_santander_adapter as t
    return t


def test_g21_santander_payload():
    t = _snt()
    rec = copy.deepcopy(t._FIXTURE_R2)
    rec["cefl_candidate_scores"][0]["score"] = NAN
    line = t._line(t._FIXTURE_R2)
    with _refused("[js:w.snt.1]"):
        santander_adapter.build_dossier(rec, line, _key(), t._TS, t._VER)


def test_g22_santander_manifest():
    t = _snt()
    line = t._line(t._FIXTURE_R2)
    rec = santander_adapter.parse_decision_jsonl(line)
    with _refused("[js:w.snt.2]"):
        santander_adapter.build_dossier(rec, line, _key(), SUR, t._VER)


def test_g23_santander_line():
    t = _snt()
    line = json.dumps(dict(t._FIXTURE_R2, cefl_candidate_scores=[
        {"index": 0, "score": NAN}]))
    assert "NaN" in line
    with pytest.raises(santander_adapter.SantanderAdapterError,
                       match=re.escape("[js:w.snt.0]")):
        santander_adapter.parse_decision_jsonl(line)
