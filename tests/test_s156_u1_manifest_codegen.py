"""S156 U1: codegen_sha256 manifest leg (fourth subject leg).

Mirrors test_manifest_coverage_field.py: drop-when-None (absent ==>
byte-identical to a pre-S156 manifest), emitted when set, round-trips through
signed JSON, and covered by the Ed25519 signature. EVIDENCES the compiled
program identity; does not prove the program ran.
__s156_u1_manifest_codegen_test_v1__
"""
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
        schema_version="1.0",
        nous_version="5.54.0",
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


def test_codegen_absent_is_byte_identical() -> None:
    m = _base_manifest()
    d = m.canonical_dict()
    assert "codegen_sha256" not in d
    assert m.codegen_sha256 is None


def test_codegen_absent_canonical_bytes_match_explicit_none() -> None:
    a = _base_manifest().canonical_bytes()
    b = _base_manifest(codegen_sha256=None).canonical_bytes()
    assert a == b
    assert b"codegen_sha256" not in a


def test_codegen_present_is_emitted() -> None:
    sha = "d" * 64
    m = _base_manifest(codegen_sha256=sha)
    assert m.canonical_dict()["codegen_sha256"] == sha


def test_codegen_roundtrips_through_json() -> None:
    sha = "e" * 64
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    m = _base_manifest(codegen_sha256=sha)
    sig = sign_manifest(m, priv)
    text = manifest_json(m, sig, pub)
    m2, _sig2, _pub2 = parse_manifest_json(text)
    assert m2.codegen_sha256 == sha


def test_codegen_signature_covers_field() -> None:
    sha = "f" * 64
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    m = _base_manifest(codegen_sha256=sha)
    sig = sign_manifest(m, priv)
    text = manifest_json(m, sig, pub)
    doc = json.loads(text)
    doc["codegen_sha256"] = "0" * 64
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


def test_codegen_keys_match_base_plus_one_when_set() -> None:
    base_keys = set(_base_manifest().canonical_dict().keys())
    with_keys = set(
        _base_manifest(codegen_sha256="1" * 64).canonical_dict().keys()
    )
    assert with_keys - base_keys == {"codegen_sha256"}
