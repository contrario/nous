"""NOUS Rekor v2 anchor verifier (in-package, offline).

Verifies a NOUS manifest's Rekor v2 transparency-log anchor block by
composing the leaf normalizer (rekor_entry) and the checkpoint + inclusion
verifier (rekor_checkpoint) with the Path-beta leaf-to-manifest ECDSA tie.

The anchor block is discriminated by an explicit ``rekor_api_version`` field
present only in v2 blocks; v1 blocks omit it. The reader treats absence as
v1, so v1 manifest bytes (and every historical v1 dossier signature) are
left byte-identical. Adding the discriminator to v1 would change those bytes
and invalidate all historical anchors, a hard regression.

verify_rekor_v2_anchor returns a RekorV2VerifyDetail with four independent
per-step booleans (leaf-to-manifest digest tie, leaf ECDSA signature,
checkpoint Ed25519 signature, RFC 6962 inclusion proof). Each step is
evaluated independently with no early exit, so an auditor inspecting a
failed v2 anchor sees exactly which of the four cryptographic links broke
rather than a single opaque false. The overall verdict (ok) is the
conjunction of the four; it is derived, not stored, so the four booleans
remain the single source of truth.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import load_der_public_key
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rekor_checkpoint import (
    CheckpointError,
    InclusionProofError,
    parse_checkpoint,
    rfc6962_leaf_hash,
    verify_checkpoint_ed25519,
    verify_inclusion_proof,
)
from rekor_entry import RekorEntryError, parse_rekor_leaf

KNOWN_REKOR_V2_LOG_KEYS: dict[str, str] = {}


class RekorV2Error(ValueError):
    """Base class for Rekor v2 anchor verification failures."""


class RekorV2AnchorMalformed(RekorV2Error):
    """The v2 anchor block is structurally invalid (precondition failure)."""


class RekorAnchorV2(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    rekor_api_version: int = Field(default=2)
    log_id: str = Field(min_length=1)
    log_index: int = Field(ge=0)
    body_b64: str = Field(min_length=1)
    checkpoint_envelope: str = Field(min_length=1)
    inclusion_proof_hashes: list[str]

    def to_manifest_block(self) -> dict:
        return {
            "rekor_api_version": self.rekor_api_version,
            "log_id": self.log_id,
            "log_index": self.log_index,
            "body_b64": self.body_b64,
            "checkpoint_envelope": self.checkpoint_envelope,
            "inclusion_proof_hashes": list(self.inclusion_proof_hashes),
        }

    @classmethod
    def from_manifest_block(cls, block: Mapping[str, object]) -> "RekorAnchorV2":
        if block.get("rekor_api_version") != 2:
            raise RekorV2AnchorMalformed(
                "block rekor_api_version is not 2 (not a v2 anchor block)"
            )
        try:
            hashes_field = block["inclusion_proof_hashes"]
            if not isinstance(hashes_field, list):
                raise TypeError("inclusion_proof_hashes is not a list")
            return cls(
                rekor_api_version=2,
                log_id=str(block["log_id"]),
                log_index=int(block["log_index"]),  # type: ignore[arg-type]
                body_b64=str(block["body_b64"]),
                checkpoint_envelope=str(block["checkpoint_envelope"]),
                inclusion_proof_hashes=[str(h) for h in hashes_field],
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise RekorV2AnchorMalformed(
                f"invalid v2 anchor block: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class RekorV2VerifyDetail:
    """Discriminated per-step result of verifying a Rekor v2 anchor."""

    leaf_digest_ok: bool
    leaf_sig_ok: bool
    checkpoint_sig_ok: bool
    inclusion_proof_ok: bool
    api_version: str | None
    log_index: int | None
    checkpoint_origin: str | None
    tree_size: int | None
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return (
            self.leaf_digest_ok
            and self.leaf_sig_ok
            and self.checkpoint_sig_ok
            and self.inclusion_proof_ok
        )


def load_trusted_log_keys(
    allowlist: Mapping[str, str] | None = None,
) -> dict[str, Ed25519PublicKey]:
    """Decode an origin -> base64 raw Ed25519 pubkey allowlist into keys.

    Defaults to KNOWN_REKOR_V2_LOG_KEYS, which is empty until the production
    Rekor v2 log key is pinned. An empty allowlist makes every v2 checkpoint
    signature verification fail closed (no trusted origin matches).
    """
    source = KNOWN_REKOR_V2_LOG_KEYS if allowlist is None else allowlist
    keys: dict[str, Ed25519PublicKey] = {}
    for origin, b64 in source.items():
        raw = base64.b64decode(b64, validate=True)
        keys[origin] = Ed25519PublicKey.from_public_bytes(raw)
    return keys


def verify_rekor_v2_anchor(
    *,
    manifest_body_bytes: bytes,
    block: Mapping[str, object],
    trusted_log_keys: Mapping[str, Ed25519PublicKey],
) -> RekorV2VerifyDetail:
    """Verify a Rekor v2 anchor block against the signed manifest body bytes.

    Raises RekorV2AnchorMalformed only if the block is not a structurally
    valid v2 anchor (a precondition / dispatch failure). All cryptographic
    outcomes are reported as per-step booleans in the returned detail.
    """
    anchor = RekorAnchorV2.from_manifest_block(block)

    errors: list[str] = []

    leaf = None
    try:
        leaf_raw = base64.b64decode(anchor.body_b64, validate=True)
        leaf = parse_rekor_leaf(json.loads(leaf_raw))
        if leaf.api_version != "0.0.2":
            errors.append(
                f"leaf is hashedrekord {leaf.api_version}, expected 0.0.2"
            )
            leaf = None
    except (binascii.Error, ValueError, RekorEntryError) as exc:
        errors.append(f"leaf parse failed: {exc}")

    leaf_digest_ok = False
    if leaf is not None:
        expected_digest = hashlib.sha256(manifest_body_bytes).hexdigest()
        if leaf.digest_hex == expected_digest:
            leaf_digest_ok = True
        else:
            errors.append(
                "leaf digest does not match sha256(manifest body bytes)"
            )

    leaf_sig_ok = False
    if leaf is not None:
        try:
            leaf_pub = load_der_public_key(leaf.leaf_public_key_der)
            if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):
                errors.append("leaf public key is not an EC key")
            elif not isinstance(leaf_pub.curve, ec.SECP256R1):
                errors.append(
                    f"leaf public key curve is not P-256: {leaf_pub.curve.name}"
                )
            else:
                leaf_pub.verify(
                    leaf.leaf_signature_der,
                    manifest_body_bytes,
                    ec.ECDSA(hashes.SHA256()),
                )
                leaf_sig_ok = True
        except InvalidSignature:
            errors.append(
                "leaf ECDSA signature does not verify over manifest body bytes"
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"leaf signature verification error: {exc}")

    checkpoint = None
    try:
        checkpoint = parse_checkpoint(anchor.checkpoint_envelope)
    except CheckpointError as exc:
        errors.append(f"checkpoint parse failed: {exc}")

    checkpoint_sig_ok = False
    if checkpoint is not None:
        trusted = trusted_log_keys.get(checkpoint.origin)
        if trusted is None:
            errors.append(
                f"checkpoint origin {checkpoint.origin!r} is not in the "
                f"trusted log key allowlist"
            )
        else:
            try:
                verify_checkpoint_ed25519(
                    checkpoint,
                    key_name=checkpoint.origin,
                    public_key=trusted,
                )
                checkpoint_sig_ok = True
            except CheckpointError as exc:
                errors.append(f"checkpoint signature: {exc}")

    inclusion_proof_ok = False
    if checkpoint is not None:
        try:
            leaf_bytes = base64.b64decode(anchor.body_b64, validate=True)
            proof = [
                base64.b64decode(h, validate=True)
                for h in anchor.inclusion_proof_hashes
            ]
            verify_inclusion_proof(
                leaf_hash=rfc6962_leaf_hash(leaf_bytes),
                log_index=anchor.log_index,
                tree_size=checkpoint.tree_size,
                proof=proof,
                root_hash=checkpoint.root_hash,
            )
            inclusion_proof_ok = True
        except (binascii.Error, ValueError, InclusionProofError) as exc:
            errors.append(f"inclusion proof: {exc}")

    return RekorV2VerifyDetail(
        leaf_digest_ok=leaf_digest_ok,
        leaf_sig_ok=leaf_sig_ok,
        checkpoint_sig_ok=checkpoint_sig_ok,
        inclusion_proof_ok=inclusion_proof_ok,
        api_version=(leaf.api_version if leaf is not None else None),
        log_index=anchor.log_index,
        checkpoint_origin=(
            checkpoint.origin if checkpoint is not None else None
        ),
        tree_size=(checkpoint.tree_size if checkpoint is not None else None),
        errors=tuple(errors),
    )
