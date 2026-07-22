"""Unit conformance for the rekor_check.py splice source (SPEC 10.1).

__nous_rekor_check_tests_v1__

rekor_check.py is the SINGLE tracked source of the Rekor v2 offline verify
leg. It is spliced into trace/reference/verifier.py and into the dossier
embed rather than being retyped in each, so the three copies cannot drift the
way the RFC 3161 copies actually did. These tests pin its behaviour at the
source; the drift tests pin the copies to this source.

The central assertion is the DISCRIMINATOR: inclusion with trusted time and
inclusion without it are different claim classes and must never collapse into
one verdict. A token that is present but does NOT verify is neither -- it is a
failure, not a silent downgrade to untimed.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import rekor_check as rk

_ORIGIN = "test-log.example"
_PINNED_ORIGIN = "log2025-1.rekor.sigstore.dev"
_FIXTURE = (
    Path(__file__).parent / "rekor_fixtures" / "real_checkpoint_log2025-1.txt"
)


def _leaf_body(signed_bytes, key):
    sig = key.sign(signed_bytes, ECDSA(hashes.SHA256()))
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {"hashedRekordV002": {
            "data": {
                "algorithm": "SHA2_256",
                "digest": base64.b64encode(
                    hashlib.sha256(signed_bytes).digest()).decode()},
            "signature": {
                "content": base64.b64encode(sig).decode(),
                "verifier": {
                    "publicKey": {
                        "rawBytes": base64.b64encode(pub).decode()},
                    "keyDetails": "PKIX_ECDSA_P256_SHA_256"}}}}}
    return json.dumps(leaf, sort_keys=True, separators=(",", ":")).encode()


def _envelope(origin, tree_size, root_hash, log_key):
    note = "%s\n%d\n%s\n" % (
        origin, tree_size, base64.b64encode(root_hash).decode())
    raw_pub = log_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    key_id = rk._rk_ed25519_key_id(origin, raw_pub)
    sig = log_key.sign(note.encode("utf-8"))
    line = "\u2014 %s %s\n" % (
        origin, base64.b64encode(key_id + sig).decode())
    return note + "\n" + line


def _two_leaf_anchor(signed_bytes, token_b64=None):
    """Index 0 of a two-leaf tree: a real one-node inclusion proof."""
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    log_key = Ed25519PrivateKey.generate()
    body = _leaf_body(signed_bytes, leaf_key)
    h0 = rk._rk_leaf_hash(body)
    h1 = rk._rk_leaf_hash(b"sibling-entry")
    root = hashlib.sha256(b"\x01" + h0 + h1).digest()
    block = {
        "type": "rekor",
        "rekor_api_version": 2,
        "log_id": "test-log-id",
        "log_index": 0,
        "body_b64": base64.b64encode(body).decode(),
        "checkpoint_envelope": _envelope(_ORIGIN, 2, root, log_key),
        "inclusion_proof_hashes": [base64.b64encode(h1).decode()],
    }
    if token_b64 is not None:
        block["rfc3161_token_b64"] = token_b64
    raw_pub = log_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return block, {_ORIGIN: raw_pub}


def _good_tsa(_token, _data):
    return True, datetime.datetime(
        2026, 7, 22, 11, 0, 0, tzinfo=datetime.timezone.utc), []


def _bad_tsa(_token, _data):
    return False, None, ["signer does not chain to a pinned root"]


@pytest.mark.offline
def test_included_untimed_when_no_token():
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(root)
    detail = rk._rk_verify_anchor(block, root, keys)
    assert detail["leaf_digest_ok"]
    assert detail["leaf_sig_ok"]
    assert detail["checkpoint_sig_ok"]
    assert detail["inclusion_ok"]
    assert detail["timestamp_ok"] is False
    assert detail["state"] == "INCLUDED-UNTIMED"
    assert detail["gen_time"] is None
    assert detail["errors"] == []


@pytest.mark.offline
def test_included_timed_when_token_verifies():
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(
        root, token_b64=base64.b64encode(b"token").decode())
    detail = rk._rk_verify_anchor(block, root, keys, _good_tsa)
    assert detail["state"] == "INCLUDED-TIMED"
    assert detail["timestamp_ok"] is True
    assert detail["gen_time"] is not None
    assert detail["errors"] == []


@pytest.mark.offline
def test_timed_and_untimed_are_different_states():
    root = hashlib.sha256(b"merkle").digest()
    untimed, keys_a = _two_leaf_anchor(root)
    timed, keys_b = _two_leaf_anchor(
        root, token_b64=base64.b64encode(b"token").decode())
    a = rk._rk_verify_anchor(untimed, root, keys_a)
    b = rk._rk_verify_anchor(timed, root, keys_b, _good_tsa)
    assert a["state"] != b["state"]
    assert {a["state"], b["state"]} == {
        "INCLUDED-UNTIMED", "INCLUDED-TIMED"}


@pytest.mark.offline
def test_present_but_failing_token_is_not_untimed():
    # A token that does not verify must NOT silently degrade to the untimed
    # state: that would launder a broken time claim into a valid one.
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(
        root, token_b64=base64.b64encode(b"token").decode())
    detail = rk._rk_verify_anchor(block, root, keys, _bad_tsa)
    assert detail["inclusion_ok"] is True
    assert detail["timestamp_ok"] is False
    assert detail["state"] is None
    assert any("timestamp:" in e for e in detail["errors"])


@pytest.mark.offline
def test_token_without_a_supplied_verifier_fails_closed():
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(
        root, token_b64=base64.b64encode(b"token").decode())
    detail = rk._rk_verify_anchor(block, root, keys, None)
    assert detail["state"] is None
    assert any("no verifier was supplied" in e for e in detail["errors"])


@pytest.mark.offline
def test_wrong_merkle_root_breaks_the_leaf_tie():
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(root)
    detail = rk._rk_verify_anchor(block, hashlib.sha256(b"other").digest(),
                                  keys)
    assert detail["leaf_digest_ok"] is False
    assert detail["leaf_sig_ok"] is False
    assert detail["state"] is None


@pytest.mark.offline
def test_tampered_inclusion_proof_fails():
    root = hashlib.sha256(b"merkle").digest()
    block, keys = _two_leaf_anchor(root)
    block["inclusion_proof_hashes"] = [
        base64.b64encode(b"\x00" * 32).decode()]
    detail = rk._rk_verify_anchor(block, root, keys)
    assert detail["inclusion_ok"] is False
    assert detail["checkpoint_sig_ok"] is True
    assert detail["state"] is None


@pytest.mark.offline
def test_unknown_origin_fails_closed():
    root = hashlib.sha256(b"merkle").digest()
    block, _ = _two_leaf_anchor(root)
    detail = rk._rk_verify_anchor(block, root, {})
    assert detail["checkpoint_sig_ok"] is False
    assert detail["state"] is None
    assert any("allowlist" in e for e in detail["errors"])


@pytest.mark.offline
def test_v1_leaf_is_refused():
    body = json.dumps({"kind": "hashedrekord", "apiVersion": "0.0.1",
                       "spec": {}}, sort_keys=True).encode()
    with pytest.raises(rk._RkMalformed) as exc:
        rk._rk_parse_leaf(body)
    assert "0.0.2" in str(exc.value)


@pytest.mark.offline
def test_dsse_leaf_is_refused():
    body = json.dumps({"kind": "dsse", "apiVersion": "0.0.2",
                       "spec": {}}, sort_keys=True).encode()
    with pytest.raises(rk._RkMalformed):
        rk._rk_parse_leaf(body)


@pytest.mark.offline
def test_v1_anchor_block_is_refused():
    with pytest.raises(rk._RkMalformed) as exc:
        rk._rk_verify_anchor({"log_index": 0}, b"x", {})
    assert "rekor_api_version" in str(exc.value)


@pytest.mark.offline
def test_carried_key_contradicting_a_builtin_pin_fails_closed():
    forged = base64.b64encode(b"\x02" * 32).decode()
    with pytest.raises(rk._RkMalformed) as exc:
        rk._rk_resolve_log_keys(None, None, {_PINNED_ORIGIN: forged})
    assert "contradicts" in str(exc.value)


@pytest.mark.offline
def test_log_key_provenance_ordering(tmp_path):
    keys, provenance = rk._rk_resolve_log_keys(None, None, None)
    assert provenance == "verifier-pinned"
    assert _PINNED_ORIGIN in keys

    extra = base64.b64encode(b"\x03" * 32).decode()
    keys, provenance = rk._rk_resolve_log_keys(
        None, None, {"other-log.example": extra})
    assert provenance == "operator-supplied"
    assert "other-log.example" in keys and _PINNED_ORIGIN in keys

    pinned = tmp_path / "rekor_log_keys.json"
    pinned.write_text(json.dumps({_ORIGIN: extra}), encoding="ascii")
    keys, provenance = rk._rk_resolve_log_keys(
        None, str(pinned), {"other-log.example": extra})
    assert provenance == "auditor-pinned"
    assert list(keys) == [_ORIGIN]


@pytest.mark.offline
def test_parses_the_real_production_checkpoint():
    if not _FIXTURE.is_file():
        pytest.skip("real checkpoint fixture not present")
    cp = rk._rk_parse_checkpoint(_FIXTURE.read_text(encoding="utf-8"))
    assert cp["origin"] == _PINNED_ORIGIN
    assert cp["tree_size"] > 0
    assert len(cp["root_hash"]) == 32
    builtin, provenance = rk._rk_resolve_log_keys(None, None, None)
    assert provenance == "verifier-pinned"
    expected = rk._rk_ed25519_key_id(_PINNED_ORIGIN, builtin[_PINNED_ORIGIN])
    assert any(s[0] == _PINNED_ORIGIN and s[1] == expected
               for s in cp["signatures"])


@pytest.mark.offline
def test_checkpoint_without_blank_separator_is_refused():
    with pytest.raises(rk._RkMalformed):
        rk._rk_parse_checkpoint("origin\n1\nAAAA\n\u2014 origin AAAA\n")


@pytest.mark.offline
def test_checkpoint_with_crlf_is_refused():
    with pytest.raises(rk._RkMalformed) as exc:
        rk._rk_parse_checkpoint("origin\r\n1\r\nAAAA\r\n\r\n")
    assert "CR" in str(exc.value)
