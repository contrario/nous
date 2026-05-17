"""Tests for POST /v1/verify-dossier V2 surface (S82 #1b).

The V2 path is gated by request.policy: when present, the endpoint
returns a structured response with verdict + checks + evidence +
human_readable. When absent, the legacy V1 shape is returned
(tested in test_verify_dossier_endpoint.py, unchanged by this patch).

# __session82_test_verify_dossier_v2_v1__
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
        "world_name": "S82V2TestWorld",
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


# 1
def test_v2_request_accepts_policy_field(client: TestClient) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    assert resp.status_code == 200, resp.text


# 2
def test_v2_response_has_spec_version(client: TestClient) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    assert body["spec_version"] == "verify-dossier/v2"


# 3
def test_v2_unanchored_with_require_anchor_returns_reject(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": True},
        },
    )
    body = resp.json()
    assert body["verdict"] == "REJECT"
    assert body["trust_level"] == "ed25519_only"
    assert body["checks"]["manifest_signature_ed25519"]["ok"] is True
    assert body["checks"]["transparency_log_present"]["ok"] is False
    assert body["checks"]["rekor_signed_entry_timestamp"]["ok"] == (
        "skipped_unanchored"
    )
    assert "anchor" in body["human_readable"]["verdict_summary"].lower()


# 4
def test_v2_unanchored_with_allow_unanchored_returns_accept(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    assert body["verdict"] == "ACCEPT"
    assert body["trust_level"] == "ed25519_only"
    assert body["checks"]["manifest_signature_ed25519"]["ok"] is True
    assert "no public anchor" in (
        body["human_readable"]["verdict_summary"].lower()
        or body["human_readable"]["trust_explanation"].lower()
    )


# 5
def test_v2_tampered_signature_returns_reject_with_check_detail(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text(flip_signature_first_byte=True)
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    assert body["verdict"] == "REJECT"
    assert body["trust_level"] == "none"
    sig_check = body["checks"]["manifest_signature_ed25519"]
    assert sig_check["ok"] is False
    assert "ed25519_signature_invalid" in sig_check["errors"]


# 6
def test_v2_skipped_unanchored_marker_in_all_rekor_checks(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    for key in (
        "rekor_public_key_in_allowlist",
        "rekor_signed_entry_timestamp",
        "rekor_leaf_inclusion",
    ):
        assert body["checks"][key]["ok"] == "skipped_unanchored", (
            key, body["checks"][key]
        )


# 7
def test_v2_anchor_age_check_skipped_when_policy_omits_limit(
    client: TestClient,
) -> None:
    """When the anchor is present but policy.max_anchor_age_seconds is
    None, the rekor_anchor_age check is 'skipped_no_policy'."""
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
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    assert body["checks"]["rekor_anchor_age"]["ok"] == "skipped_no_policy"


# 8
def test_v2_anchor_age_check_runs_when_policy_sets_limit(
    client: TestClient,
) -> None:
    """When max_anchor_age_seconds is set, the age check runs.
    The S80 fixture anchor is some hours old at most relative to now,
    so a very small limit fails and a generous one passes."""
    anchor_block = json.loads(
        (REKOR_FIXTURE_DIR / "valid_anchor.json").read_text(
            encoding="utf-8"
        )
    )
    text = _build_signed_dossier_text(
        extra_transparency_log=anchor_block
    )
    resp_tight = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {
                "require_anchor": False,
                "max_anchor_age_seconds": 1,
            },
        },
    )
    age_check_tight = resp_tight.json()["checks"]["rekor_anchor_age"]
    assert age_check_tight["ok"] is False
    assert any(
        "anchor_too_old" in e for e in age_check_tight["errors"]
    )

    resp_loose = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {
                "require_anchor": False,
                "max_anchor_age_seconds": 10 ** 12,
            },
        },
    )
    age_check_loose = resp_loose.json()["checks"]["rekor_anchor_age"]
    assert age_check_loose["ok"] is True


# 9
def test_v2_anchored_response_includes_full_evidence(
    client: TestClient,
) -> None:
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
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    ev = body["evidence"]
    assert ev["rekor_log_index"] == anchor_block["log_index"]
    assert isinstance(ev["rekor_integrated_at"], str)
    assert ev["rekor_integrated_at"].endswith("Z")
    assert isinstance(ev["rekor_log_id"], str)
    assert isinstance(ev["rekor_anchor_age_seconds"], int)
    assert ev["rekor_anchor_age_seconds"] >= 0
    assert isinstance(ev["public_key_b64"], str)
    assert len(ev["manifest_sha256"]) == 64
    assert len(ev["manifest_canonical_bytes_sha256"]) == 64


# 10
def test_v2_human_readable_present_for_all_verdicts(
    client: TestClient,
) -> None:
    text = _build_signed_dossier_text()
    for policy in [
        {"require_anchor": False},
        {"require_anchor": True},
    ]:
        resp = client.post(
            "/v1/verify-dossier",
            json={"manifest_json": text, "policy": policy},
        )
        hr = resp.json()["human_readable"]
        assert isinstance(hr["verdict_summary"], str)
        assert len(hr["verdict_summary"]) > 0
        assert isinstance(hr["trust_explanation"], str)
        assert len(hr["trust_explanation"]) > 0
        assert isinstance(hr["next_steps"], list)


# 11
def test_v2_parse_failure_returns_reject_with_well_formed_check(
    client: TestClient,
) -> None:
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": "not a valid manifest",
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    assert body["verdict"] == "REJECT"
    assert body["trust_level"] == "none"
    wf = body["checks"]["manifest_well_formed"]
    assert wf["ok"] is False
    assert any("parse_error" in e for e in wf["errors"])


# 12
def test_v2_response_pydantic_round_trips(client: TestClient) -> None:
    """Sanity: V2 response body parses back through the same Pydantic
    model that produced it (strict + extra=forbid)."""
    from nous_api_server import VerifyDossierEndpointResponseV2
    text = _build_signed_dossier_text()
    resp = client.post(
        "/v1/verify-dossier",
        json={
            "manifest_json": text,
            "policy": {"require_anchor": False},
        },
    )
    body = resp.json()
    parsed = VerifyDossierEndpointResponseV2(**body)
    assert parsed.spec_version == "verify-dossier/v2"
    assert parsed.verdict in ("ACCEPT", "REJECT")
    assert parsed.trust_level in (
        "rekor_anchored", "ed25519_only", "none"
    )
