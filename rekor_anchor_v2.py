"""
NOUS Sigstore Rekor v2 transparency-log anchor (emission / write path).

Submits a NOUS Manifest's canonical bytes to a Rekor v2 tile-backed
transparency log (``log2025-1.rekor.sigstore.dev``) via the typed
``hashedrekord 0.0.2`` entry type, then captures a RekorAnchorV2 object
that can be embedded in the dossier envelope and verified OFFLINE later
using only the ``cryptography`` library plus stdlib.

This is the WRITE counterpart to rekor_verify_v2.py (read path) and the v2
counterpart to rekor_anchor.py (v1 write path). The proven v1 submission
client is left untouched; v2 uses a separate request envelope
(CreateEntryRequest / HashedRekordRequestV002) and a separate response
shape (TransparencyLogEntry) that carries the inclusion proof and signed
checkpoint inline in a single round-trip.

Wire contract (pinned from sigstore/rekor-tiles api/proto/rekor/v2 and
sigstore/protobuf-specs protos/sigstore_rekor.proto):

  Request body (protojson, POST /api/v2/log/entries):
    {
      "hashedRekordRequestV002": {
        "digest":    b64(raw sha256 of canonical bytes),
        "signature": {
          "content": b64(DER ECDSA-P-256 signature over canonical bytes),
          "verifier": {
            "publicKey": {"rawBytes": b64(DER SubjectPublicKeyInfo)},
            "keyDetails": "PKIX_ECDSA_P256_SHA_256"
          }
        }
      }
    }

  Response (protojson TransparencyLogEntry; int64 -> JSON string,
  bytes -> standard base64):
    logIndex, logId.keyId, canonicalizedBody,
    inclusionProof.{hashes[], checkpoint.envelope}

Leaf semantics match v1: a per-submission ephemeral ECDSA-P-256 keypair
signs SHA-256 of the manifest canonical bytes; the ECDSA signature, the
ECDSA public key, and the raw digest are submitted. The offline verifier
recovers the digest, public key, and signature from the canonicalized leaf
body and checks them against the manifest body bytes (rekor_verify_v2 /
rekor_entry); the checkpoint signature is checked against the pinned v2 log
key allowlist (KNOWN_REKOR_V2_LOG_KEYS), not a per-entry fetched key, so no
publicKey GET is performed on this path.

Public API:
  REKOR_V2_DEFAULT_BASE_URL          str, log2025-1 tile-backed log
  KEY_DETAILS_ECDSA_P256_SHA_256     str, PublicKeyDetails enum literal
  anchor_manifest_to_rekor_v2(...)   submit + capture; returns RekorAnchorV2

# __nous_aetherproof_rekor_anchor_v2_module_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

from rekor_anchor import (
    REKOR_CONNECT_TIMEOUT_S,
    REKOR_DEFAULT_TIMEOUT_S,
    RekorRejected,
    RekorUnavailable,
)
from rekor_signing_config import REKOR_V2_ENTRIES_PATH
from rekor_verify_v2 import RekorAnchorV2

REKOR_V2_DEFAULT_BASE_URL: str = "https://log2025-1.rekor.sigstore.dev"
KEY_DETAILS_ECDSA_P256_SHA_256: str = "PKIX_ECDSA_P256_SHA_256"


def _build_create_entry_request(
    manifest_canonical_bytes: bytes,
    signing_key: ec.EllipticCurvePrivateKey,
) -> dict[str, object]:
    digest_raw = hashlib.sha256(manifest_canonical_bytes).digest()
    signature_der = signing_key.sign(
        manifest_canonical_bytes, ECDSA(hashes.SHA256())
    )
    public_key_der = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "hashedRekordRequestV002": {
            "digest": base64.b64encode(digest_raw).decode("ascii"),
            "signature": {
                "content": base64.b64encode(signature_der).decode("ascii"),
                "verifier": {
                    "publicKey": {
                        "rawBytes": base64.b64encode(
                            public_key_der
                        ).decode("ascii"),
                    },
                    "keyDetails": KEY_DETAILS_ECDSA_P256_SHA_256,
                },
            },
        },
    }


def _parse_transparency_log_entry(envelope: object) -> RekorAnchorV2:
    if not isinstance(envelope, dict):
        raise RekorRejected(
            "rekor v2 submit returned non-object TransparencyLogEntry "
            f"(type={type(envelope).__name__})"
        )
    try:
        log_index = int(envelope["logIndex"])
        log_id_field = envelope["logId"]
        if isinstance(log_id_field, dict):
            log_id = str(log_id_field["keyId"])
        else:
            log_id = str(log_id_field)
        canonicalized_body = str(envelope["canonicalizedBody"])
        inclusion_proof = envelope["inclusionProof"]
        if not isinstance(inclusion_proof, dict):
            raise TypeError("inclusionProof is not an object")
        checkpoint = inclusion_proof["checkpoint"]
        if not isinstance(checkpoint, dict):
            raise TypeError("inclusionProof.checkpoint is not an object")
        checkpoint_envelope = str(checkpoint["envelope"])
        hashes_field = inclusion_proof["hashes"]
        if not isinstance(hashes_field, list):
            raise TypeError("inclusionProof.hashes is not a list")
        inclusion_proof_hashes = [str(h) for h in hashes_field]
    except (KeyError, TypeError, ValueError) as exc:
        raise RekorRejected(
            f"rekor v2 TransparencyLogEntry missing required fields: {exc!r}"
        ) from exc
    return RekorAnchorV2(
        rekor_api_version=2,
        log_id=log_id,
        log_index=log_index,
        body_b64=canonicalized_body,
        checkpoint_envelope=checkpoint_envelope,
        inclusion_proof_hashes=inclusion_proof_hashes,
    )


def anchor_manifest_to_rekor_v2(
    manifest_canonical_bytes: bytes,
    *,
    client: Optional[httpx.Client] = None,
    base_url: str = REKOR_V2_DEFAULT_BASE_URL,
    timeout_seconds: float = REKOR_DEFAULT_TIMEOUT_S,
) -> RekorAnchorV2:
    own_client = False
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(
                timeout_seconds, connect=REKOR_CONNECT_TIMEOUT_S
            ),
        )
        own_client = True

    try:
        signing_key = ec.generate_private_key(ec.SECP256R1())
        body = _build_create_entry_request(
            manifest_canonical_bytes, signing_key
        )
        try:
            response = client.post(
                base_url + REKOR_V2_ENTRIES_PATH,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as exc:
            raise RekorUnavailable(
                f"failed to submit to rekor v2: {exc!r}"
            ) from exc

        if response.status_code not in (200, 201):
            detail = response.text[:512]
            raise RekorRejected(
                f"rekor v2 submit returned HTTP {response.status_code}: "
                f"{detail}"
            )

        try:
            envelope = response.json()
        except json.JSONDecodeError as exc:
            raise RekorRejected(
                f"rekor v2 submit returned non-JSON: {exc!r}"
            ) from exc

        return _parse_transparency_log_entry(envelope)
    finally:
        if own_client:
            client.close()
