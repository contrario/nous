from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# __s150_u1_glm_manifest_module_v1__

GLM_DIGEST_PLACEHOLDER = "<computed-at-publish-time>"
GLM_SIGNATURE_PLACEHOLDER = "<signed-at-publish-time>"

KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64: tuple[str, ...] = (
    "lC/9LQHWjregBHiEklWdr/Bo0lTJZjAE/IwTf2Mbg1A=",  # __s150_u2_glm_pin_v1__
)


class GlmManifestError(ValueError):
    """The manifest text is structurally invalid (a precondition failure)."""


def _quoted(value: str) -> str:
    return '"' + value + '"'


def _require_single(text: str, needle: str, what: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise GlmManifestError(
            what + " must appear exactly once in the manifest text; found "
            + str(count) + " (refusing ambiguous substitution, fail closed)"
        )


def _block_value(
    manifest: Mapping[str, object], outer: str, inner: str
) -> object:
    block = manifest.get(outer)
    if not isinstance(block, Mapping):
        raise GlmManifestError("manifest has no '" + outer + "' object")
    return block.get(inner)


def canonical_glm_bytes(served_text: str) -> bytes:
    """Return the placeholder-form bytes the manifest digest and any Rekor leaf
    commit to: the served manifest text with manifest_digest.value replaced by
    GLM_DIGEST_PLACEHOLDER and, when a signature is present,
    manifest_signature.value replaced by GLM_SIGNATURE_PLACEHOLDER.

    Operates by exact-quoted-string substitution on the served bytes, never by
    re-serialization, so it is faithful to the file as served and stays
    compatible with the pre-existing single-placeholder digest method. Refuses
    fail-closed if either value is not present exactly once.
    """
    try:
        manifest = json.loads(served_text)
    except ValueError as exc:
        raise GlmManifestError(
            "manifest is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise GlmManifestError("manifest is not a JSON object")

    digest_value = _block_value(manifest, "manifest_digest", "value")
    if not isinstance(digest_value, str) or not digest_value:
        raise GlmManifestError(
            "manifest_digest.value is missing or not a string"
        )

    text = served_text
    digest_quoted = _quoted(digest_value)
    _require_single(text, digest_quoted, "manifest_digest.value")
    text = text.replace(digest_quoted, _quoted(GLM_DIGEST_PLACEHOLDER), 1)

    sig_value = _block_value(manifest, "manifest_signature", "value")
    if isinstance(sig_value, str) and sig_value:
        sig_quoted = _quoted(sig_value)
        _require_single(served_text, sig_quoted, "manifest_signature.value")
        text = text.replace(sig_quoted, _quoted(GLM_SIGNATURE_PLACEHOLDER), 1)

    return text.encode("utf-8")


def compute_glm_digest(served_text: str) -> str:
    """Hex SHA-256 over the canonical (placeholder-form) manifest bytes."""
    return hashlib.sha256(canonical_glm_bytes(served_text)).hexdigest()


def seal_glm_manifest(
    manifest: Mapping[str, object],
    *,
    private_key: Ed25519PrivateKey | None,
) -> str:
    """Serialize a manifest into its served text with a recomputed
    manifest_digest.value and, when a key is supplied, an Ed25519
    manifest_signature over the 32-byte digest.

    The hashed canonical form is always the placeholder form, so swapping the
    placeholder for the 64-char digest, and the signature, after hashing never
    invalidates the digest. Refuses fail-closed on placeholder collision.
    """
    doc = copy.deepcopy(dict(manifest))

    digest_block = doc.get("manifest_digest")
    if not isinstance(digest_block, dict):
        raise GlmManifestError(
            "manifest has no 'manifest_digest' object to seal"
        )
    digest_block["value"] = GLM_DIGEST_PLACEHOLDER

    sig_block = doc.get("manifest_signature")
    if not isinstance(sig_block, dict):
        raise GlmManifestError(
            "manifest has no 'manifest_signature' object to seal"
        )

    if private_key is not None:
        public_raw = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        sig_block["type"] = "ed25519"
        sig_block["public_key"] = base64.b64encode(public_raw).decode("ascii")
        sig_block["value"] = GLM_SIGNATURE_PLACEHOLDER
    else:
        sig_block["type"] = None
        sig_block["value"] = None

    text_ph = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"

    digest_ph_quoted = _quoted(GLM_DIGEST_PLACEHOLDER)
    _require_single(text_ph, digest_ph_quoted, "digest placeholder")
    digest_hex = hashlib.sha256(text_ph.encode("utf-8")).hexdigest()
    served = text_ph.replace(digest_ph_quoted, _quoted(digest_hex), 1)

    if private_key is not None:
        sig_ph_quoted = _quoted(GLM_SIGNATURE_PLACEHOLDER)
        _require_single(text_ph, sig_ph_quoted, "signature placeholder")
        signature = private_key.sign(bytes.fromhex(digest_hex))
        sig_b64 = base64.b64encode(signature).decode("ascii")
        served = served.replace(sig_ph_quoted, _quoted(sig_b64), 1)

    return served


@dataclass(frozen=True, slots=True)
class GlmVerifyDetail:
    """Discriminated per-step result of verifying a GLM manifest."""

    digest_ok: bool
    signature_present: bool
    signer_pinned: bool
    signature_ok: bool
    anchor_present: bool
    anchor_ok: bool
    declared_digest: str | None
    computed_digest: str | None
    owner_version: str | None
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return self.digest_ok and self.signature_ok


def verify_glm_manifest(
    served_text: str,
    *,
    rekor_anchor: Mapping[str, object] | None = None,
    trusted_keys_b64: Sequence[str] = KNOWN_GLM_MANIFEST_PUBLIC_KEYS_B64,
    trusted_log_keys: Mapping[str, Ed25519PublicKey] | None = None,
) -> GlmVerifyDetail:
    """Verify a GLM manifest fail-closed: recompute the placeholder-form digest
    and match manifest_digest.value, then (if a signature is present) verify the
    Ed25519 signature over the 32-byte digest against a pinned key allowlist,
    then (if a Rekor anchor is supplied) verify it over the same canonical bytes
    against pinned Sigstore log keys.

    Raises GlmManifestError only on a structurally invalid manifest. All
    cryptographic outcomes are reported as per-step booleans. With the default
    empty pinned allowlist (no signing ceremony has run) signature verification
    fails closed: no trusted key matches.
    """
    try:
        manifest = json.loads(served_text)
    except ValueError as exc:
        raise GlmManifestError(
            "manifest is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise GlmManifestError("manifest is not a JSON object")

    errors: list[str] = []

    owner = manifest.get("owner")
    owner_version_raw = (
        owner.get("version") if isinstance(owner, Mapping) else None
    )
    owner_version = (
        owner_version_raw if isinstance(owner_version_raw, str) else None
    )

    declared_raw = _block_value(manifest, "manifest_digest", "value")
    declared = declared_raw if isinstance(declared_raw, str) else None

    computed: str | None = None
    digest_ok = False
    try:
        computed = compute_glm_digest(served_text)
        if declared is not None and computed == declared:
            digest_ok = True
        else:
            errors.append(
                "manifest_digest.value does not match the recomputed digest "
                "of the canonical (placeholder) manifest bytes"
            )
    except GlmManifestError as exc:
        errors.append("digest recompute failed: " + str(exc))

    sig_block = manifest.get("manifest_signature")
    sig_value = (
        sig_block.get("value") if isinstance(sig_block, Mapping) else None
    )
    pub_b64 = (
        sig_block.get("public_key")
        if isinstance(sig_block, Mapping)
        else None
    )
    signature_present = isinstance(sig_value, str) and bool(sig_value)
    signer_pinned = False
    signature_ok = False

    if not signature_present:
        errors.append(
            "manifest carries no Ed25519 signature (digest-only: content "
            "integrity without authorship)"
        )
    elif not isinstance(pub_b64, str) or not pub_b64:
        errors.append("manifest_signature.public_key is missing")
    elif pub_b64 not in set(trusted_keys_b64):
        errors.append(
            "manifest signing key is not in the pinned GLM allowlist "
            "(no signing ceremony pin, or a foreign signer)"
        )
    elif declared is None:
        errors.append("cannot verify signature: manifest_digest.value absent")
    else:
        signer_pinned = True
        try:
            pub_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(pub_b64, validate=True)
            )
            pub_key.verify(
                base64.b64decode(sig_value, validate=True),
                bytes.fromhex(declared),
            )
            signature_ok = True
        except InvalidSignature:
            errors.append("manifest Ed25519 signature does not verify")
        except (binascii.Error, ValueError) as exc:
            errors.append("manifest signature decode error: " + str(exc))

    anchor_present = rekor_anchor is not None
    anchor_ok = False
    if anchor_present:
        try:
            from rekor_verify_v2 import (
                load_trusted_log_keys,
                verify_rekor_v2_anchor,
            )
        except ImportError as exc:
            errors.append("rekor verify unavailable: " + str(exc))
        else:
            keys = (
                load_trusted_log_keys()
                if trusted_log_keys is None
                else trusted_log_keys
            )
            try:
                body_bytes = canonical_glm_bytes(served_text)
                detail = verify_rekor_v2_anchor(
                    manifest_body_bytes=body_bytes,
                    block=rekor_anchor,
                    trusted_log_keys=keys,
                )
                anchor_ok = detail.ok
                if not anchor_ok:
                    errors.extend("anchor: " + e for e in detail.errors)
            except Exception as exc:  # noqa: BLE001
                errors.append("anchor verify failed: " + str(exc))

    return GlmVerifyDetail(
        digest_ok=digest_ok,
        signature_present=signature_present,
        signer_pinned=signer_pinned,
        signature_ok=signature_ok,
        anchor_present=anchor_present,
        anchor_ok=anchor_ok,
        declared_digest=declared,
        computed_digest=computed,
        owner_version=owner_version,
        errors=tuple(errors),
    )
