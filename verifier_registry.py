"""Cross-version verifier-digest registry for NOUS dossier verifiers.
# __s148_u1_verifier_registry_module_v1__

A static, Ed25519-signed, optionally Rekor-v2-anchored file that maps each
official ``VERIFY_OFFLINE_PY*`` dossier verifier template (by name and emitting
NOUS version) to its sha256 digest. It exists to break the version-coupling of
the S147 installed allowlist (``ndec.canonical_verifier_digests``), which can
only confirm a carried verifier whose bytes match the LOCALLY installed
``dossier.py`` templates. A legitimate older .ndec whose carried verifier was
emitted by a different NOUS release fails that local match and degrades.

This registry is a SUPPLEMENT to that local match, never a replacement. Its two
honest tiers:

  signed  -- the registry Ed25519 signature verifies against a pinned NOUS
             registry public key. Evidences a NOUS-authored cross-version
             allowlist (covers versions other than the local install).
  logged  -- signed AND a Rekor v2 hashedrekord inclusion proof + checkpoint
             over the same canonical body verifies against pinned Sigstore log
             keys. Evidences that the allowlist is publicly logged and
             append-only: a third party runs a standard Rekor monitor and
             DETECTS if NOUS ever blesses a digest it should not.

Honest boundary (fixed): registry membership EVIDENCES that a verifier digest
is an officially-published (signed) and, at the logged tier, publicly-logged
NOUS verifier template. It does NOT prove the verifier is correct, the decision
is correct, or compliance. "Proves" is reserved for Z3 cost bounds and Farkas
certificates.

Determinism / serialization. The registry is modeled as plain dicts serialized
with deterministic sorted-keys compact JSON, NOT as Pydantic models. Documented
relaxation of the Pydantic-strict default (project axiom 6): the canonical body
is both Ed25519-signed and Rekor-anchored and must be byte-preserved; routing
it through a Pydantic model risks re-serialization drift that would break
byte-identity of the signed and anchored payload. This mirrors ndec.py for the
same reason. The canonical body is the registry minus BOTH ``signature`` and
``rekor_anchor`` (both cover that same body), exactly as a dossier manifest
strips ``signature`` and ``transparency_log``.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from rekor_verify_v2 import (
    RekorV2AnchorMalformed,
    RekorV2Error,
    load_trusted_log_keys,
    verify_rekor_v2_anchor,
)

REGISTRY_SCHEMA: int = 1

KNOWN_REGISTRY_PUBLIC_KEYS_B64: tuple[str, ...] = (
    "cDpi1vlquPoXHKsWMowN01UQOigIZHSvmm9AkgzZlcQ=",  # __s149_u4_registry_pin_v1__
)


class RegistryError(ValueError):
    """Raised on a structurally invalid registry (a precondition failure)."""


@dataclass(frozen=True, slots=True)
class RegistryVerifyDetail:
    """Discriminated per-step result of verifying a registry."""

    signature_ok: bool
    anchor_present: bool
    anchor_ok: bool
    tier: str | None
    entries_count: int
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        if not self.signature_ok:
            return False
        if self.anchor_present:
            return self.anchor_ok
        return True


@dataclass(frozen=True, slots=True)
class RegistryConfirmation:
    """Result of confirming a single verifier digest against a registry."""

    confirmed: bool
    template_name: str | None
    nous_version: str | None
    tier: str | None
    reason: str


def _is_hex64(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(c in "0123456789abcdef" for c in value)


def canonical_registry_body_bytes(registry: Mapping[str, object]) -> bytes:
    """Canonical body bytes: the registry minus ``signature`` and
    ``rekor_anchor``, serialized as sorted-keys compact JSON. Both the
    Ed25519 signature and the Rekor leaf digest cover exactly these bytes.
    """
    body = {
        k: v
        for k, v in registry.items()
        if k not in ("signature", "rekor_anchor")
    }
    return json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_registry(
    entries: Sequence[Mapping[str, object]],
    *,
    registry_schema: int = REGISTRY_SCHEMA,
) -> dict:
    """Assemble an unsigned, un-anchored registry from verifier entries.

    Each entry must carry ``template_name`` (a ``VERIFY_OFFLINE_PY*`` name),
    ``template_sha256`` (64-char lowercase hex), and ``nous_version`` (a
    non-empty string). Refuses on any malformed or duplicate entry rather
    than emitting an ambiguous registry (project axiom 5, refuse over guess).
    Entries are normalized and deterministically sorted so the canonical body
    is byte-stable across producers.
    """
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise RegistryError("entries is not a sequence")
    if not entries:
        raise RegistryError("registry must declare at least one entry")
    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, str]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise RegistryError(f"entry[{idx}] is not an object")
        name = entry.get("template_name")
        sha = entry.get("template_sha256")
        version = entry.get("nous_version")
        if not isinstance(name, str) or not name.startswith(
            "VERIFY_OFFLINE_PY"
        ):
            raise RegistryError(
                f"entry[{idx}].template_name is not a VERIFY_OFFLINE_PY* "
                f"name: {name!r}"
            )
        if not _is_hex64(sha):
            raise RegistryError(
                f"entry[{idx}].template_sha256 is not 64-char lowercase "
                f"hex: {sha!r}"
            )
        if not isinstance(version, str) or not version:
            raise RegistryError(
                f"entry[{idx}].nous_version is missing or not a non-empty "
                f"string: {version!r}"
            )
        key = (name, version)
        if key in seen:
            raise RegistryError(
                f"duplicate registry entry for (template_name={name!r}, "
                f"nous_version={version!r})"
            )
        seen.add(key)
        normalized.append(
            {
                "template_name": name,
                "template_sha256": sha,  # type: ignore[dict-item]
                "nous_version": version,
            }
        )
    normalized.sort(
        key=lambda e: (
            e["template_name"],
            e["nous_version"],
            e["template_sha256"],
        )
    )
    return {"registry_schema": int(registry_schema), "entries": normalized}


def sign_registry(
    unsigned: Mapping[str, object],
    private_key: Ed25519PrivateKey,
) -> dict:
    """Attach an Ed25519 signature block over the canonical body bytes.

    The input must not already carry ``signature`` or ``rekor_anchor``; both
    are stripped to form the canonical body regardless, but signing an input
    that already declares them is refused to avoid masking an authoring bug.
    """
    if "signature" in unsigned:
        raise RegistryError("registry already carries a signature block")
    if "rekor_anchor" in unsigned:
        raise RegistryError(
            "registry already carries a rekor_anchor; anchor is attached "
            "after signing, never before"
        )
    body_bytes = canonical_registry_body_bytes(unsigned)
    signature = private_key.sign(body_bytes)
    public_raw = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    out = dict(unsigned)
    out["signature"] = {
        "public_key_b64": base64.b64encode(public_raw).decode("ascii"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    return out


def verify_registry(
    registry: Mapping[str, object],
    *,
    trusted_registry_keys_b64: Sequence[str] = KNOWN_REGISTRY_PUBLIC_KEYS_B64,
    trusted_log_keys: Mapping[str, Ed25519PublicKey] | None = None,
) -> RegistryVerifyDetail:
    """Verify a registry fail-closed: Ed25519 signature against a pinned
    registry-key allowlist, then (if present) the Rekor v2 anchor over the
    same canonical body against pinned Sigstore log keys.

    Raises RegistryError only on a structurally invalid registry (a
    precondition / dispatch failure). All cryptographic outcomes are reported
    as per-step booleans in the returned detail. With the default empty pinned
    allowlist (no registry-signing ceremony has run), signature verification
    fails closed: no trusted key matches.
    """
    if not isinstance(registry, Mapping):
        raise RegistryError("registry is not an object")
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise RegistryError("registry has no entries list")
    entries_count = len(entries)

    errors: list[str] = []
    body_bytes = canonical_registry_body_bytes(registry)

    signature_ok = False
    sig_block = registry.get("signature")
    if not isinstance(sig_block, Mapping):
        errors.append("registry has no signature block")
    else:
        pub_b64 = sig_block.get("public_key_b64")
        sig_b64 = sig_block.get("signature_b64")
        if not isinstance(pub_b64, str) or not isinstance(sig_b64, str):
            errors.append("registry signature block is incomplete")
        elif pub_b64 not in set(trusted_registry_keys_b64):
            errors.append(
                "registry public key is not in the pinned registry-key "
                "allowlist (no registry-signing ceremony pin, or a foreign "
                "signer)"
            )
        else:
            try:
                pub_key = Ed25519PublicKey.from_public_bytes(
                    base64.b64decode(pub_b64, validate=True)
                )
                pub_key.verify(
                    base64.b64decode(sig_b64, validate=True), body_bytes
                )
                signature_ok = True
            except InvalidSignature:
                errors.append("registry Ed25519 signature does not verify")
            except (binascii.Error, ValueError) as exc:
                errors.append(f"registry signature decode error: {exc}")

    anchor = registry.get("rekor_anchor")
    anchor_present = anchor is not None
    anchor_ok = False
    if anchor_present:
        if not isinstance(anchor, Mapping):
            errors.append("registry rekor_anchor is not an object")
        else:
            keys = (
                load_trusted_log_keys()
                if trusted_log_keys is None
                else trusted_log_keys
            )
            try:
                detail = verify_rekor_v2_anchor(
                    manifest_body_bytes=body_bytes,
                    block=anchor,
                    trusted_log_keys=keys,
                )
                anchor_ok = detail.ok
                if not anchor_ok:
                    errors.extend(
                        f"anchor: {e}" for e in detail.errors
                    )
            except (RekorV2AnchorMalformed, RekorV2Error) as exc:
                errors.append(f"anchor malformed: {exc}")

    if signature_ok and anchor_present and anchor_ok:
        tier: str | None = "logged"
    elif signature_ok and not anchor_present:
        tier = "signed"
    else:
        tier = None

    return RegistryVerifyDetail(
        signature_ok=signature_ok,
        anchor_present=anchor_present,
        anchor_ok=anchor_ok,
        tier=tier,
        entries_count=entries_count,
        errors=tuple(errors),
    )


def confirm_digest(
    registry: Mapping[str, object],
    template_sha256: str,
    *,
    trusted_registry_keys_b64: Sequence[str] = KNOWN_REGISTRY_PUBLIC_KEYS_B64,
    trusted_log_keys: Mapping[str, Ed25519PublicKey] | None = None,
    require_anchor: bool = False,
) -> RegistryConfirmation:
    """Confirm a single verifier-template digest against a registry.

    Fail-closed: the registry signature must verify; if ``require_anchor`` is
    set, the Rekor v2 anchor must also be present and verify. Only then is
    membership consulted. Returns a RegistryConfirmation carrying the tier at
    which the registry verified and, on success, the matched template name and
    NOUS version.
    """
    if not _is_hex64(template_sha256):
        return RegistryConfirmation(
            confirmed=False,
            template_name=None,
            nous_version=None,
            tier=None,
            reason="queried template_sha256 is not 64-char lowercase hex",
        )
    detail = verify_registry(
        registry,
        trusted_registry_keys_b64=trusted_registry_keys_b64,
        trusted_log_keys=trusted_log_keys,
    )
    if not detail.signature_ok:
        return RegistryConfirmation(
            confirmed=False,
            template_name=None,
            nous_version=None,
            tier=None,
            reason="registry signature did not verify: "
            + "; ".join(detail.errors),
        )
    if require_anchor and not (detail.anchor_present and detail.anchor_ok):
        return RegistryConfirmation(
            confirmed=False,
            template_name=None,
            nous_version=None,
            tier=detail.tier,
            reason="registry is not anchored to the public log or the "
            "anchor failed (require_anchor): "
            + "; ".join(detail.errors),
        )
    entries = registry.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if (
                isinstance(entry, Mapping)
                and entry.get("template_sha256") == template_sha256
            ):
                return RegistryConfirmation(
                    confirmed=True,
                    template_name=(
                        entry.get("template_name")
                        if isinstance(entry.get("template_name"), str)
                        else None
                    ),
                    nous_version=(
                        entry.get("nous_version")
                        if isinstance(entry.get("nous_version"), str)
                        else None
                    ),
                    tier=detail.tier,
                    reason="digest confirmed at tier " + str(detail.tier),
                )
    return RegistryConfirmation(
        confirmed=False,
        template_name=None,
        nous_version=None,
        tier=detail.tier,
        reason="digest is not present in the registry entries",
    )
