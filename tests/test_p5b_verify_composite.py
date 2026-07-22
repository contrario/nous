"""P5b-2/P5b-3: composite "both" anchor verification, both verifiers.
__nous_p5b_verify_tests_v1__

trace/reference/verifier.py and tb_check.py are two verifiers over one
wire format. P5b-2 landed the composite arm in the reference verifier;
P5b-3 landed the byte-for-byte equivalent in tb_check.py and re-synced
dossier._TRACE_BUNDLE_CHECK_EMBED. FG-S252-B: a rule in one and not the
other makes the emitted verify_offline.py disagree with the Producer's own
dossier, so every state below is asserted against BOTH.

Five verify-time states for a run declaring the composite policy:

  composite, both legs verify   INCLUDED-TIMED     rc 0  enters 10.3
  rekor leg only, verifies      INCLUDED-UNTIMED   rc 10 no T_anchor
  rfc3161 leg only, verifies    TIMED-UNINCLUDED   rc 10 T present
  any leg present but failing   INVALID(ANCHOR_INVALID) rc 20
  both legs absent              unanchored + shortfall  rc 10

The two partials are DISCRETE states, not one state with a missing_leg
field: present-but-failing evidence is rc 20, absent evidence is rc 10.
A composite whose rekor leg carries its own RFC 3161 token is refused --
two genTimes in one anchor have no disagreement rule in the SPEC.

Anchors are built offline with a synthetic ECDSA leaf and a synthetic
Ed25519 log checkpoint (the _submit_factory pattern from
test_c4_rekor_verify), and the RFC 3161 verifier is stubbed to return a
genTime tracking the run's wall clock (SPEC 10.3 bounds every event by
T_anchor +/- tol, so a frozen literal would fail the bound instead of
testing the wiring). FG-S252-A: T is loop-carried; both verifiers now
bind it to None per checkpoint iteration.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

pytest.importorskip("trace_bridge")

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import rekor_anchor_v2
import tb_check
import tsa_client
from rekor_verify_v2 import RekorAnchorV2
from trace_bridge import TraceBridge

_ORIGIN = "test-origin"
_VERIFIER_PATH = _REPO / "trace" / "reference" / "verifier.py"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _raw_pub(key) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _reference_verifier():
    spec = importlib.util.spec_from_file_location(
        "_rv_p5b", _VERIFIER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _leaf_body(signed_bytes, ec_key) -> bytes:
    sig = ec_key.sign(signed_bytes, ECDSA(hashes.SHA256()))
    pub = ec_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {"hashedRekordV002": {
            "data": {
                "algorithm": "SHA2_256",
                "digest": _b64(hashlib.sha256(signed_bytes).digest())},
            "signature": {
                "content": _b64(sig),
                "verifier": {
                    "publicKey": {"rawBytes": _b64(pub)},
                    "keyDetails": "PKIX_ECDSA_P256_SHA_256"}}}}}
    return json.dumps(
        leaf, sort_keys=True, separators=(",", ":")
    ).encode()


def _envelope(origin, tree_size, root_hash, log_key) -> str:
    note = "%s\n%d\n%s\n" % (origin, tree_size, _b64(root_hash))
    key_id = tb_check._rk_ed25519_key_id(origin, _raw_pub(log_key))
    sig = log_key.sign(note.encode("utf-8"))
    return note + "\n" + "\u2014 %s %s\n" % (
        origin, _b64(key_id + sig))


def _rekor_leg_factory(log_key):
    def _submit(data, **kwargs):
        body = _leaf_body(data, ec.generate_private_key(ec.SECP256R1()))
        h0 = hashlib.sha256(b"\x00" + body).digest()
        h1 = hashlib.sha256(b"\x00" + b"sibling").digest()
        root = hashlib.sha256(b"\x01" + h0 + h1).digest()
        return RekorAnchorV2(
            rekor_api_version=2,
            log_id="test-log-id",
            log_index=0,
            body_b64=_b64(body),
            checkpoint_envelope=_envelope(_ORIGIN, 2, root, log_key),
            inclusion_proof_hashes=[_b64(h1)])
    return _submit


def _pack(tmp_path, monkeypatch, backend, rekor_ok, tsa_ok,
          pin_log_key=True):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    monkeypatch.delenv("NOUS_REKOR_LOG_KEYS", raising=False)
    log_key = Ed25519PrivateKey.generate()
    if rekor_ok:
        monkeypatch.setattr(
            rekor_anchor_v2, "anchor_manifest_to_rekor_v2",
            _rekor_leg_factory(log_key))
    else:
        def _boom_rekor(data, **kwargs):
            raise RuntimeError("rekor down")
        monkeypatch.setattr(
            rekor_anchor_v2, "anchor_manifest_to_rekor_v2", _boom_rekor)
    if tsa_ok:
        monkeypatch.setattr(
            tsa_client, "anchor_timestamp",
            lambda **kwargs: b"\x30\x03TOK")
    else:
        def _boom_tsa(**kwargs):
            raise RuntimeError("tsa down")
        monkeypatch.setattr(tsa_client, "anchor_timestamp", _boom_tsa)
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring=backend) as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    if pin_log_key:
        (pack / "rekor_log_keys.json").write_text(
            json.dumps({_ORIGIN: _b64(_raw_pub(log_key))}),
            encoding="ascii")
    return pack


def _stub_rfc3161(module) -> None:
    def _ok(_token, _data):
        return True, datetime.datetime.now(datetime.timezone.utc), []
    module._rv_verify_rfc3161 = _ok


def _stub_rfc3161_tb() -> None:
    def _ok(_token, _data):
        return True, datetime.datetime.now(datetime.timezone.utc), []
    tb_check._tbrv_verify_rfc3161 = _ok


def _tsa_roots(monkeypatch, pack) -> None:
    monkeypatch.setenv(
        "NOUS_TSA_ROOTS", str(pack / "tsa_roots.pem"))
    (pack / "tsa_roots.pem").write_text(
        "-----BEGIN CERTIFICATE-----\nAA==\n"
        "-----END CERTIFICATE-----\n", encoding="ascii")


def _both_verifiers(pack, monkeypatch):
    ref = _reference_verifier()
    _stub_rfc3161(ref)
    _stub_rfc3161_tb()
    monkeypatch.setenv("NOUS_TSA_ROOTS", str(pack / "tsa_roots.pem"))
    code_r, report_r = ref.verify_pack(str(pack))
    code_t, report_t = tb_check._tb_verify_pack(str(pack))
    return (code_r, report_r), (code_t, report_t)


def _anchor_state(report):
    return report["anchors"][-1]["state"] if report["anchors"] else None


@pytest.mark.offline
def test_composite_both_legs_is_included_timed(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, "both", True, True)
    _tsa_roots(monkeypatch, pack)
    ck = json.loads(
        (pack / "trace.ndjson").read_text().splitlines()[-1])
    assert ck["body"]["anchor"]["type"] == "both"
    (cr, rr), (ct, rt) = _both_verifiers(pack, monkeypatch)
    assert cr == 0 and rr["verdict"] == "VALID"
    assert ct == 0 and rt["verdict"] == "VALID"
    assert _anchor_state(rr) == "INCLUDED-TIMED"
    assert _anchor_state(rt) == "INCLUDED-TIMED"


@pytest.mark.offline
def test_composite_rekor_only_is_included_untimed(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, "both", True, False)
    _tsa_roots(monkeypatch, pack)
    ck = json.loads(
        (pack / "trace.ndjson").read_text().splitlines()[-1])
    assert ck["body"]["anchor"]["type"] == "rekor"
    (cr, rr), (ct, rt) = _both_verifiers(pack, monkeypatch)
    assert cr == 10 and rr["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    assert ct == 10 and rt["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    assert _anchor_state(rr) == "INCLUDED-UNTIMED"
    assert _anchor_state(rt) == "INCLUDED-UNTIMED"


@pytest.mark.offline
def test_composite_rfc3161_only_is_timed_unincluded(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, "both", False, True)
    _tsa_roots(monkeypatch, pack)
    ck = json.loads(
        (pack / "trace.ndjson").read_text().splitlines()[-1])
    assert ck["body"]["anchor"]["type"] == "rfc3161"
    (cr, rr), (ct, rt) = _both_verifiers(pack, monkeypatch)
    assert cr == 10 and rr["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    assert ct == 10 and rt["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    assert _anchor_state(rr) == "TIMED-UNINCLUDED"
    assert _anchor_state(rt) == "TIMED-UNINCLUDED"


@pytest.mark.offline
def test_composite_both_legs_fail_is_unanchored(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, "both", False, False)
    ck = json.loads(
        (pack / "trace.ndjson").read_text().splitlines()[-1])
    assert ck["body"]["anchor"] is None
    (cr, rr), (ct, rt) = _both_verifiers(pack, monkeypatch)
    assert cr == 10 and ct == 10
    assert any("unanchored" in f for f in rr["flags"])
    assert any("unanchored" in f for f in rt["flags"])


def _mutated_pack(tmp_path, monkeypatch, mutate):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    monkeypatch.delenv("NOUS_REKOR_LOG_KEYS", raising=False)
    log_key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        rekor_anchor_v2, "anchor_manifest_to_rekor_v2",
        _rekor_leg_factory(log_key))
    monkeypatch.setattr(
        tsa_client, "anchor_timestamp", lambda **kwargs: b"\x30\x03TOK")
    real_make = TraceBridge._make_anchor

    def _wrapped(self, root):
        block = real_make(self, root)
        return mutate(block)
    monkeypatch.setattr(TraceBridge, "_make_anchor", _wrapped)
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="both") as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    (pack / "rekor_log_keys.json").write_text(
        json.dumps({_ORIGIN: _b64(_raw_pub(log_key))}), encoding="ascii")
    (pack / "tsa_roots.pem").write_text(
        "-----BEGIN CERTIFICATE-----\nAA==\n"
        "-----END CERTIFICATE-----\n", encoding="ascii")
    return pack


def _reject_both(pack, monkeypatch):
    ref = _reference_verifier()
    _stub_rfc3161(ref)
    _stub_rfc3161_tb()
    monkeypatch.setenv("NOUS_TSA_ROOTS", str(pack / "tsa_roots.pem"))
    with pytest.raises(ref.VErr) as ref_exc:
        ref.verify_pack(str(pack))
    with pytest.raises(tb_check._TbVErr) as tb_exc:
        tb_check._tb_verify_pack(str(pack))
    return ref_exc.value, tb_exc.value


@pytest.mark.offline
def test_composite_with_broken_rekor_leg_is_invalid(tmp_path, monkeypatch):
    def _mutate(block):
        body = base64.b64decode(block["rekor"]["body_b64"])
        tampered = bytearray(body)
        tampered[-1] ^= 0x01
        block["rekor"]["body_b64"] = base64.b64encode(
            bytes(tampered)).decode()
        return block
    pack = _mutated_pack(tmp_path, monkeypatch, _mutate)
    ref_err, tb_err = _reject_both(pack, monkeypatch)
    assert ref_err.reason == "ANCHOR_INVALID"
    assert tb_err.reason == "ANCHOR_INVALID"


@pytest.mark.offline
def test_composite_rekor_leg_with_own_token_is_refused(
    tmp_path, monkeypatch
):
    def _mutate(block):
        block["rekor"]["rfc3161_token_b64"] = _b64(b"X")
        return block
    pack = _mutated_pack(tmp_path, monkeypatch, _mutate)
    ref_err, tb_err = _reject_both(pack, monkeypatch)
    assert ref_err.reason == "ANCHOR_INVALID"
    assert tb_err.reason == "ANCHOR_INVALID"


@pytest.mark.offline
def test_composite_missing_a_leg_object_is_refused(tmp_path, monkeypatch):
    def _mutate(block):
        del block["rfc3161"]
        return block
    pack = _mutated_pack(tmp_path, monkeypatch, _mutate)
    ref_err, tb_err = _reject_both(pack, monkeypatch)
    assert ref_err.reason == "ANCHOR_INVALID"
    assert tb_err.reason == "ANCHOR_INVALID"


@pytest.mark.offline
def test_reference_and_tb_agree_on_every_composite_state(
    tmp_path, monkeypatch
):
    for rekor_ok, tsa_ok in ((True, True), (True, False),
                             (False, True), (False, False)):
        sub = tmp_path / ("s_%d_%d" % (rekor_ok, tsa_ok))
        sub.mkdir()
        pack = _pack(sub, monkeypatch, "both", rekor_ok, tsa_ok)
        if rekor_ok or tsa_ok:
            _tsa_roots(monkeypatch, pack)
        (cr, rr), (ct, rt) = _both_verifiers(pack, monkeypatch)
        assert cr == ct, (rekor_ok, tsa_ok, cr, ct)
        assert rr["verdict"] == rt["verdict"], (rekor_ok, tsa_ok)
        assert _anchor_state(rr) == _anchor_state(rt), (rekor_ok, tsa_ok)
