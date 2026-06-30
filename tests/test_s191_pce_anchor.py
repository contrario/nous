"""S191 4a: pce_anchor absolute pre-commitment receipt.

Network is monkeypatched; no live Rekor/TSA POST is performed. The Rekor leg
uses the real RekorAnchorV2 so to_manifest_block() is exercised end to end.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

import pce_anchor as pa

GOOD_ENV = {
    "pce_schema_version": 1,
    "basis": "Membership evidence only; not a legal substantiality "
    "determination.",
    "baseline_canon_sha256": "a" * 64,
    "per_step": {"SA": {"mutable": False}},
}
GOOD_BYTES = json.dumps(
    GOOD_ENV, sort_keys=True, separators=(",", ":")
).encode("utf-8")

FAKE_BLOCK = {
    "rekor_api_version": 2,
    "log_id": "log2025-1",
    "log_index": 7,
    "body_b64": "eyJ4IjogMX0=",
    "checkpoint_envelope": "origin\n7\nROOTHASH\n",
    "inclusion_proof_hashes": ["aa", "bb"],
}
FAKE_TOKEN = b"\x30\x82\x01\x00DER-TSTOKEN-PLACEHOLDER"


def test_receipt_binds_envelope_sha() -> None:
    r = pa.build_pce_anchor_receipt(
        pce_bytes=GOOD_BYTES,
        rekor_v2_block=dict(FAKE_BLOCK),
        pce_rfc3161_token_der=FAKE_TOKEN,
    )
    assert r["pce_anchor_schema_version"] == 1
    assert r["anchored_pce_sha256"] == hashlib.sha256(GOOD_BYTES).hexdigest()
    assert base64.b64decode(r["pce_rfc3161_token_b64"]) == FAKE_TOKEN
    assert r["rekor_v2"] == FAKE_BLOCK


def test_receipt_keys_are_exactly_five_absolute_fields() -> None:
    r = pa.build_pce_anchor_receipt(
        pce_bytes=GOOD_BYTES,
        rekor_v2_block=dict(FAKE_BLOCK),
        pce_rfc3161_token_der=FAKE_TOKEN,
    )
    assert set(r.keys()) == {
        "pce_anchor_schema_version",
        "anchored_pce_sha256",
        "basis",
        "rekor_v2",
        "pce_rfc3161_token_b64",
    }


def test_no_ordering_claim_in_structured_fields() -> None:
    r = pa.build_pce_anchor_receipt(
        pce_bytes=GOOD_BYTES,
        rekor_v2_block=dict(FAKE_BLOCK),
        pce_rfc3161_token_der=FAKE_TOKEN,
    )
    struct = dict(r)
    basis = struct.pop("basis")
    flat = json.dumps(struct).lower()
    for tok in (
        "preced", "temporal_precedence", '"within"', '"outside"',
        "ordering", "anteriorit", "before", "after",
    ):
        assert tok not in flat, tok
    assert "asserts no ordering" in basis
    assert "not a legal substantiality determination" in basis
    assert "preced" not in basis.lower()
    assert "anteriorit" not in basis.lower()


def test_receipt_canonical_deterministic() -> None:
    r = pa.build_pce_anchor_receipt(
        pce_bytes=GOOD_BYTES,
        rekor_v2_block=dict(FAKE_BLOCK),
        pce_rfc3161_token_der=FAKE_TOKEN,
    )
    c1 = pa._canonical_bytes(r)
    c2 = pa._canonical_bytes(json.loads(c1.decode("utf-8")))
    assert c1 == c2


def test_non_v2_block_refused() -> None:
    with pytest.raises(pa.PceAnchorError):
        pa.build_pce_anchor_receipt(
            pce_bytes=GOOD_BYTES,
            rekor_v2_block={"rekor_api_version": 1},
            pce_rfc3161_token_der=FAKE_TOKEN,
        )


def _patch_transport(monkeypatch, captured):
    from rekor_verify_v2 import RekorAnchorV2
    import rekor_anchor_v2
    import tsa_client

    def fake_rekor(*, manifest_canonical_bytes, client=None,
                   base_url=None, timeout_seconds=None):
        captured["rekor_bytes"] = manifest_canonical_bytes
        return RekorAnchorV2(
            log_id="log2025-1",
            log_index=7,
            body_b64="eyJ4IjogMX0=",
            checkpoint_envelope="origin\n7\nROOTHASH\n",
            inclusion_proof_hashes=["aa", "bb"],
        )

    def fake_tsa(*, timestamped_data, client=None, base_url=None,
                 timeout_seconds=None):
        captured["tsa_bytes"] = timestamped_data
        return FAKE_TOKEN

    monkeypatch.setattr(
        rekor_anchor_v2, "anchor_manifest_to_rekor_v2", fake_rekor
    )
    monkeypatch.setattr(tsa_client, "anchor_timestamp", fake_tsa)


def test_anchor_pce_writes_receipt(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    _patch_transport(monkeypatch, captured)
    pce_p = tmp_path / "pce.json"
    pce_p.write_bytes(GOOD_BYTES)

    out = pa.anchor_pce(pce_p)

    assert out == tmp_path / "pce.anchor.json"
    assert captured["rekor_bytes"] == GOOD_BYTES
    assert captured["tsa_bytes"] == GOOD_BYTES
    written = json.loads(out.read_bytes().decode("utf-8"))
    assert written["anchored_pce_sha256"] == hashlib.sha256(
        GOOD_BYTES
    ).hexdigest()
    assert written["rekor_v2"]["rekor_api_version"] == 2
    assert out.read_bytes() == pa._canonical_bytes(written)


def test_anchor_pce_refuses_non_json(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    _patch_transport(monkeypatch, captured)
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"not json {")
    with pytest.raises(pa.PceAnchorError):
        pa.anchor_pce(bad)
    assert "rekor_bytes" not in captured


def test_anchor_pce_refuses_non_envelope(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    _patch_transport(monkeypatch, captured)
    notenv = tmp_path / "notenv.json"
    notenv.write_bytes(json.dumps({"hello": "world"}).encode("utf-8"))
    with pytest.raises(pa.PceAnchorError):
        pa.anchor_pce(notenv)
    assert "rekor_bytes" not in captured


def test_anchor_pce_custom_out_path(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    _patch_transport(monkeypatch, captured)
    pce_p = tmp_path / "pce.json"
    pce_p.write_bytes(GOOD_BYTES)
    custom = tmp_path / "sub" / "receipt.json"
    custom.parent.mkdir()
    out = pa.anchor_pce(pce_p, out_path=custom)
    assert out == custom
    assert custom.is_file()
