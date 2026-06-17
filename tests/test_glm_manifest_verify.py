from __future__ import annotations

import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import glm_manifest as gm

# __s150_u1_glm_manifest_tests_v1__


def _minimal_manifest() -> dict:
    return {
        "schema_version": "1.1",
        "manifest_version": "1.0",
        "owner": {"name": "NOUS", "version": "5.49.0"},
        "manifest_digest": {
            "type": "sha256",
            "value": gm.GLM_DIGEST_PLACEHOLDER,
            "canonicalization_method": (
                "SHA-256 over the manifest text with manifest_digest.value set "
                "to the placeholder string <computed-at-publish-time> and "
                "manifest_signature.value set to <signed-at-publish-time>."
            ),
        },
        "manifest_signature": {
            "type": None,
            "value": None,
            "public_key": None,
        },
    }


def test_unsigned_digest_roundtrips() -> None:
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=None)
    detail = gm.verify_glm_manifest(served)
    assert detail.digest_ok is True
    assert detail.signature_present is False
    assert detail.signature_ok is False
    assert detail.owner_version == "5.49.0"
    assert detail.computed_digest == detail.declared_digest


def test_signed_roundtrip_with_pinned_key() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    pub_b64 = gm.base64.b64encode(
        key.public_key().public_bytes(
            gm.serialization.Encoding.Raw,
            gm.serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    detail = gm.verify_glm_manifest(served, trusted_keys_b64=(pub_b64,))
    assert detail.digest_ok is True
    assert detail.signature_present is True
    assert detail.signer_pinned is True
    assert detail.signature_ok is True
    assert detail.ok is True


def test_signed_but_unpinned_fails_closed() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    detail = gm.verify_glm_manifest(served)
    assert detail.digest_ok is True
    assert detail.signature_present is True
    assert detail.signer_pinned is False
    assert detail.signature_ok is False
    assert detail.ok is False
    assert any("pinned GLM allowlist" in e for e in detail.errors)


def test_digest_tamper_fails() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    tampered = served.replace('"5.49.0"', '"9.9.9"', 1)
    assert tampered != served
    pub_b64 = gm.base64.b64encode(
        key.public_key().public_bytes(
            gm.serialization.Encoding.Raw,
            gm.serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    detail = gm.verify_glm_manifest(tampered, trusted_keys_b64=(pub_b64,))
    assert detail.digest_ok is False
    assert detail.ok is False


def test_signature_tamper_fails() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    pub_b64 = gm.base64.b64encode(
        key.public_key().public_bytes(
            gm.serialization.Encoding.Raw,
            gm.serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    import json

    parsed = json.loads(served)
    good_sig = parsed["manifest_signature"]["value"]
    flipped = good_sig[:-2] + ("AA" if good_sig[-2:] != "AA" else "BB")
    tampered = served.replace('"' + good_sig + '"', '"' + flipped + '"', 1)
    assert tampered != served
    detail = gm.verify_glm_manifest(tampered, trusted_keys_b64=(pub_b64,))
    assert detail.digest_ok is True
    assert detail.signature_ok is False
    assert detail.ok is False


def test_ambiguous_digest_value_refused() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    import json

    digest = json.loads(served)["manifest_digest"]["value"]
    duplicated = served.replace(
        '"manifest_version": "1.0"',
        '"manifest_version": "1.0", "_dup": "' + digest + '"',
        1,
    )
    with pytest.raises(gm.GlmManifestError):
        gm.canonical_glm_bytes(duplicated)


def test_canonical_refuses_duplicated_signature_value() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    import json

    sig = json.loads(served)["manifest_signature"]["value"]
    duplicated = served.replace(
        '"manifest_version": "1.0"',
        '"manifest_version": "1.0", "_dup": "' + sig + '"',
        1,
    )
    with pytest.raises(gm.GlmManifestError):
        gm.canonical_glm_bytes(duplicated)


def test_anchor_present_fails_closed() -> None:
    key = Ed25519PrivateKey.generate()
    served = gm.seal_glm_manifest(_minimal_manifest(), private_key=key)
    pub_b64 = gm.base64.b64encode(
        key.public_key().public_bytes(
            gm.serialization.Encoding.Raw,
            gm.serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    bogus_anchor = {
        "rekor_api_version": 2,
        "log_id": "x",
        "log_index": 0,
        "body_b64": "AAAA",
        "checkpoint_envelope": "x",
        "inclusion_proof_hashes": [],
    }
    detail = gm.verify_glm_manifest(
        served, rekor_anchor=bogus_anchor, trusted_keys_b64=(pub_b64,)
    )
    assert detail.anchor_present is True
    assert detail.anchor_ok is False
    assert detail.digest_ok is True
    assert detail.signature_ok is True
    assert detail.ok is True


def test_unchanged_seal_is_deterministic() -> None:
    m = _minimal_manifest()
    a = gm.seal_glm_manifest(copy.deepcopy(m), private_key=None)
    b = gm.seal_glm_manifest(copy.deepcopy(m), private_key=None)
    assert a == b
