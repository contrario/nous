"""XF5 XD-1 (seat 427): every signed Manifest field survives the parse.

Each optional field of Manifest, set alone, is signed once under a fresh
Ed25519 key, rendered by manifest_json, parsed by each of the three parse
functions, and checked by verify_manifest_signature. A field that
canonical_dict signs but a parse function does not read fails here: the
parsed Manifest's canonical bytes then differ from the signed ones
(FG-S427-A, safety_margin_pct).

No artifact is altered or re-signed: every manifest is built and signed
once, in memory, under its own fresh key.

# __xf5_xd1_roundtrip_test_v1__
"""
from __future__ import annotations

import dataclasses

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import manifest as M

_H = "ab" * 32
_BASE = dict(
    schema_version="1", nous_version="8.0.0", smt_emit_version="1",
    source_sha256=_H, pricing_sha256=_H, smt_spec_sha256=_H,
    world_name="W", cost_cap_usd="1.00", max_ticks=1,
    verdict="proven", solver_name="z3", solver_version="4",
    elapsed_ms=1, timestamp_utc="2026-11-01T00:00:00Z",
)
_VALUES = {
    "counterexample_total_usd": "1.50",
    "safety_margin_pct": 10,
    "chain_coverage_mode": "full",
    "attribution": M.Attribution(
        actor_identity="a", role="r", key_id="k",
        attribution_kind="asserted",
    ),
}
_PAIRED = {"source_kind": "gap-witness", "gap_witness_sha256": _H}
_UNSIGNED = ("proof_assumptions",)


def _optional_fields():
    return [f.name for f in dataclasses.fields(M.Manifest)
            if f.default is None and f.name not in _UNSIGNED]


def _cases():
    out = [("control", {})]
    for name in _optional_fields():
        if name in _PAIRED:
            continue
        out.append((name, {name: _VALUES.get(name, _H)}))
    out.append(("source_kind+gap_witness_sha256", dict(_PAIRED)))
    return out


_CASES = _cases()
_PATHS = {
    "parse_manifest_json":
        lambda t: M.parse_manifest_json(t)[:3],
    "parse_manifest_json_with_anchor":
        lambda t: M.parse_manifest_json_with_anchor(t)[:3],
    "parse_manifest_json_with_anchor_v2":
        lambda t: M.parse_manifest_json_with_anchor_v2(t)[:3],
}


@pytest.mark.parametrize("path", sorted(_PATHS))
@pytest.mark.parametrize("name,extra", _CASES, ids=[c[0] for c in _CASES])
def test_signed_field_survives_parse(name, extra, path):
    m = M.Manifest(**_BASE, **extra)
    key = Ed25519PrivateKey.generate()
    text = M.manifest_json(m, M.sign_manifest(m, key), key.public_key())
    parsed, sig, pub = _PATHS[path](text)
    for field, value in extra.items():
        assert getattr(parsed, field) == value, (name, path, field)
    assert M.verify_manifest_signature(parsed, sig, pub), (name, path)


def test_every_signed_optional_field_has_a_case():
    covered = set()
    for _name, extra in _CASES:
        covered |= set(extra)
    assert covered == set(_optional_fields())
    base_keys = set(M.Manifest(**_BASE).canonical_dict())
    emitted = set()
    for _name, extra in _CASES:
        emitted |= set(M.Manifest(**_BASE, **extra).canonical_dict())
    assert emitted - base_keys == covered
