"""S91 -- Rekor v2 anchor dispatch tests.

Proves parse_manifest_json_with_anchor_v2 routes the transparency_log block
by its rekor_api_version discriminator, and that the v1 path is identical to
the untouched 4-tuple parser down to every RekorAnchor field.

Fixtures (real, repo-shipped):
  - rekor_fixtures/v1_full_manifest.json: a real unanchored manifest emitted
    by the manifest_from_verify -> sign_manifest -> manifest_json chain.
  - rekor_fixtures/valid_anchor.json: the canonical v1 transparency_log block.

The v1 regression guard pins each RekorAnchor field to its source key in
valid_anchor.json, so any change to RekorAnchor.from_manifest_block's field
mapping turns this test red.

# __nous_s91_anchor_dispatch_pytest_v1__
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from manifest import (
    parse_manifest_json_with_anchor,
    parse_manifest_json_with_anchor_v2,
    public_key_b64,
)

FIX = Path(__file__).parent / "rekor_fixtures"


def _base_manifest() -> dict:
    return json.loads((FIX / "v1_full_manifest.json").read_text("utf-8"))


def _v1_block() -> dict:
    return json.loads((FIX / "valid_anchor.json").read_text("utf-8"))


def _text(manifest: dict) -> str:
    return json.dumps(manifest)


def test_absent_block_routes_v1_none_v2_none() -> None:
    base = _base_manifest()
    assert "transparency_log" not in base
    m, sig, pub, anchor_v1, block_v2 = parse_manifest_json_with_anchor_v2(
        _text(base)
    )
    assert anchor_v1 is None
    assert block_v2 is None


def test_v1_block_routes_v1_and_field_identical() -> None:
    base = _base_manifest()
    blk = _v1_block()
    base["transparency_log"] = blk
    text = _text(base)

    m2, sig2, pub2, anchor_v1, block_v2 = parse_manifest_json_with_anchor_v2(
        text
    )
    m1, sig1, pub1, anchor_4tuple = parse_manifest_json_with_anchor(text)

    assert block_v2 is None
    assert anchor_v1 is not None

    assert m2 == m1
    assert sig2 == sig1
    assert public_key_b64(pub2) == public_key_b64(pub1)
    assert anchor_v1 == anchor_4tuple

    assert anchor_v1.log_id == blk["log_id"]
    assert anchor_v1.log_index == int(blk["log_index"])
    assert anchor_v1.integrated_time == int(blk["integrated_time"])
    assert (
        anchor_v1.signed_entry_timestamp_b64
        == blk["signed_entry_timestamp_b64"]
    )
    assert anchor_v1.body_b64 == blk["body_b64"]
    assert anchor_v1.rekor_public_key_pem == blk["rekor_public_key_pem"]
    assert anchor_v1.provider == blk.get("provider", "sigstore-rekor")


def test_v1_explicit_version_routes_v1() -> None:
    base = _base_manifest()
    blk = dict(_v1_block())
    blk["rekor_api_version"] = 1
    base["transparency_log"] = blk
    _, _, _, anchor_v1, block_v2 = parse_manifest_json_with_anchor_v2(
        _text(base)
    )
    assert anchor_v1 is not None
    assert block_v2 is None


def test_v2_block_routes_v2() -> None:
    base = _base_manifest()
    v2 = {
        "rekor_api_version": 2,
        "log_id": "log2025-1",
        "log_index": 7,
        "body_b64": "e30=",
    }
    base["transparency_log"] = v2
    _, _, _, anchor_v1, block_v2 = parse_manifest_json_with_anchor_v2(
        _text(base)
    )
    assert anchor_v1 is None
    assert block_v2 == v2


def test_unsupported_version_refuses() -> None:
    base = _base_manifest()
    base["transparency_log"] = {"rekor_api_version": 3, "log_id": "x"}
    with pytest.raises(ValueError) as exc:
        parse_manifest_json_with_anchor_v2(_text(base))
    assert "exceeds MAX_SUPPORTED_REKOR_API_VERSION" in str(exc.value)


def test_non_integer_version_refuses() -> None:
    base = _base_manifest()
    base["transparency_log"] = {"rekor_api_version": True, "log_id": "x"}
    with pytest.raises(ValueError) as exc:
        parse_manifest_json_with_anchor_v2(_text(base))
    assert "not an integer" in str(exc.value)
