"""S134 2c-1: manifest source_kind discriminator + gap_witness_sha256 binding.

B1 schema unit (test-only, byte-identical). Adds two drop-when-None fields to
the frozen Manifest: source_kind (None => coverage, "gap-witness" => a
REFUTATION artifact) and gap_witness_sha256 (the crypto-only binding of the
gap-witness sidecar). A __post_init__ enforces coherence and axiom-8 mutual
exclusivity with coverage bindings via the typed ManifestCoherenceError.

The discriminator lives inside Manifest.canonical_dict -- the Ed25519-signed
body -- so a coverage dossier cannot be silently relabeled a refutation (or
vice versa) without breaking the signature (type-confusion avoidance). This
module proves: byte-identity for legacy manifests, round-trip through all
parse paths, coherence refusals, and the signature-binding property.

BOUNDARY: source_kind labels the KIND of claim; it does not itself prove the
claim. A gap-witness manifest asserts a gap exists at a point, not legal
sufficiency nor real-world harm.
"""
from __future__ import annotations

from typing import Any

import pytest

from manifest import (
    Manifest,
    ManifestCoherenceError,
    manifest_json,
    parse_manifest_json,
    parse_manifest_json_with_anchor,
    parse_manifest_json_with_anchor_v2,
)


def _base(**over: Any) -> Manifest:
    fields = dict(
        schema_version="1",
        nous_version="5.36.0",
        smt_emit_version="1",
        source_sha256="0" * 64,
        pricing_sha256="1" * 64,
        smt_spec_sha256="2" * 64,
        world_name="w",
        cost_cap_usd="10.00",
        max_ticks=100,
        verdict="PASS",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=5,
        timestamp_utc="2026-06-12T00:00:00+00:00",
    )
    fields.update(over)
    return Manifest(**fields)


def _signed(m: Manifest) -> "tuple[bytes, Any]":
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    sk = Ed25519PrivateKey.generate()
    return sk.sign(m.canonical_bytes()), sk.public_key()


def test_legacy_byte_identity() -> None:
    m = _base()
    d = m.canonical_dict()
    assert "source_kind" not in d
    assert "gap_witness_sha256" not in d
    body = m.canonical_bytes()
    assert b"source_kind" not in body
    assert b"gap_witness_sha256" not in body


def test_coverage_dossier_unaffected() -> None:
    m = _base(coverage_farkas_sha256="b" * 64)
    d = m.canonical_dict()
    assert d["coverage_farkas_sha256"] == "b" * 64
    assert "source_kind" not in d


def test_gap_witness_canonical_includes_fields() -> None:
    m = _base(source_kind="gap-witness", gap_witness_sha256="a" * 64)
    d = m.canonical_dict()
    assert d["source_kind"] == "gap-witness"
    assert d["gap_witness_sha256"] == "a" * 64


def test_round_trip_parse_manifest_json() -> None:
    m = _base(source_kind="gap-witness", gap_witness_sha256="a" * 64)
    sig, pub = _signed(m)
    text = manifest_json(m, sig, pub)
    m2, _sig2, _pub2 = parse_manifest_json(text)
    assert m2 == m
    assert m2.source_kind == "gap-witness"
    assert m2.gap_witness_sha256 == "a" * 64


def test_round_trip_parse_with_anchor() -> None:
    m = _base(source_kind="gap-witness", gap_witness_sha256="a" * 64)
    sig, pub = _signed(m)
    text = manifest_json(m, sig, pub)
    m2, _s, _p, anchor = parse_manifest_json_with_anchor(text)
    assert anchor is None
    assert m2 == m


def test_round_trip_parse_with_anchor_v2() -> None:
    m = _base(source_kind="gap-witness", gap_witness_sha256="a" * 64)
    sig, pub = _signed(m)
    text = manifest_json(m, sig, pub)
    m2, _s, _p, a1, a2 = parse_manifest_json_with_anchor_v2(text)
    assert a1 is None
    assert a2 is None
    assert m2 == m


def test_legacy_round_trip_unchanged() -> None:
    m = _base(coverage_farkas_sha256="b" * 64)
    sig, pub = _signed(m)
    text = manifest_json(m, sig, pub)
    m2, _s, _p = parse_manifest_json(text)
    assert m2 == m
    assert m2.source_kind is None
    assert m2.gap_witness_sha256 is None


def test_signature_binds_source_kind() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.exceptions import InvalidSignature
    sk = Ed25519PrivateKey.generate()
    pub = sk.public_key()
    gap = _base(source_kind="gap-witness", gap_witness_sha256="a" * 64)
    cov = _base()
    sig = sk.sign(gap.canonical_bytes())
    pub.verify(sig, gap.canonical_bytes())
    with pytest.raises(InvalidSignature):
        pub.verify(sig, cov.canonical_bytes())


def test_legacy_constructs_fine() -> None:
    _base()
    _base(coverage_farkas_sha256="b" * 64)
    _base(coverage_smt2_sha256="c" * 64, policy_coverage_sha256="d" * 64)


@pytest.mark.parametrize(
    "over",
    [
        {"source_kind": "bogus"},
        {"source_kind": "coverage"},
        {"source_kind": "gap-witness"},
        {"gap_witness_sha256": "a" * 64},
        {"source_kind": "gap-witness", "gap_witness_sha256": "xyz"},
        {"source_kind": "gap-witness", "gap_witness_sha256": "A" * 64},
        {"source_kind": "gap-witness", "gap_witness_sha256": "a" * 63},
        {
            "source_kind": "gap-witness",
            "gap_witness_sha256": "a" * 64,
            "coverage_farkas_sha256": "b" * 64,
        },
        {
            "source_kind": "gap-witness",
            "gap_witness_sha256": "a" * 64,
            "coverage_smt2_sha256": "b" * 64,
        },
        {
            "source_kind": "gap-witness",
            "gap_witness_sha256": "a" * 64,
            "policy_coverage_sha256": "b" * 64,
        },
    ],
)
def test_coherence_refusals(over: dict) -> None:
    with pytest.raises(ManifestCoherenceError):
        _base(**over)
