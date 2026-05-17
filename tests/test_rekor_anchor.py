"""S79 #6b: rekor_anchor module + Path beta dual-signing test suite.

Tests the public API of rekor_anchor (RekorAnchor model, RekorUnavailable /
RekorRejected exception classes, anchor_manifest_to_rekor failure modes,
verify_rekor_anchor_offline behavior with the live captured fixtures from
S79 #6a) plus the SkillExportEndpointRequest Pydantic V2 anchor field
introduced by S79 #5b.

Fixtures in tests/rekor_fixtures/ were captured by S79 #6a via ONE live
submission to https://rekor.sigstore.dev. Permanent public log entry at
log_index 1554376230, integratedTime 1778962105 (2026-05-16T20:08:25Z).

# __nous_aetherproof_rekor_tests_v1__
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from rekor_anchor import (
    KNOWN_REKOR_PUBLIC_KEYS,
    RekorAnchor,
    RekorRejected,
    RekorUnavailable,
    _build_hashedrekord_body,
    _raw_ed25519_b64_to_pem,
    anchor_manifest_to_rekor,
    verify_rekor_anchor_offline,
)

FIXTURE_DIR = _TESTS_DIR / "rekor_fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _valid_anchor() -> RekorAnchor:
    return RekorAnchor(**_load_fixture("valid_anchor.json"))


def _valid_inputs() -> dict:
    inp = _load_fixture("valid_inputs.json")
    return {
        "canonical_bytes": base64.b64decode(inp["manifest_canonical_bytes_b64"]),
        "signature_b64": inp["manifest_signature_b64"],
        "public_key_b64": inp["manifest_public_key_b64"],
    }


class TestRekorAnchorModel:

    def test_valid_fixture_constructs(self) -> None:
        anchor = _valid_anchor()
        assert anchor.provider == "sigstore-rekor"
        assert anchor.log_index >= 0
        assert anchor.integrated_time >= 0
        assert anchor.body_b64
        assert anchor.signed_entry_timestamp_b64
        assert "BEGIN PUBLIC KEY" in anchor.rekor_public_key_pem

    def test_missing_required_field_raises(self) -> None:
        d = _load_fixture("valid_anchor.json")
        del d["log_id"]
        with pytest.raises(ValidationError):
            RekorAnchor(**d)

    def test_extra_field_forbidden(self) -> None:
        d = _load_fixture("valid_anchor.json")
        d["sneaky_extra"] = "value"
        with pytest.raises(ValidationError):
            RekorAnchor(**d)

    def test_frozen_blocks_field_assignment(self) -> None:
        anchor = _valid_anchor()
        with pytest.raises(ValidationError):
            anchor.log_index = 999

    def test_negative_log_index_rejected(self) -> None:
        d = _load_fixture("valid_anchor.json")
        d["log_index"] = -1
        with pytest.raises(ValidationError):
            RekorAnchor(**d)

    def test_to_manifest_block_round_trips(self) -> None:
        anchor = _valid_anchor()
        block = anchor.to_manifest_block()
        restored = RekorAnchor.from_manifest_block(block)
        assert restored == anchor


class TestAnchorManifestToRekorFailureModes:

    @staticmethod
    def _make_pubkey_ok_client() -> Mock:
        client = Mock(spec=httpx.Client)
        pk_resp = Mock()
        pk_resp.status_code = 200
        pk_resp.text = KNOWN_REKOR_PUBLIC_KEYS[0]
        client.get.return_value = pk_resp
        return client

    def test_pubkey_fetch_request_error_raises_unavailable(self) -> None:
        client = Mock(spec=httpx.Client)
        client.get.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(RekorUnavailable):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )

    def test_pubkey_fetch_non_200_raises_rejected(self) -> None:
        client = Mock(spec=httpx.Client)
        resp = Mock()
        resp.status_code = 503
        resp.text = "service unavailable"
        client.get.return_value = resp
        with pytest.raises(RekorRejected):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )

    def test_pubkey_fetch_non_pem_raises_rejected(self) -> None:
        client = Mock(spec=httpx.Client)
        resp = Mock()
        resp.status_code = 200
        resp.text = "not a PEM blob"
        client.get.return_value = resp
        with pytest.raises(RekorRejected):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )

    def test_submit_request_error_raises_unavailable(self) -> None:
        client = self._make_pubkey_ok_client()
        client.post.side_effect = httpx.ReadTimeout("read timeout")
        with pytest.raises(RekorUnavailable):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )

    def test_submit_400_raises_rejected(self) -> None:
        client = self._make_pubkey_ok_client()
        post_resp = Mock()
        post_resp.status_code = 400
        post_resp.text = '{"code":400,"message":"bad request"}'
        client.post.return_value = post_resp
        with pytest.raises(RekorRejected, match="400"):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )

    def test_submit_non_json_raises_rejected(self) -> None:
        client = self._make_pubkey_ok_client()
        post_resp = Mock()
        post_resp.status_code = 201
        post_resp.text = "not json at all"
        post_resp.json = Mock(side_effect=json.JSONDecodeError("bad", "doc", 0))
        client.post.return_value = post_resp
        with pytest.raises(RekorRejected):
            anchor_manifest_to_rekor(
                manifest_canonical_bytes=b"x",
                manifest_signature_b64="",
                manifest_public_key_b64="",
                client=client,
            )


class TestVerifyRekorAnchorOffline:

    def test_valid_fixture_verifies_true(self) -> None:
        anchor = _valid_anchor()
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert result is True

    def test_tampered_set_fails(self) -> None:
        anchor = RekorAnchor(**_load_fixture("tampered_anchor.json"))
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert result is False

    def test_wrong_pubkey_fails(self) -> None:
        anchor = RekorAnchor(**_load_fixture("wrong_pubkey_anchor.json"))
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert result is False

    def test_wrong_canonical_bytes_fails(self) -> None:
        anchor = _valid_anchor()
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=b"different bytes entirely",
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert result is False

    def test_allowlist_excluding_anchor_pubkey_fails(self) -> None:
        anchor = _valid_anchor()
        inp = _valid_inputs()
        bogus_pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n"
            "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n"
            "-----END PUBLIC KEY-----\n"
        )
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
            known_rekor_public_keys=[bogus_pem],
        )
        assert result is False

    def test_explicit_allowlist_with_anchor_pubkey_succeeds(self) -> None:
        anchor_dict = _load_fixture("valid_anchor.json")
        anchor = RekorAnchor(**anchor_dict)
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
            known_rekor_public_keys=[anchor_dict["rekor_public_key_pem"]],
        )
        assert result is True

    def test_provider_mismatch_fails(self) -> None:
        d = _load_fixture("valid_anchor.json")
        d["provider"] = "fake-provider"
        anchor = RekorAnchor(**d)
        inp = _valid_inputs()
        result = verify_rekor_anchor_offline(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert result is False


class TestRawEd25519PemHelper:

    def test_helper_round_trips_real_key(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        sk = ed25519.Ed25519PrivateKey.generate()
        raw = sk.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        b64 = base64.b64encode(raw).decode("ascii")
        pem = _raw_ed25519_b64_to_pem(b64)
        loaded = serialization.load_pem_public_key(pem.encode("ascii"))
        assert isinstance(loaded, ed25519.Ed25519PublicKey)
        loaded_raw = loaded.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        assert loaded_raw == raw

    def test_helper_rejects_invalid_b64(self) -> None:
        with pytest.raises(Exception):
            _raw_ed25519_b64_to_pem("not-valid-base64-input!!!")

    def test_helper_rejects_short_key(self) -> None:
        b64 = base64.b64encode(b"\x00" * 16).decode("ascii")
        with pytest.raises(Exception):
            _raw_ed25519_b64_to_pem(b64)


class TestBuildHashedrekordBody:

    def test_body_shape_correct(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        sk = ec.generate_private_key(ec.SECP256R1())
        pem = sk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        body = _build_hashedrekord_body(
            payload_sha256_hex="0" * 64,
            submitter_signature_b64=base64.b64encode(b"fake-sig").decode("ascii"),
            submitter_public_key_pem=pem,
        )
        assert body["kind"] == "hashedrekord"
        assert body["apiVersion"] == "0.0.1"
        assert body["spec"]["data"]["hash"]["algorithm"] == "sha256"
        assert body["spec"]["data"]["hash"]["value"] == "0" * 64
        inner_pem = base64.b64decode(
            body["spec"]["signature"]["publicKey"]["content"]
        ).decode("ascii")
        assert inner_pem == pem
        loaded = serialization.load_pem_public_key(inner_pem.encode("ascii"))
        assert isinstance(loaded, ec.EllipticCurvePublicKey)


def _try_import_skill_export_request():
    try:
        from nous_api_server import SkillExportEndpointRequest
        return SkillExportEndpointRequest
    except Exception:
        return None


class TestSkillExportEndpointRequestAnchorField:

    def test_anchor_default_is_none(self) -> None:
        Model = _try_import_skill_export_request()
        if Model is None:
            pytest.skip("cannot import SkillExportEndpointRequest from nous_api_server")
        m = Model(source="x", description="y")
        assert m.anchor == "none"

    def test_anchor_rekor_accepted(self) -> None:
        Model = _try_import_skill_export_request()
        if Model is None:
            pytest.skip("cannot import SkillExportEndpointRequest from nous_api_server")
        m = Model(source="x", description="y", anchor="rekor")
        assert m.anchor == "rekor"

    def test_anchor_bogus_pattern_rejected(self) -> None:
        Model = _try_import_skill_export_request()
        if Model is None:
            pytest.skip("cannot import SkillExportEndpointRequest from nous_api_server")
        with pytest.raises(ValidationError):
            Model(source="x", description="y", anchor="bogus")

    def test_extra_field_with_anchor_still_forbidden(self) -> None:
        Model = _try_import_skill_export_request()
        if Model is None:
            pytest.skip("cannot import SkillExportEndpointRequest from nous_api_server")
        with pytest.raises(ValidationError):
            Model(source="x", description="y", anchor="rekor", extra_field="x")


class TestVerifyRekorAnchorOfflineDetail:
    """S81 #1: granular detail variant of verify_rekor_anchor_offline.

    # __session81_test_rekor_detail_v1__
    """

    def test_valid_fixture_returns_all_true(self) -> None:
        from rekor_anchor import verify_rekor_anchor_offline_detail
        anchor = _valid_anchor()
        inp = _valid_inputs()
        detail = verify_rekor_anchor_offline_detail(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert detail.pubkey_in_allowlist is True
        assert detail.set_signature_ok is True
        assert detail.inclusion_body_ok is True
        assert detail.errors == []

    def test_failure_fixture_yields_errors(self) -> None:
        from rekor_anchor import verify_rekor_anchor_offline_detail
        anchor = RekorAnchor(**_load_fixture("tampered_anchor.json"))
        inp = _valid_inputs()
        detail = verify_rekor_anchor_offline_detail(
            anchor=anchor,
            expected_manifest_canonical_bytes=inp["canonical_bytes"],
            expected_manifest_signature_b64=inp["signature_b64"],
            expected_manifest_public_key_b64=inp["public_key_b64"],
        )
        assert detail.errors, "tampered fixture must produce errors"
        assert not (
            detail.pubkey_in_allowlist
            and detail.set_signature_ok
            and detail.inclusion_body_ok
        )

    def test_legacy_bool_matches_and_of_detail_fields(self) -> None:
        """Regression backstop: verify_rekor_anchor_offline outcome
        equals AND of detail.{pubkey_in_allowlist, set_signature_ok,
        inclusion_body_ok} across ALL three S80 fixtures.
        """
        from rekor_anchor import (
            verify_rekor_anchor_offline,
            verify_rekor_anchor_offline_detail,
        )
        inp = _valid_inputs()
        for fname in (
            "valid_anchor.json",
            "tampered_anchor.json",
            "wrong_pubkey_anchor.json",
        ):
            anchor = RekorAnchor(**_load_fixture(fname))
            legacy = verify_rekor_anchor_offline(
                anchor=anchor,
                expected_manifest_canonical_bytes=inp[
                    "canonical_bytes"
                ],
                expected_manifest_signature_b64=inp["signature_b64"],
                expected_manifest_public_key_b64=inp[
                    "public_key_b64"
                ],
            )
            detail = verify_rekor_anchor_offline_detail(
                anchor=anchor,
                expected_manifest_canonical_bytes=inp[
                    "canonical_bytes"
                ],
                expected_manifest_signature_b64=inp["signature_b64"],
                expected_manifest_public_key_b64=inp[
                    "public_key_b64"
                ],
            )
            expected = (
                detail.pubkey_in_allowlist
                and detail.set_signature_ok
                and detail.inclusion_body_ok
            )
            assert legacy == expected, (
                f"mismatch on {fname}: legacy={legacy} "
                f"detail.AND={expected}"
            )
