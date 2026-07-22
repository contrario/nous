"""C4 conformance: Rekor v2 transparency-log checkpoint anchors (SPEC 10.1).

__nous_trace_rekor_backend_newtest_v1__

offline: a failed SUBMISSION degrades to an unanchored checkpoint (SPEC 10.2);
         a successful submission whose TSA leg fails yields an INCLUDED-UNTIMED
         block (transparency inclusion, no trusted time), while a successful
         TSA leg yields INCLUDED-TIMED; the Producer never declares a time; the
         leaf binds the checkpoint Merkle root.
live:    a real submission to the production Rekor v2 log.

The timed and untimed states are STRUCTURALLY distinct (presence of
rfc3161_token_b64), not a prose flag: they carry different assurance and must
not collapse into one verdict. anchor_failures is PRODUCER-ASSERTED -- it
records what this Producer observed, and a Verifier can only report that no
trusted time is present, never that a TSA was unavailable.
"""
from __future__ import annotations

import base64
import hashlib
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

import rekor_anchor_v2
import tsa_client
from rekor_entry import parse_rekor_leaf
from rekor_verify_v2 import RekorAnchorV2
from trace_bridge import TraceBridge

_FAKE_TOKEN = b"\x30\x03FAKE-TSA-TOKEN"


def _synthetic_v2_anchor(signed_bytes):
    key = ec.generate_private_key(ec.SECP256R1())
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
    body_b64 = base64.b64encode(
        json.dumps(leaf, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    return RekorAnchorV2(
        rekor_api_version=2,
        log_id="test-log-id",
        log_index=0,
        body_b64=body_b64,
        checkpoint_envelope="test-origin\n1\nAAAA\n\n",
        inclusion_proof_hashes=[])


def _checkpoints(pack):
    events = [json.loads(line) for line
              in (pack / "trace.ndjson").read_text().splitlines()
              if line.strip()]
    return [e for e in events if e["event_type"] == "checkpoint"]


def _run(tmp_path, monkeypatch, submit, timestamp):
    pack = tmp_path / "pack"
    if submit is not None:
        monkeypatch.setattr(
            rekor_anchor_v2, "anchor_manifest_to_rekor_v2", submit)
    if timestamp is not None:
        monkeypatch.setattr(tsa_client, "anchor_timestamp", timestamp)
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="rekor") as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    return pack, br


@pytest.mark.offline
def test_rekor_submit_failure_degrades_to_unanchored(tmp_path, monkeypatch):
    def _boom(data, **kwargs):
        raise RuntimeError("log unreachable")

    pack, br = _run(tmp_path, monkeypatch, _boom, None)
    man = json.loads((pack / "manifest.json").read_text())
    assert man["anchoring"] == "rekor"
    ckpts = _checkpoints(pack)
    assert ckpts and all(e["body"]["anchor"] is None for e in ckpts)
    stages = [f.get("stage") for f in br.anchor_failures]
    assert "rekor" in stages, br.anchor_failures


@pytest.mark.offline
def test_included_untimed_when_tsa_leg_fails(tmp_path, monkeypatch):
    def _submit(data, **kwargs):
        return _synthetic_v2_anchor(data)

    def _boom(**kwargs):
        raise RuntimeError("tsa unreachable")

    pack, br = _run(tmp_path, monkeypatch, _submit, _boom)
    anchor = _checkpoints(pack)[-1]["body"]["anchor"]
    assert anchor["type"] == "rekor"
    assert anchor["rekor_api_version"] == 2
    assert "rfc3161_token_b64" not in anchor
    assert "gen_time" not in anchor
    stages = [f.get("stage") for f in br.anchor_failures]
    assert "rekor-timestamp" in stages, br.anchor_failures


@pytest.mark.offline
def test_included_timed_binds_token_to_leaf_signature(tmp_path, monkeypatch):
    captured = {}

    def _submit(data, **kwargs):
        return _synthetic_v2_anchor(data)

    def _stamp(**kwargs):
        captured["data"] = kwargs["timestamped_data"]
        return _FAKE_TOKEN

    pack, br = _run(tmp_path, monkeypatch, _submit, _stamp)
    anchor = _checkpoints(pack)[-1]["body"]["anchor"]
    assert anchor["type"] == "rekor"
    assert base64.b64decode(anchor["rfc3161_token_b64"]) == _FAKE_TOKEN
    assert "gen_time" not in anchor
    assert not br.anchor_failures, br.anchor_failures
    leaf = parse_rekor_leaf(
        json.loads(base64.b64decode(anchor["body_b64"], validate=True)))
    assert captured["data"] == leaf.leaf_signature_der


@pytest.mark.offline
def test_leaf_binds_the_checkpoint_merkle_root(tmp_path, monkeypatch):
    def _submit(data, **kwargs):
        return _synthetic_v2_anchor(data)

    def _stamp(**kwargs):
        return _FAKE_TOKEN

    pack, br = _run(tmp_path, monkeypatch, _submit, _stamp)
    ck = _checkpoints(pack)[-1]
    root = bytes.fromhex(ck["body"]["merkle_root"])
    leaf = parse_rekor_leaf(
        json.loads(base64.b64decode(
            ck["body"]["anchor"]["body_b64"], validate=True)))
    assert leaf.digest_hex == hashlib.sha256(root).hexdigest()
    pub = serialization.load_der_public_key(leaf.leaf_public_key_der)
    pub.verify(leaf.leaf_signature_der, root, ECDSA(hashes.SHA256()))


@pytest.mark.offline
def test_timed_and_untimed_are_structurally_distinct(tmp_path, monkeypatch):
    def _submit(data, **kwargs):
        return _synthetic_v2_anchor(data)

    def _stamp(**kwargs):
        return _FAKE_TOKEN

    def _boom(**kwargs):
        raise RuntimeError("tsa unreachable")

    timed, _ = _run(tmp_path / "a", monkeypatch, _submit, _stamp)
    untimed, _ = _run(tmp_path / "b", monkeypatch, _submit, _boom)
    a = _checkpoints(timed)[-1]["body"]["anchor"]
    b = _checkpoints(untimed)[-1]["body"]["anchor"]
    assert a["type"] == b["type"] == "rekor"
    assert ("rfc3161_token_b64" in a) and ("rfc3161_token_b64" not in b)


@pytest.mark.live
def test_production_rekor_anchor_end_to_end(tmp_path):
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "k"),
                     anchoring="rekor") as br:
        br.tool_call("t", "ad", input_bytes=b"{}")
    assert not br.anchor_failures, br.anchor_failures
    ck = _checkpoints(pack)[-1]
    anchor = ck["body"]["anchor"]
    assert anchor["type"] == "rekor" and anchor["rekor_api_version"] == 2
    assert anchor["log_index"] >= 0
    assert anchor["checkpoint_envelope"]
    assert "gen_time" not in anchor
    root = bytes.fromhex(ck["body"]["merkle_root"])
    leaf = parse_rekor_leaf(
        json.loads(base64.b64decode(anchor["body_b64"], validate=True)))
    assert leaf.digest_hex == hashlib.sha256(root).hexdigest()
