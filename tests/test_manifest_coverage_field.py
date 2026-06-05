"""Tests for the policy_coverage_sha256 manifest field (S115 P3a)."""
from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from manifest import (
    Manifest,
    manifest_json,
    parse_manifest_json,
    sign_manifest,
)


def _base_manifest(**over) -> Manifest:
    defaults = dict(
        schema_version="1",
        nous_version="5.26.1",
        smt_emit_version="1",
        source_sha256="a" * 64,
        pricing_sha256="b" * 64,
        smt_spec_sha256="c" * 64,
        world_name="W",
        cost_cap_usd="0.50",
        max_ticks=1,
        verdict="proven",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=10,
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )
    defaults.update(over)
    return Manifest(**defaults)


def test_coverage_sha_absent_is_byte_identical() -> None:
    m = _base_manifest()
    d = m.canonical_dict()
    assert "policy_coverage_sha256" not in d
    assert m.policy_coverage_sha256 is None


def test_coverage_sha_present_is_emitted() -> None:
    sha = "d" * 64
    m = _base_manifest(policy_coverage_sha256=sha)
    d = m.canonical_dict()
    assert d["policy_coverage_sha256"] == sha


def test_coverage_sha_roundtrips_through_json() -> None:
    sha = "e" * 64
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    m = _base_manifest(policy_coverage_sha256=sha)
    sig = sign_manifest(m, priv)
    text = manifest_json(m, sig, pub)
    m2, _sig2, _pub2 = parse_manifest_json(text)
    assert m2.policy_coverage_sha256 == sha


def test_coverage_sha_signature_covers_field() -> None:
    sha = "f" * 64
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    m = _base_manifest(policy_coverage_sha256=sha)
    sig = sign_manifest(m, priv)
    text = manifest_json(m, sig, pub)
    doc = json.loads(text)
    doc["policy_coverage_sha256"] = "0" * 64
    body = {k: v for k, v in doc.items() if k != "signature"}
    body_bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    from cryptography.exceptions import InvalidSignature
    sig_bytes = base64.b64decode(doc["signature"]["signature_b64"])
    raised = False
    try:
        pub.verify(sig_bytes, body_bytes)
    except InvalidSignature:
        raised = True
    assert raised


def test_none_manifest_canonical_unchanged_keys() -> None:
    m = _base_manifest()
    keys = set(m.canonical_dict().keys())
    expected = {
        "schema_version", "nous_version", "smt_emit_version",
        "source_sha256", "pricing_sha256", "smt_spec_sha256",
        "world_name", "cost_cap_usd", "max_ticks", "verdict",
        "solver_name", "solver_version", "elapsed_ms", "timestamp_utc",
    }
    assert keys == expected


def test_smt2_sha_absent_is_byte_identical() -> None:
    m = _base_manifest()
    assert "coverage_smt2_sha256" not in m.canonical_dict()
    assert m.coverage_smt2_sha256 is None


def test_smt2_sha_roundtrips_and_is_signed() -> None:
    import base64 as _b64
    import json as _json
    from cryptography.exceptions import InvalidSignature
    sha = "9" * 64
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    m = _base_manifest(
        policy_coverage_sha256="a" * 64,
        coverage_smt2_sha256=sha,
    )
    sig = sign_manifest(m, priv)
    text = manifest_json(m, sig, pub)
    m2, _s, _p = parse_manifest_json(text)
    assert m2.coverage_smt2_sha256 == sha
    doc = _json.loads(text)
    doc["coverage_smt2_sha256"] = "0" * 64
    body = {k: v for k, v in doc.items() if k != "signature"}
    bb = _json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    raised = False
    try:
        pub.verify(_b64.b64decode(doc["signature"]["signature_b64"]), bb)
    except InvalidSignature:
        raised = True
    assert raised
