from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

import guardrails_adapter
import llm_guard_adapter

_GENESIS_TIMESTAMP_UTC = "1970-01-01T00:00:00Z"
_GENESIS_NOUS_VERSION = "genesis"

_FROZEN = {
    "guardrails": {
        "module": guardrails_adapter,
        "tag": b"nous/guardrails-validation/v1|",
        "manifest_attr": "GuardrailsDossierManifest",
        "pubkey_b64": "mZO/GgpDIG+awgUmtlKV5/axlghzXY1L5qs7hfGty/k=",
        "signature_b64": (
            "i8tmMWdpaiQdz+2ou4O1iE7bvafYp2+O6T9oyFxvqthSe8CHfXoMGLRG2JV"
            "x4qWvWZM25DyXvjfCXJbNPWAxBA=="
        ),
        "commitment_sha256": (
            "4c2b53116453db524db98e22b660fbbeb2d504abfba4a0e685002daa0770e5aa"
        ),
    },
    "llm_guard": {
        "module": llm_guard_adapter,
        "tag": b"nous/llm-guard-scan/v1|",
        "manifest_attr": "LLMGuardDossierManifest",
        "pubkey_b64": "Bovf9PMU7RsLVCKICRaGW2x2PUMHJ63n6IGIbPPDXOk=",
        "signature_b64": (
            "lFRmJNDcMB3UTYIF1Kr5KQScIbg/b7gklhi6CVBOBkQQP9coR7ORYqaBkl0"
            "eCFK1uXIuKhmgLygMXORpWDmjAg=="
        ),
        "commitment_sha256": (
            "98bb8b7b20ce9f12366268aff5da715a8a9007d1cd6b932f9ddf73bce5d1511d"
        ),
    },
}


def _sentinel_commitment(spec):
    mod = spec["module"]
    tag = spec["tag"]
    manifest_cls = getattr(mod, spec["manifest_attr"])
    manifest = manifest_cls(
        nous_version=_GENESIS_NOUS_VERSION,
        upstream_digest=hashlib.sha256(tag + b"|genesis-upstream").hexdigest(),
        projection_digest=hashlib.sha256(
            tag + b"|genesis-projection"
        ).hexdigest(),
        timestamp_utc=_GENESIS_TIMESTAMP_UTC,
    )
    return mod.dossier_commitment(manifest), manifest


def test_frozen_commit_tags():
    assert (
        guardrails_adapter.GUARDRAILS_COMMIT_TAG
        == b"nous/guardrails-validation/v1|"
    )
    assert (
        llm_guard_adapter.LLM_GUARD_COMMIT_TAG == b"nous/llm-guard-scan/v1|"
    )


def test_frozen_source_kinds():
    assert (
        guardrails_adapter.GUARDRAILS_SOURCE_KIND
        == "guardrails-ai/validation/decision"
    )
    assert (
        llm_guard_adapter.LLM_GUARD_SOURCE_KIND == "llm-guard/scan/decision"
    )


@pytest.mark.parametrize("name", ["guardrails", "llm_guard"])
def test_genesis_commitment_matches_frozen(name):
    spec = _FROZEN[name]
    commitment, _manifest = _sentinel_commitment(spec)
    assert commitment.hex() == spec["commitment_sha256"]


@pytest.mark.parametrize("name", ["guardrails", "llm_guard"])
def test_genesis_signature_verifies(name):
    spec = _FROZEN[name]
    commitment, _manifest = _sentinel_commitment(spec)
    pub = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(spec["pubkey_b64"], validate=True)
    )
    sig = base64.b64decode(spec["signature_b64"], validate=True)
    pub.verify(sig, commitment)


@pytest.mark.parametrize("name", ["guardrails", "llm_guard"])
def test_genesis_signature_rejects_flipped_tag(name):
    spec = _FROZEN[name]
    mod = spec["module"]
    _commitment, manifest = _sentinel_commitment(spec)
    flipped = bytearray(spec["tag"])
    flipped[0] ^= 0x01
    flipped_commitment = hashlib.sha256(
        bytes(flipped) + mod._public_body(manifest)
    ).digest()
    pub = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(spec["pubkey_b64"], validate=True)
    )
    sig = base64.b64decode(spec["signature_b64"], validate=True)
    with pytest.raises(InvalidSignature):
        pub.verify(sig, flipped_commitment)
