"""S119 -- tests for the signed, drop-when-None prior_digest field.

Field-only unit (per the envelope-binding freeze, section 5.1 + 6). These
tests assert the three guarantees the freeze requires of the field, and the
genesis/re-binding discriminator. They do NOT exercise any producer wiring,
chain-carrying dossier, or offline chain-walk -- those are later units.
"""
from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from manifest import (
    Manifest,
    manifest_json,
    parse_manifest_json,
    sign_manifest,
    verify_manifest_signature,
)


def _base_manifest(**overrides: object) -> Manifest:
    """A minimal PROVEN manifest with all required fields set."""
    fields: dict = dict(
        schema_version="1",
        nous_version="5.28.0",
        smt_emit_version="1",
        source_sha256="a" * 64,
        pricing_sha256="b" * 64,
        smt_spec_sha256="c" * 64,
        world_name="test_world",
        cost_cap_usd="1.00",
        max_ticks=10,
        verdict="proven",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=5,
        timestamp_utc="2026-06-08T00:00:00+00:00",
    )
    fields.update(overrides)
    return Manifest(**fields)


def test_genesis_omits_prior_digest_key() -> None:
    """prior_digest=None -> key absent from canonical_dict and bytes."""
    g = _base_manifest()
    assert g.prior_digest is None
    assert "prior_digest" not in g.canonical_dict()
    assert b"prior_digest" not in g.canonical_bytes()


def test_byte_identity_none_matches_explicit_none() -> None:
    """A manifest that never sets prior_digest is byte-identical to one that
    sets it explicitly to None. This is the guarantee that pre-field manifests
    and pre-existing signatures stay valid byte-for-byte."""
    a = _base_manifest()
    b = _base_manifest(prior_digest=None)
    assert a.canonical_bytes() == b.canonical_bytes()
    assert manifest_json(a, b"\x00" * 64, _pub()) == manifest_json(
        b, b"\x00" * 64, _pub()
    )


def _priv() -> Ed25519PrivateKey:
    seed = b"\x01" * 32
    return Ed25519PrivateKey.from_private_bytes(seed)


def _pub():  # type: ignore[no-untyped-def]
    return _priv().public_key()


def test_genesis_golden_canonical_bytes() -> None:
    """Golden: the genesis canonical body is exactly the pre-field layout
    (sorted compact JSON, no prior_digest key). Byte-for-byte pinned so a
    regression that shifts the field's emission is caught here."""
    g = _base_manifest()
    expected = (
        b'{"cost_cap_usd":"1.00","elapsed_ms":5,"max_ticks":10,'
        b'"nous_version":"5.28.0","pricing_sha256":"'
        + b"b" * 64
        + b'","schema_version":"1","smt_emit_version":"1",'
        b'"smt_spec_sha256":"'
        + b"c" * 64
        + b'","solver_name":"z3","solver_version":"4.16.0",'
        b'"source_sha256":"'
        + b"a" * 64
        + b'","timestamp_utc":"2026-06-08T00:00:00+00:00",'
        b'"verdict":"proven","world_name":"test_world"}'
    )
    assert g.canonical_bytes() == expected


def test_rebinding_includes_prior_digest_alphabetically() -> None:
    """prior_digest set -> present in canonical bytes, placed by sort_keys
    (between pricing_sha256 and schema_version, alphabetically)."""
    rb = _base_manifest(prior_digest="d" * 64)
    body = rb.canonical_bytes().decode("utf-8")
    assert '"prior_digest":"' + "d" * 64 + '"' in body
    # alphabetical neighbours: pricing_sha256 < prior_digest < schema_version
    assert body.index("pricing_sha256") < body.index("prior_digest")
    assert body.index("prior_digest") < body.index("schema_version")


def test_signed_body_includes_prior_digest() -> None:
    """A re-binding manifest signs OVER prior_digest: the signature verifies,
    and tampering prior_digest after signing breaks verification."""
    priv = _priv()
    rb = _base_manifest(prior_digest="d" * 64)
    sig = sign_manifest(rb, priv)
    assert verify_manifest_signature(rb, sig, priv.public_key())
    # Same bytes, different prior_digest -> signature must NOT verify.
    tampered = _base_manifest(prior_digest="e" * 64)
    assert not verify_manifest_signature(tampered, sig, priv.public_key())


def test_genesis_signature_unaffected_by_field_existence() -> None:
    """A genesis manifest (no prior_digest) signs and verifies exactly as a
    pre-field manifest would: the field's mere existence in the schema does
    not perturb the signed bytes."""
    priv = _priv()
    g = _base_manifest()
    sig = sign_manifest(g, priv)
    assert verify_manifest_signature(g, sig, priv.public_key())
    assert b"prior_digest" not in g.canonical_bytes()


def test_round_trip_through_parse_preserves_prior_digest() -> None:
    """manifest_json -> parse_manifest_json round-trips prior_digest and the
    parsed manifest re-derives the identical canonical bytes (determinism)."""
    priv = _priv()
    rb = _base_manifest(prior_digest="f" * 64)
    sig = sign_manifest(rb, priv)
    text = manifest_json(rb, sig, priv.public_key())
    parsed, psig, ppub = parse_manifest_json(text)
    assert parsed.prior_digest == "f" * 64
    assert parsed.canonical_bytes() == rb.canonical_bytes()
    assert verify_manifest_signature(parsed, psig, ppub)


def test_round_trip_genesis_prior_digest_none() -> None:
    """A genesis manifest round-trips with prior_digest None (key absent)."""
    priv = _priv()
    g = _base_manifest()
    sig = sign_manifest(g, priv)
    text = manifest_json(g, sig, priv.public_key())
    assert "prior_digest" not in text
    parsed, psig, ppub = parse_manifest_json(text)
    assert parsed.prior_digest is None
    assert parsed.canonical_bytes() == g.canonical_bytes()


def test_determinism_same_inputs_same_digest() -> None:
    """Identical inputs -> identical canonical bytes -> identical sha256."""
    a = _base_manifest(prior_digest="d" * 64)
    b = _base_manifest(prior_digest="d" * 64)
    da = hashlib.sha256(a.canonical_bytes()).hexdigest()
    db = hashlib.sha256(b.canonical_bytes()).hexdigest()
    assert da == db
