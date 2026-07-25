"""S262 -- completeness backstop for the manifest drop-when-None law.

The suite already checks drop-when-None, but ONE FIELD AT A TIME, across
nine-plus files, each written by the session that added its field. That
coverage is incidental: field N+1 ships with no test and nothing fails.

This file ENUMERATES the fields instead of naming them, so a newly declared
optional field is covered the moment it exists. Same structural shape as the
release-script wheel-content gate: a backstop against the forgotten
registration, not a restatement of what the code already says.

Three laws, over manifest.Manifest and manifest.Attribution:

  L1  X is None      -> X's key is ABSENT from the canonical dict and bytes.
  L2  X is not None  -> X's key is PRESENT, carries the value, and is the
                        ONLY delta against the all-None baseline.
  L3  proof_assumptions is the single documented exception: ABSENT even
      when set. It travels as an UNSIGNED sibling beside the signature
      block (conformance.py: "tamperable and therefore advisory only";
      cli_conformance.py: bounds are never read from it). The exemption is
      LOAD-BEARING, not cosmetic: parse_manifest_json reads the sibling
      back into the dataclass, so emitting it into the canonical body would
      change the recomputed bytes and invalidate every signature over a
      manifest carrying one. L3 asserts that round-trip still verifies.

Sentinels are keyed by RESOLVED FIELD TYPE, never by field name. An optional
field whose type has no registered sentinel FAILS with an explicit
instruction, so an unrecognised type cannot slip through as a silent pass.

Type resolution goes through typing.get_type_hints, not Field.type, so the
result is identical whether or not the module carries
'from __future__ import annotations'.

EVIDENCES that the canonical serialization obeys its declared law.
PROVES nothing about the correctness of any manifest.
"""
from __future__ import annotations

import dataclasses
import typing

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from manifest import (
    Attribution,
    Manifest,
    manifest_json,
    parse_manifest_json,
    sign_manifest,
    verify_manifest_signature,
)

_MARKER = "__s262_drop_when_none_completeness_v1__"

_SHA: str = "d" * 64

_EXEMPT: frozenset[str] = frozenset({"proof_assumptions"})

_COUPLED: dict[str, dict[str, object]] = {
    "source_kind": {
        "source_kind": "gap-witness",
        "gap_witness_sha256": _SHA,
    },
    "gap_witness_sha256": {
        "source_kind": "gap-witness",
        "gap_witness_sha256": _SHA,
    },
}

_ATTRIBUTION_SENTINEL = Attribution(
    actor_identity="operator@example.invalid",
    role="release-operator",
    key_id="s262-key",
    attribution_kind="asserted",
)


def _sentinel_for(name: str, resolved: object) -> object:
    if resolved is str:
        return "gap-witness" if name == "source_kind" else _SHA
    if resolved is int:
        return 7
    if resolved is dict:
        return {"gated_actions": ["s262"]}
    if resolved is Attribution:
        return _ATTRIBUTION_SENTINEL
    raise LookupError(
        "no sentinel registered for optional field " + repr(name)
        + " of resolved type " + repr(resolved)
        + "; register one in _sentinel_for so the drop-when-None law is "
        "enforced for it (this failure is the backstop working, not a bug "
        "in the test)"
    )


def _optional_fields(cls: type) -> dict[str, object]:
    """name -> resolved non-None type, for every Optional-with-None-default."""
    hints = typing.get_type_hints(cls)
    out: dict[str, object] = {}
    for f in dataclasses.fields(cls):
        if f.default is not None:
            continue
        args = typing.get_args(hints[f.name])
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) != 1:
            raise LookupError(
                "optional field " + repr(f.name) + " has an unsupported "
                "annotation shape " + repr(hints[f.name])
                + "; extend _optional_fields before shipping it"
            )
        out[f.name] = non_none[0]
    return out


_MANIFEST_OPTIONAL: dict[str, object] = _optional_fields(Manifest)
_ATTRIBUTION_OPTIONAL: dict[str, object] = _optional_fields(Attribution)

_MANIFEST_LAW2: list[str] = sorted(set(_MANIFEST_OPTIONAL) - _EXEMPT)


def _base_manifest(**overrides: object) -> Manifest:
    fields: dict = dict(
        schema_version="1",
        nous_version="5.78.0",
        smt_emit_version="1",
        source_sha256="a" * 64,
        pricing_sha256="b" * 64,
        smt_spec_sha256="c" * 64,
        world_name="s262_world",
        cost_cap_usd="1.00",
        max_ticks=10,
        verdict="proven",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=5,
        timestamp_utc="2026-07-25T00:00:00+00:00",
    )
    fields.update(overrides)
    return Manifest(**fields)


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b"\x2a" * 32)


def _set_for(name: str) -> dict[str, object]:
    if name in _COUPLED:
        return dict(_COUPLED[name])
    return {name: _sentinel_for(name, _MANIFEST_OPTIONAL[name])}


def test_every_manifest_optional_field_has_a_sentinel() -> None:
    """The backstop itself: an unregistered type must not pass silently."""
    assert _MANIFEST_OPTIONAL, "no optional fields discovered on Manifest"
    for name, resolved in _MANIFEST_OPTIONAL.items():
        _sentinel_for(name, resolved)


def test_every_attribution_optional_field_has_a_sentinel() -> None:
    assert _ATTRIBUTION_OPTIONAL, "no optional fields discovered on Attribution"
    for name, resolved in _ATTRIBUTION_OPTIONAL.items():
        assert resolved is str, (
            "Attribution optional field " + repr(name) + " is no longer str; "
            "extend this leg"
        )


