"""S127 U2 tests: chain_coverage_mode manifest discriminator.

__s127_chain_coverage_mode_field_tests_v1__
"""
from __future__ import annotations

import base64
import dataclasses
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from manifest import (
    Manifest,
    parse_manifest_json,
    parse_manifest_json_with_anchor,
)


def _base_manifest() -> Manifest:
    return Manifest(
        schema_version="1",
        nous_version="5.34.0",
        smt_emit_version="1",
        source_sha256="a" * 64,
        pricing_sha256="b" * 64,
        smt_spec_sha256="c" * 64,
        world_name="w",
        cost_cap_usd="1.00",
        max_ticks=3,
        verdict="PROVABLE",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=1,
        timestamp_utc="2026-06-10T00:00:00+00:00",
    )


def _signed_text(m: Manifest) -> str:
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    sig = priv.sign(m.canonical_bytes())
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )
    pub_raw = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    doc = dict(m.canonical_dict())
    doc["signature"] = {
        "algorithm": "ed25519",
        "signature_b64": base64.b64encode(sig).decode("ascii"),
        "public_key_b64": base64.b64encode(pub_raw).decode("ascii"),
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def test_mode_absent_is_byte_identical() -> None:
    m = _base_manifest()
    m_none = dataclasses.replace(m, chain_coverage_mode=None)
    assert m.canonical_bytes() == m_none.canonical_bytes()
    assert "chain_coverage_mode" not in m.canonical_dict()
    assert b"chain_coverage_mode" not in m.canonical_bytes()


def test_mode_present_is_emitted() -> None:
    m = dataclasses.replace(
        _base_manifest(), chain_coverage_mode="blocking-net-full"
    )
    d = m.canonical_dict()
    assert d["chain_coverage_mode"] == "blocking-net-full"
    assert b"blocking-net-full" in m.canonical_bytes()


def test_mode_changes_signed_bytes() -> None:
    m = _base_manifest()
    m_full = dataclasses.replace(
        m, chain_coverage_mode="blocking-net-full"
    )
    assert m.canonical_bytes() != m_full.canonical_bytes()


def test_mode_roundtrips_and_signature_verifies() -> None:
    m = dataclasses.replace(
        _base_manifest(), chain_coverage_mode="blocking-net-full"
    )
    text = _signed_text(m)
    parsed, sig, pub = parse_manifest_json(text)
    assert parsed.chain_coverage_mode == "blocking-net-full"
    pub.verify(sig, parsed.canonical_bytes())


def test_mode_roundtrips_via_anchor_parse_path() -> None:
    m = dataclasses.replace(
        _base_manifest(), chain_coverage_mode="blocking-net-full"
    )
    text = _signed_text(m)
    parsed, sig, pub, anchor = parse_manifest_json_with_anchor(text)
    assert anchor is None
    assert parsed.chain_coverage_mode == "blocking-net-full"
    pub.verify(sig, parsed.canonical_bytes())


def test_mode_absent_roundtrips_as_none() -> None:
    m = _base_manifest()
    text = _signed_text(m)
    parsed, _sig, _pub = parse_manifest_json(text)
    assert parsed.chain_coverage_mode is None
