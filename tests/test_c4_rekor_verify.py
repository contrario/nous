"""C4: the reference verifier's Rekor v2 anchor leg (SPEC 10.1 / 10.3).

__nous_rekor_verify_tests_v1__

Two things are pinned here.

(1) DRIFT. trace/reference/verifier.py carries the rekor leg spliced verbatim
    from the tracked source rekor_check.py, because the verifier is standalone
    (stdlib + cryptography, no sibling imports) and cannot import it. The
    splice is compared byte-for-byte with the source, so the copy cannot drift
    the way the three RFC 3161 copies actually did.

(2) DISCRIMINATED OUTCOME. Rekor v2 carries no per-entry integrated time and
    no SET, so trusted time can only come from an RFC 3161 token over the leaf
    signature. Inclusion WITH time and inclusion WITHOUT it are different claim
    classes:

      INCLUDED-TIMED    enters the SPEC 10.3 time bound -> VALID, rc 0
      INCLUDED-UNTIMED  cannot enter it -> INTEGRITY-OK/INCOMPLETE, rc 10
      inclusion fails   -> INVALID(ANCHOR_INVALID), rc 20
      token present but not verifying -> INVALID, never a silent downgrade

    The verifier reports that no trusted time is PRESENT. It cannot distinguish
    a TSA outage from a Producer that skipped the TSA, so it asserts no cause.
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
import rekor_check as rk
import tsa_client
from rekor_verify_v2 import RekorAnchorV2
from trace_bridge import TraceBridge

_ORIGIN = "test-log.example"
_VERIFIER_PATH = _REPO / "trace" / "reference" / "verifier.py"
_SOURCE_PATH = _REPO / "rekor_check.py"
_BEGIN = "# __rk_splice_begin_v1__\n"
_END = "# __rk_splice_end_v1__\n"


def _verifier():
    spec = importlib.util.spec_from_file_location("_rv_c4", _VERIFIER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _b64(raw):
    return base64.b64encode(raw).decode()


def _leaf_body(signed_bytes, leaf_key):
    sig = leaf_key.sign(signed_bytes, ECDSA(hashes.SHA256()))
    pub = leaf_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
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
    return json.dumps(leaf, sort_keys=True, separators=(",", ":")).encode()


def _raw_pub(log_key):
    return log_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


def _envelope(origin, tree_size, root_hash, log_key):
    note = "%s\n%d\n%s\n" % (origin, tree_size, _b64(root_hash))
    key_id = rk._rk_ed25519_key_id(origin, _raw_pub(log_key))
    sig = log_key.sign(note.encode("utf-8"))
    return note + "\n" + "\u2014 %s %s\n" % (
        origin, _b64(key_id + sig))


def _submit_factory(log_key):
    def _submit(data, **kwargs):
        body = _leaf_body(data, ec.generate_private_key(ec.SECP256R1()))
        h0 = hashlib.sha256(b"\x00" + body).digest()
        h1 = hashlib.sha256(b"\x00" + b"sibling-entry").digest()
        root = hashlib.sha256(b"\x01" + h0 + h1).digest()
        return RekorAnchorV2(
            rekor_api_version=2,
            log_id="test-log-id",
            log_index=0,
            body_b64=_b64(body),
            checkpoint_envelope=_envelope(_ORIGIN, 2, root, log_key),
            inclusion_proof_hashes=[_b64(h1)])
    return _submit


def _pack(tmp_path, monkeypatch, timed, pin_log_key=True):
    monkeypatch.delenv("NOUS_TSA_ROOTS", raising=False)
    monkeypatch.delenv("NOUS_REKOR_LOG_KEYS", raising=False)
    log_key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(rekor_anchor_v2, "anchor_manifest_to_rekor_v2",
                        _submit_factory(log_key))
    if timed:
        monkeypatch.setattr(tsa_client, "anchor_timestamp",
                            lambda **kwargs: b"\x30\x03TOK")
    else:
        def _boom(**kwargs):
            raise RuntimeError("no tsa")
        monkeypatch.setattr(tsa_client, "anchor_timestamp", _boom)
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="rekor") as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    if pin_log_key:
        (pack / "rekor_log_keys.json").write_text(
            json.dumps({_ORIGIN: _b64(_raw_pub(log_key))}), encoding="ascii")
    return pack


def _stub_tsa(module):
    # __rk_stub_now_v1__ The stubbed genTime must track the run's wall clock.
    # SPEC 10.3 bounds every event by T_anchor +/- tol, so a frozen literal
    # fails the bound instead of testing the wiring -- which is exactly what
    # happened on first run, evidencing that the time bound is live on the
    # rekor path and not bypassed by the new dispatch arm.
    def _ok(_token, _data):
        return True, datetime.datetime.now(datetime.timezone.utc), []
    module._rv_verify_rfc3161 = _ok


@pytest.mark.offline
def test_splice_matches_the_tracked_source():
    text = _VERIFIER_PATH.read_text(encoding="utf-8")
    assert text.count(_BEGIN) == 1, "splice begin sentinel is not unique"
    assert text.count(_END) == 1, "splice end sentinel is not unique"
    spliced = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    assert spliced == source, (
        "trace/reference/verifier.py has DRIFTED from the tracked source "
        "rekor_check.py; edit rekor_check.py and re-splice, never edit the "
        "copy in place")


@pytest.mark.offline
def test_untimed_anchor_is_incomplete_and_names_the_gap(tmp_path,
                                                        monkeypatch):
    pack = _pack(tmp_path, monkeypatch, timed=False)
    code, report = _verifier().verify_pack(str(pack))
    assert code == 10, (code, report["verdict"])
    assert report["verdict"] == "INTEGRITY-OK/INCOMPLETE"
    entries = [a for a in report["anchors"] if a["type"] == "rekor"]
    assert entries, report["anchors"]
    assert all(a["state"] == "INCLUDED-UNTIMED" for a in entries)
    assert all("gen_time" not in a for a in entries)
    assert any("INCLUDED-UNTIMED" in f for f in report["flags"]), \
        report["flags"]


@pytest.mark.offline
def test_timed_anchor_is_valid(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, timed=True)
    module = _verifier()
    _stub_tsa(module)
    code, report = module.verify_pack(str(pack))
    assert code == 0, (code, report)
    assert report["verdict"] == "VALID"
    entries = [a for a in report["anchors"] if a["type"] == "rekor"]
    assert entries and all(a["state"] == "INCLUDED-TIMED" for a in entries)
    assert all(a["gen_time"] for a in entries)


@pytest.mark.offline
def test_timed_and_untimed_reach_different_outcomes(tmp_path, monkeypatch):
    untimed = _pack(tmp_path / "u", monkeypatch, timed=False)
    code_u, report_u = _verifier().verify_pack(str(untimed))
    timed = _pack(tmp_path / "t", monkeypatch, timed=True)
    module = _verifier()
    _stub_tsa(module)
    code_t, report_t = module.verify_pack(str(timed))
    assert code_u != code_t
    assert report_u["verdict"] != report_t["verdict"]


@pytest.mark.offline
def test_unpinned_log_origin_fails_closed(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, timed=False, pin_log_key=False)
    module = _verifier()
    with pytest.raises(module.VErr) as exc:
        module.verify_pack(str(pack))
    assert exc.value.reason == "ANCHOR_INVALID"
    assert "allowlist" in exc.value.detail


@pytest.mark.offline
def test_present_but_failing_token_is_invalid(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, timed=True)
    module = _verifier()

    def _bad(_token, _data):
        return False, None, ["signer does not chain to a pinned root"]

    module._rv_verify_rfc3161 = _bad
    with pytest.raises(module.VErr) as exc:
        module.verify_pack(str(pack))
    assert exc.value.reason == "ANCHOR_INVALID"
    assert "timestamp:" in exc.value.detail


@pytest.mark.offline
def test_verifier_asserts_no_cause_for_absent_time(tmp_path, monkeypatch):
    # anchor_failures is producer-asserted and never reaches the pack; the
    # verifier must not speculate about why time is missing.
    pack = _pack(tmp_path, monkeypatch, timed=False)
    _, report = _verifier().verify_pack(str(pack))
    blob = json.dumps(report).lower()
    for forbidden in ("unavailable", "outage", "was down", "tsa failed",
                      "could not reach"):
        assert forbidden not in blob, forbidden


@pytest.mark.offline
def test_log_key_provenance_is_reported(tmp_path, monkeypatch):
    pack = _pack(tmp_path, monkeypatch, timed=False)
    _, report = _verifier().verify_pack(str(pack))
    assert report["rekor_log_key_provenance"] == "auditor-pinned"
    entries = [a for a in report["anchors"] if a["type"] == "rekor"]
    assert all(a["rekor_log_key_provenance"] == "auditor-pinned"
               for a in entries)
