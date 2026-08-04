"""S297 tests for the GLM ceremony: the published manifest and the
version-transform step of scripts/sign_glm_manifest.py.

scripts/ is not a package, so the ceremony tool is loaded by file path.
These tests are hermetic: no network, no private key, no served-path read.
The published manifest is verified with the pinned PUBLIC key only, so the
suite stays CI-portable.

__s297_glm_ceremony_tests_v1__
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

import glm_manifest as gm

_REPO = Path(__file__).resolve().parents[1]
_SIGNER = _REPO / "scripts" / "sign_glm_manifest.py"
_MANIFEST = _REPO / "website" / ".well-known" / "governance-layer-manifest.json"
_SHA_SIDECAR = _MANIFEST.with_name(_MANIFEST.name + ".sha256")


def _load_signer():
    spec = importlib.util.spec_from_file_location("_s297_signer", _SIGNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_manifest() -> dict:
    """A minimal but structurally complete GLM source document."""
    return {
        "schema_version": "1.1",
        "manifest_version": "1.0",
        "owner": {"name": "NOUS", "version": "1.0.0"},
        "valid_from": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00Z",
        "supersedes": "https://example.invalid/old.json",
        "supersedes_digest": "0" * 64,
        "operational_scope": {
            "does_not": [
                "Enforce, authorize, halt, or intervene in execution",
                "Attest the behavior of any specific execution",
            ]
        },
        "manifest_digest": {
            "type": "sha256",
            "value": "ab" * 32,
            "canonicalization_method": "superseded by the transform",
        },
        "manifest_signature": {
            "type": "ed25519",
            "value": "old-signature",
            "public_key": "old-public-key",
        },
    }


# --- the transform step -------------------------------------------------


def test_transform_chains_supersedes_digest_from_the_source_digest() -> None:
    signer = _load_signer()
    out = signer._transform_source(
        _source_manifest(),
        new_version="2.0.0",
        valid_from="2026-08-04",
        supersedes_url="https://example.invalid/new.json",
    )
    assert out["supersedes_digest"] == "ab" * 32
    assert out["supersedes"] == "https://example.invalid/new.json"
    assert out["owner"]["version"] == "2.0.0"
    assert out["valid_from"] == "2026-08-04"
    assert out["generated_at"] == "2026-08-04T00:00:00Z"


def test_transform_clears_the_signature_for_reseal() -> None:
    signer = _load_signer()
    out = signer._transform_source(
        _source_manifest(),
        new_version="2.0.0",
        valid_from="2026-08-04",
        supersedes_url="https://example.invalid/new.json",
    )
    assert out["manifest_signature"]["value"] is None
    assert out["manifest_signature"]["public_key"] is None
    assert out["manifest_signature"]["type"] == "ed25519"


def test_transform_does_not_touch_operational_scope() -> None:
    """The ceremony reseals; it never edits claims. Any correction to
    operational_scope.does_not must happen in the source document, under its
    own gate, before build runs."""
    signer = _load_signer()
    source = _source_manifest()
    before = copy.deepcopy(source["operational_scope"])
    out = signer._transform_source(
        source,
        new_version="2.0.0",
        valid_from="2026-08-04",
        supersedes_url="https://example.invalid/new.json",
    )
    assert out["operational_scope"] == before


def test_transform_is_idempotent() -> None:
    """It mutates in place, but the predecessor digest it reads is never one
    of the fields it writes, so a second pass yields the same document."""
    signer = _load_signer()
    kwargs = {
        "new_version": "2.0.0",
        "valid_from": "2026-08-04",
        "supersedes_url": "https://example.invalid/new.json",
    }
    once = copy.deepcopy(signer._transform_source(_source_manifest(), **kwargs))
    twice = signer._transform_source(
        signer._transform_source(_source_manifest(), **kwargs), **kwargs
    )
    assert once == twice


def test_transform_refuses_a_source_without_a_digest_block() -> None:
    signer = _load_signer()
    source = _source_manifest()
    del source["manifest_digest"]
    with pytest.raises(signer.CeremonyError):
        signer._transform_source(
            source,
            new_version="2.0.0",
            valid_from="2026-08-04",
            supersedes_url="https://example.invalid/new.json",
        )


# --- the published artifact ---------------------------------------------


def test_published_glm_manifest_is_internally_consistent() -> None:
    """The tracked manifest verifies against the pinned public key. This is a
    lock on the published bytes: a hand edit turns the suite red instead of
    drifting silently. It does not pin the digest or the version, so a
    correctly resealed successor still passes."""
    served = _MANIFEST.read_text(encoding="utf-8")
    detail = gm.verify_glm_manifest(served)
    assert detail.digest_ok is True, detail.errors
    assert detail.signature_present is True, detail.errors
    assert detail.signer_pinned is True, detail.errors
    assert detail.signature_ok is True, detail.errors
    assert detail.ok is True, detail.errors
    assert detail.computed_digest == detail.declared_digest
    assert isinstance(detail.owner_version, str) and detail.owner_version


def test_published_glm_sha256_sidecar_matches_the_manifest() -> None:
    digest = hashlib.sha256(_MANIFEST.read_bytes()).hexdigest()
    declared = _SHA_SIDECAR.read_text(encoding="utf-8").split()[0]
    assert declared == digest


def test_published_glm_manifest_declares_a_supersedes_chain() -> None:
    doc = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    predecessor = doc.get("supersedes_digest")
    assert isinstance(predecessor, str)
    assert len(predecessor) == 64
    assert predecessor == predecessor.lower()
    int(predecessor, 16)
    assert isinstance(doc.get("supersedes"), str) and doc["supersedes"]
