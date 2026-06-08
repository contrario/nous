"""S119 U2 -- tests for resolve_prior_digest (re-binding admission control).

These exercise the EXTRACTED, solver-free security gates in isolation:
predecessor signature validation and no-op refusal. No SMT pipeline is stood
up. They use the real manifest.py (frozen Manifest, real Ed25519 sign/parse).
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from cli_verify import SupersedesError, resolve_prior_digest
from manifest import (
    Manifest,
    manifest_json,
    sign_manifest,
)


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)


def _manifest(**overrides: object) -> Manifest:
    fields: dict = dict(
        schema_version="1",
        nous_version="5.28.0",
        smt_emit_version="1",
        source_sha256="a" * 64,
        pricing_sha256="b" * 64,
        smt_spec_sha256="c" * 64,
        world_name="w",
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


def _write_signed(m: Manifest, path: Path) -> None:
    priv = _priv()
    sig = sign_manifest(m, priv)
    path.write_text(manifest_json(m, sig, priv.public_key()), encoding="utf-8")


def test_missing_predecessor_raises(tmp_path: Path) -> None:
    new = _manifest(source_sha256="d" * 64)
    with pytest.raises(SupersedesError) as ei:
        resolve_prior_digest(new, str(tmp_path / "nope.json"))
    assert "not found" in str(ei.value)


def test_unparseable_predecessor_raises(tmp_path: Path) -> None:
    bad = tmp_path / "garbage.json"
    bad.write_text("not json {{{", encoding="utf-8")
    new = _manifest(source_sha256="d" * 64)
    with pytest.raises(SupersedesError) as ei:
        resolve_prior_digest(new, str(bad))
    assert "cannot parse" in str(ei.value)


def test_invalid_signature_raises(tmp_path: Path) -> None:
    prior = _manifest(source_sha256="a" * 64)
    p = tmp_path / "prior.json"
    _write_signed(prior, p)
    # Corrupt the signature.
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["signature"]["signature_b64"] = base64.b64encode(b"\x00" * 64).decode(
        "ascii"
    )
    p.write_text(json.dumps(doc), encoding="utf-8")
    new = _manifest(source_sha256="d" * 64)
    with pytest.raises(SupersedesError) as ei:
        resolve_prior_digest(new, str(p))
    assert "does NOT verify" in str(ei.value)


def test_no_op_rebinding_raises(tmp_path: Path) -> None:
    # Predecessor identical in all sha-bearing fields to the new build.
    prior = _manifest()
    p = tmp_path / "noop.json"
    _write_signed(prior, p)
    new = _manifest()  # same sha-bearing fields
    with pytest.raises(SupersedesError) as ei:
        resolve_prior_digest(new, str(p))
    assert "no-op re-binding" in str(ei.value)


def test_valid_rebinding_returns_predecessor_digest(tmp_path: Path) -> None:
    prior = _manifest(source_sha256="a" * 64)
    p = tmp_path / "prior.json"
    _write_signed(prior, p)
    new = _manifest(source_sha256="d" * 64)  # source moved
    digest = resolve_prior_digest(new, str(p))
    assert len(digest) == 64
    assert digest == hashlib.sha256(prior.canonical_bytes()).hexdigest()


def test_cost_cap_move_alone_is_sufficient(tmp_path: Path) -> None:
    prior = _manifest(cost_cap_usd="1.00")
    p = tmp_path / "prior.json"
    _write_signed(prior, p)
    new = _manifest(cost_cap_usd="2.00")  # only the cap moved
    digest = resolve_prior_digest(new, str(p))
    assert digest == hashlib.sha256(prior.canonical_bytes()).hexdigest()


def test_max_ticks_move_alone_is_sufficient(tmp_path: Path) -> None:
    prior = _manifest(max_ticks=10)
    p = tmp_path / "prior.json"
    _write_signed(prior, p)
    new = _manifest(max_ticks=20)  # only the tick bound moved
    digest = resolve_prior_digest(new, str(p))
    assert digest == hashlib.sha256(prior.canonical_bytes()).hexdigest()


def test_digest_is_deterministic(tmp_path: Path) -> None:
    prior = _manifest(source_sha256="a" * 64)
    p = tmp_path / "prior.json"
    _write_signed(prior, p)
    new = _manifest(source_sha256="d" * 64)
    d1 = resolve_prior_digest(new, str(p))
    d2 = resolve_prior_digest(new, str(p))
    assert d1 == d2
