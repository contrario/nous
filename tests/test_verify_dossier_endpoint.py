"""Tests for POST /v1/verify-dossier (S81 #1).

Public surface: no API key required. Endpoint is the convenience
wrapper behind nous-lang.org/verify and the IDE Rekor badge. Trust
path remains offline verification with verify_offline.py; this
endpoint exists for structured PASS/FAIL display in the browser.

Coverage:
  - Public access (no API key, no 401).
  - Pydantic V2 strict mode (missing field 422, extra field 422).
  - Parse-failure path (invalid JSON, missing signature block)
    returns HTTP 200 with structured signature_ok=False and
    errors[] populated.
  - Real Ed25519 signing of a synthetic Manifest verifies
    signature_ok=True.
  - Tampered signature bytes -> signature_ok=False.
  - Tampered manifest field (post-sign) -> signature_ok=False.
  - Real manifest + fixture anchor (S80 captured) -> signature_ok
    True, rekor_set_ok=True (Rekor SET valid), rekor_inclusion_ok
    False (leaf hash does not match the new manifest canonical
    bytes). Integration test for the anchor handling code path.

# __session81_test_verify_dossier_v1__
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from fastapi.testclient import TestClient

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

REKOR_FIXTURE_DIR = _TESTS_DIR / "rekor_fixtures"


@pytest.fixture
def client() -> TestClient:
    from nous_api_server import app
    return TestClient(app)


def _build_signed_dossier_text(
    field_overrides: dict[str, Any] | None = None,
    flip_signature_first_byte: bool = False,
    extra_transparency_log: dict | None = None,
) -> str:
    from manifest import Manifest, manifest_json
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "nous_version": "5.4.0",
        "smt_emit_version": "1.0",
        "source_sha256": "a" * 64,
        "pricing_sha256": "b" * 64,
        "smt_spec_sha256": "c" * 64,
        "world_name": "S81VerifyTestWorld",
        "cost_cap_usd": "1.00",
        "max_ticks": 100,
        "verdict": "VERIFIED",
        "solver_name": "z3",
        "solver_version": "4.16.0",
        "elapsed_ms": 1,
        "timestamp_utc": "2026-05-17T00:00:00Z",
    }
    if field_overrides:
        base.update(field_overrides)
    m = Manifest(**base)
    sk = Ed25519PrivateKey.generate()
    sig = sk.sign(m.canonical_bytes())
    if flip_signature_first_byte:
        sig = bytes([sig[0] ^ 0xFF]) + sig[1:]
    pub = sk.public_key()
    text = manifest_json(m, sig, pub)
    if extra_transparency_log is not None:
        doc = json.loads(text)
        doc["transparency_log"] = extra_transparency_log
        text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    return text


def test_verify_dossier_endpoint_is_public_no_api_key_required(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": text},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signature_ok"] is True


def test_verify_dossier_endpoint_rejects_missing_field_422(
    client: TestClient,
) -> None:
    resp = client.post("/v1/verify-dossier", json={})
    assert resp.status_code == 422


def test_verify_dossier_endpoint_rejects_extra_field_422(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": text, "sneaky_extra": "value"},
    )
    assert resp.status_code == 422


def test_verify_dossier_endpoint_handles_invalid_json_returns_structured(
    client: TestClient,
) -> None:
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": "this is not json at all"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is False
    assert body["rekor_inclusion_ok"] is None
    assert body["rekor_set_ok"] is None
    assert body["rekor_log_index"] is None
    assert body["rekor_integrated_at"] is None
    assert body["errors"], "errors list must be populated on parse failure"
    assert any("parse_error" in e for e in body["errors"])
    assert len(body["manifest_sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in body["manifest_sha256"])


def test_verify_dossier_endpoint_handles_missing_signature_block(
    client: TestClient,
) -> None:
    payload = json.dumps(
        {"schema_version": "1.0", "nous_version": "5.4.0"}
    )
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": payload},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is False
    assert body["errors"]


def test_verify_dossier_endpoint_verifies_valid_unanchored_dossier(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": text},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is True
    assert body["rekor_inclusion_ok"] is None
    assert body["rekor_set_ok"] is None
    assert body["rekor_log_index"] is None
    assert body["rekor_integrated_at"] is None
    assert isinstance(body["public_key_b64"], str)
    assert len(body["public_key_b64"]) > 0
    assert len(body["manifest_sha256"]) == 64
    assert body["errors"] == []


def test_verify_dossier_endpoint_detects_tampered_signature_bytes(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text(flip_signature_first_byte=True)
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": text},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is False
    assert "ed25519_signature_invalid" in body["errors"]


def test_verify_dossier_endpoint_detects_tampered_manifest_field(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    doc = json.loads(text)
    doc["world_name"] = "TamperedAfterSigning"
    tampered = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": tampered},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is False


def test_verify_dossier_endpoint_real_manifest_plus_fixture_anchor(
    client: TestClient,
) -> None:
    """Real Ed25519 signing on a synthetic Manifest, combined with a
    real Rekor anchor captured in S80 over UNRELATED bytes.

    Expected outcome:
        signature_ok = True         (manifest signed correctly)
        rekor_set_ok = True         (SET signature valid, pubkey in
                                     allowlist; SET is over the
                                     anchor metadata, not the
                                     manifest)
        rekor_inclusion_ok = False  (leaf body sha256 does NOT match
                                     the new manifest's canonical
                                     bytes)
        rekor_log_index, rekor_integrated_at populated.

    Full-pass anchored test requires a Rekor submission over a real
    Manifest (captured only by live --anchor rekor invocations); the
    v5.4.0 blog-post live demo provides that end-to-end evidence.
    """
    anchor_block = json.loads(
        (REKOR_FIXTURE_DIR / "valid_anchor.json").read_text(
            encoding="utf-8"
        )
    )
    text = _build_signed_dossier_text(
        extra_transparency_log=anchor_block
    )
    resp = client.post(
        "/v1/verify-dossier",
        json={"manifest_json": text},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["signature_ok"] is True
    assert body["rekor_set_ok"] is True, body
    assert body["rekor_inclusion_ok"] is False, body
    assert body["rekor_log_index"] == anchor_block["log_index"]
    assert isinstance(body["rekor_integrated_at"], str)
    assert body["rekor_integrated_at"].endswith("Z")