def test_exempt_set_is_exactly_proof_assumptions() -> None:
    """A SECOND field excused from the canonical body must be a deliberate,
    reviewed act. If one appears, this fails until the exemption is argued
    in _EXEMPT and its own load-bearing test is written."""
    assert _EXEMPT == frozenset({"proof_assumptions"})
    assert _EXEMPT <= set(_MANIFEST_OPTIONAL)


@pytest.mark.parametrize("name", sorted(_MANIFEST_OPTIONAL))
def test_l1_none_field_key_absent(name: str) -> None:
    base = _base_manifest()
    assert getattr(base, name) is None
    assert name not in base.canonical_dict()
    assert name.encode("ascii") not in base.canonical_bytes()


@pytest.mark.parametrize("name", _MANIFEST_LAW2)
def test_l2_set_field_key_present_and_is_the_only_delta(name: str) -> None:
    overrides = _set_for(name)
    base = _base_manifest()
    m = _base_manifest(**overrides)
    base_keys = set(base.canonical_dict())
    m_keys = set(m.canonical_dict())
    assert m_keys - base_keys == set(overrides), (
        "setting " + repr(name) + " changed the canonical key set by "
        + repr(sorted(m_keys - base_keys)) + ", expected "
        + repr(sorted(overrides))
    )
    assert base_keys - m_keys == set(), (
        "setting " + repr(name) + " REMOVED canonical keys "
        + repr(sorted(base_keys - m_keys))
    )
    for key, value in overrides.items():
        expected = (
            value.canonical_dict()
            if isinstance(value, Attribution)
            else value
        )
        assert m.canonical_dict()[key] == expected


@pytest.mark.parametrize("name", _MANIFEST_LAW2)
def test_l2_set_field_is_covered_by_the_signature(name: str) -> None:
    priv = _priv()
    m = _base_manifest(**_set_for(name))
    sig = sign_manifest(m, priv)
    assert verify_manifest_signature(m, sig, priv.public_key())
    assert not verify_manifest_signature(
        _base_manifest(), sig, priv.public_key()
    ), (
        "a manifest WITHOUT " + repr(name) + " verified against a signature "
        "made WITH it; the field is outside the signed body"
    )


@pytest.mark.parametrize("name", sorted(_ATTRIBUTION_OPTIONAL))
def test_l1_l2_attribution_optional_field(name: str) -> None:
    base = _ATTRIBUTION_SENTINEL
    assert getattr(base, name) is None
    assert name not in base.canonical_dict()
    filled = dataclasses.replace(base, **{name: _SHA})
    d = filled.canonical_dict()
    assert d[name] == _SHA
    assert set(d) - set(base.canonical_dict()) == {name}


def test_l3_proof_assumptions_absent_from_canonical_body_when_set() -> None:
    """The documented exception, asserted rather than assumed."""
    m = _base_manifest(proof_assumptions={"gated_actions": ["s262"]})
    assert m.proof_assumptions is not None
    assert "proof_assumptions" not in m.canonical_dict()
    assert b"proof_assumptions" not in m.canonical_bytes()


def test_l3_proof_assumptions_does_not_perturb_canonical_bytes() -> None:
    a = _base_manifest()
    b = _base_manifest(proof_assumptions={"gated_actions": ["s262"]})
    assert a.canonical_bytes() == b.canonical_bytes()


def test_l3_exemption_is_load_bearing_across_the_sibling_round_trip() -> None:
    """Why the exemption cannot be 'fixed': the sibling is parsed back INTO
    the dataclass. If proof_assumptions entered the canonical body, the
    reconstructed manifest would recompute different bytes and the operator
    signature over the original would fail. This asserts it does not."""
    priv = _priv()
    m = _base_manifest(proof_assumptions={"gated_actions": ["s262"]})
    sig = sign_manifest(m, priv)
    doc = manifest_json(
        m, sig, priv.public_key(), include_proof_assumptions=True
    )
    assert '"proof_assumptions"' in doc, (
        "opt-in sibling emission did not fire; this test no longer exercises "
        "the round-trip it claims to"
    )
    parsed, parsed_sig, parsed_pub = parse_manifest_json(doc)
    assert parsed.proof_assumptions == m.proof_assumptions
    assert parsed.canonical_bytes() == m.canonical_bytes()
    assert verify_manifest_signature(parsed, parsed_sig, parsed_pub)


def test_l3_sibling_is_unsigned_and_tamperable() -> None:
    """Stating the trust hole in an executable form: mutating the sibling
    leaves the signature valid. This is the ADVISORY status the conformance
    layer already documents, pinned so it cannot be silently upgraded to a
    signed field without this test failing."""
    priv = _priv()
    m = _base_manifest(proof_assumptions={"gated_actions": ["original"]})
    sig = sign_manifest(m, priv)
    doc = manifest_json(
        m, sig, priv.public_key(), include_proof_assumptions=True
    ).replace('"original"', '"tampered"')
    parsed, parsed_sig, parsed_pub = parse_manifest_json(doc)
    assert parsed.proof_assumptions == {"gated_actions": ["tampered"]}
    assert verify_manifest_signature(parsed, parsed_sig, parsed_pub), (
        "the sibling became signature-covered; if that is intended, "
        "proof_assumptions must leave _EXEMPT and enter canonical_dict"
    )


def test_marker_present() -> None:
    assert _MARKER == "__s262_drop_when_none_completeness_v1__"
