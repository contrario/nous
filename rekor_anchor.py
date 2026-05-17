"""
NOUS Sigstore Rekor transparency-log anchor.

Submits the Ed25519 signature event of a NOUS Manifest to the public
Sigstore Rekor transparency log, then captures a RekorAnchor object that
can be embedded in the dossier envelope and verified OFFLINE later using
only the ``cryptography`` library.

External trust root: Sigstore Rekor public Merkle tree at
``https://rekor.sigstore.dev`` (ECDSA P-256 signed tree heads and entry
timestamps). The Rekor public key fetched at submission time is pinned
INTO the dossier; the offline verifier additionally cross-checks that
pinned key against a known-keys allowlist shipped with each NOUS release.

Public API:
  KNOWN_REKOR_PUBLIC_KEYS         list[str], PEM-encoded, allowlist
  RekorAnchor                     Pydantic V2 strict, frozen
  RekorUnavailable                exception, network unreachable / timeout
  RekorRejected                   exception, 4xx/5xx from Rekor
  anchor_manifest_to_rekor(...)   submit + capture; returns RekorAnchor
  verify_rekor_anchor_offline(...) -> bool

# __nous_aetherproof_rekor_anchor_module_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Optional

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from pydantic import BaseModel, ConfigDict, Field

REKOR_DEFAULT_BASE_URL: str = "https://rekor.sigstore.dev"
REKOR_SUBMIT_PATH: str = "/api/v1/log/entries"
REKOR_PUBKEY_PATH: str = "/api/v1/log/publicKey"
REKOR_DEFAULT_TIMEOUT_S: float = 15.0
REKOR_CONNECT_TIMEOUT_S: float = 5.0


KNOWN_REKOR_PUBLIC_KEYS: list[str] = [
    "-----BEGIN PUBLIC KEY-----\n"
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwr\n"
    "kBbmLSGtks4L3qX6yYY0zufBnhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw==\n"
    "-----END PUBLIC KEY-----\n",
]


class RekorAnchor(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    provider: str = Field(default="sigstore-rekor")
    log_id: str
    log_index: int = Field(ge=0)
    integrated_time: int = Field(ge=0)
    signed_entry_timestamp_b64: str = Field(min_length=1)
    body_b64: str = Field(min_length=1)
    rekor_public_key_pem: str = Field(min_length=1)

    def to_manifest_block(self) -> dict:
        return {
            "provider": self.provider,
            "log_id": self.log_id,
            "log_index": self.log_index,
            "integrated_time": self.integrated_time,
            "signed_entry_timestamp_b64": self.signed_entry_timestamp_b64,
            "body_b64": self.body_b64,
            "rekor_public_key_pem": self.rekor_public_key_pem,
        }

    @classmethod
    def from_manifest_block(cls, block: dict) -> "RekorAnchor":
        return cls(
            provider=block.get("provider", "sigstore-rekor"),
            log_id=block["log_id"],
            log_index=int(block["log_index"]),
            integrated_time=int(block["integrated_time"]),
            signed_entry_timestamp_b64=block["signed_entry_timestamp_b64"],
            body_b64=block["body_b64"],
            rekor_public_key_pem=block["rekor_public_key_pem"],
        )


class RekorUnavailable(RuntimeError):
    pass


class RekorRejected(RuntimeError):
    pass


def _raw_ed25519_b64_to_pem(public_key_b64: str) -> str:
    """Convert raw Ed25519 public-key b64 (32 bytes -> 44 chars) into
    standard PEM-encoded SubjectPublicKeyInfo, byte-deterministic.

    Used by both the Rekor submit path and the offline verify path to
    canonicalize Ed25519 public keys into the format that Rekor's
    hashedrekord/0.0.1 schema expects in publicKey.content.

    # __nous_aetherproof_rekor_pubkey_wire_fix_v1__
    """
    raw = base64.b64decode(public_key_b64, validate=True)
    pub = ed25519.Ed25519PublicKey.from_public_bytes(raw)
    pem_bytes = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_bytes.decode("ascii")


def _build_hashedrekord_body(
    payload_sha256_hex: str,
    submitter_signature_b64: str,
    submitter_public_key_pem: str,
) -> dict:
    submitter_pem_b64 = base64.b64encode(
        submitter_public_key_pem.encode("utf-8")
    ).decode("ascii")
    return {
        "kind": "hashedrekord",
        "apiVersion": "0.0.1",
        "spec": {
            "signature": {
                "content": submitter_signature_b64,
                "publicKey": {"content": submitter_pem_b64},
            },
            "data": {
                "hash": {
                    "algorithm": "sha256",
                    "value": payload_sha256_hex,
                },
            },
        },
    }


def _fetch_rekor_public_key_pem(
    client: httpx.Client,
    base_url: str,
) -> str:
    try:
        response = client.get(base_url + REKOR_PUBKEY_PATH)
    except httpx.RequestError as exc:
        raise RekorUnavailable(
            f"failed to fetch rekor public key: {exc!r}"
        ) from exc
    if response.status_code != 200:
        raise RekorRejected(
            f"rekor publicKey returned HTTP {response.status_code}"
        )
    pem_text = response.text
    if "-----BEGIN PUBLIC KEY-----" not in pem_text:
        raise RekorRejected(
            "rekor publicKey response is not PEM-encoded"
        )
    return pem_text


def anchor_manifest_to_rekor(
    manifest_canonical_bytes: bytes,
    manifest_signature_b64: str,
    manifest_public_key_b64: str,
    client: Optional[httpx.Client] = None,
    base_url: str = REKOR_DEFAULT_BASE_URL,
    timeout_seconds: float = REKOR_DEFAULT_TIMEOUT_S,
) -> RekorAnchor:
    """Submit a NOUS manifest hash to Sigstore Rekor for transparency anchoring.

    Architecture (S79 #5d, Path Beta dual signing):
    Rekor's hashedrekord/0.0.1 entry type is incompatible with Ed25519 sigs
    (EdDSA internally re-hashes; hashedrekord passes only the pre-computed
    hash to the verifier; see sigstore/rekor issue #851). To anchor a NOUS
    manifest signed with Ed25519, this function generates a per-submission
    ephemeral ECDSA-P-256 keypair, signs SHA-256 of the manifest canonical
    bytes with that ephemeral key, and submits the ECDSA signature plus
    ECDSA pubkey to Rekor. The original Ed25519 manifest signature is
    verified separately by the embedded dossier verifier; the Rekor anchor
    proves only "this SHA-256 was anchored at integrated_time T".

    Parameters manifest_signature_b64 and manifest_public_key_b64 are kept
    for API backward compatibility but are unused in the dual-signing path.
    They may be consumed by future leaf formats (DSSE / Rekor v2 in v6.x).

    # __nous_aetherproof_rekor_dual_signing_v1__
    """
    own_client = False
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(
                timeout_seconds, connect=REKOR_CONNECT_TIMEOUT_S
            ),
        )
        own_client = True

    try:
        rekor_pubkey_pem = _fetch_rekor_public_key_pem(client, base_url)

        submitter_sk = ec.generate_private_key(ec.SECP256R1())
        submitter_pk_pem = submitter_sk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        payload_sha256_hex = hashlib.sha256(
            manifest_canonical_bytes
        ).hexdigest()
        submitter_sig_der = submitter_sk.sign(
            manifest_canonical_bytes, ECDSA(hashes.SHA256())
        )
        submitter_sig_b64 = base64.b64encode(
            submitter_sig_der
        ).decode("ascii")

        body = _build_hashedrekord_body(
            payload_sha256_hex=payload_sha256_hex,
            submitter_signature_b64=submitter_sig_b64,
            submitter_public_key_pem=submitter_pk_pem,
        )
        try:
            response = client.post(
                base_url + REKOR_SUBMIT_PATH,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as exc:
            raise RekorUnavailable(
                f"failed to submit to rekor: {exc!r}"
            ) from exc

        if response.status_code not in (200, 201):
            detail = response.text[:512]
            raise RekorRejected(
                f"rekor submit returned HTTP {response.status_code}: {detail}"
            )

        try:
            envelope = response.json()
        except json.JSONDecodeError as exc:
            raise RekorRejected(
                f"rekor submit returned non-JSON: {exc!r}"
            ) from exc

        if not isinstance(envelope, dict) or len(envelope) != 1:
            raise RekorRejected(
                "rekor submit returned unexpected envelope shape "
                f"(keys={list(envelope) if isinstance(envelope, dict) else envelope})"
            )
        uuid = next(iter(envelope))
        entry = envelope[uuid]
        if not isinstance(entry, dict):
            raise RekorRejected(
                f"rekor entry under {uuid} is not a dict"
            )
        try:
            log_id = str(entry["logID"])
            log_index = int(entry["logIndex"])
            integrated_time = int(entry["integratedTime"])
            signed_entry_timestamp_b64 = str(
                entry["verification"]["signedEntryTimestamp"]
            )
            body_b64 = str(entry["body"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RekorRejected(
                f"rekor entry missing required fields: {exc!r}"
            ) from exc

        return RekorAnchor(
            provider="sigstore-rekor",
            log_id=log_id,
            log_index=log_index,
            integrated_time=integrated_time,
            signed_entry_timestamp_b64=signed_entry_timestamp_b64,
            body_b64=body_b64,
            rekor_public_key_pem=rekor_pubkey_pem,
        )
    finally:
        if own_client:
            client.close()


def _canonical_set_payload(anchor: RekorAnchor) -> bytes:
    payload = {
        "body": anchor.body_b64,
        "integratedTime": anchor.integrated_time,
        "logID": anchor.log_id,
        "logIndex": anchor.log_index,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load_ecdsa_p256_public_key(
    pem_text: str,
) -> ec.EllipticCurvePublicKey:
    pub = serialization.load_pem_public_key(pem_text.encode("utf-8"))
    if not isinstance(pub, ec.EllipticCurvePublicKey):
        raise ValueError("rekor pubkey is not an EC public key")
    if not isinstance(pub.curve, ec.SECP256R1):
        raise ValueError(
            f"rekor pubkey curve is not P-256: {pub.curve.name}"
        )
    return pub


class RekorVerifyDetail(BaseModel):
    """Granular result of verify_rekor_anchor_offline_detail().

    Each boolean reflects a single independent check:

      pubkey_in_allowlist  - anchor.rekor_public_key_pem matches the
                             known-keys allowlist (or the override
                             passed via known_rekor_public_keys=).
      set_signature_ok     - the Rekor signedEntryTimestamp
                             ECDSA-P-256 signature verifies over the
                             canonical SET payload
                             {body, integratedTime, logID, logIndex}.
      inclusion_body_ok    - the leaf body parses as
                             hashedrekord/0.0.1, its sha256 matches
                             the expected manifest canonical bytes,
                             and the submitter (ephemeral ECDSA-P-256
                             per submission) signature over the
                             manifest canonical bytes verifies.

    errors[] holds short diagnostic strings for any failed check.

    # __session81_rekor_verify_detail_v1__
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    pubkey_in_allowlist: bool
    set_signature_ok: bool
    inclusion_body_ok: bool
    errors: list[str] = Field(default_factory=list)


def verify_rekor_anchor_offline_detail(
    anchor: RekorAnchor,
    expected_manifest_canonical_bytes: bytes,
    expected_manifest_signature_b64: str,
    expected_manifest_public_key_b64: str,
    known_rekor_public_keys: Optional[list[str]] = None,
) -> RekorVerifyDetail:
    """Like verify_rekor_anchor_offline() but returns RekorVerifyDetail.

    Each of the three booleans is evaluated independently (no early
    exit). The AND of the three is byte-equivalent to the legacy bool
    return of verify_rekor_anchor_offline() (regression-asserted by
    tests/test_rekor_anchor.py).

    Parameters expected_manifest_signature_b64 and
    expected_manifest_public_key_b64 are kept for API parity with the
    legacy function; they are not consumed by the Path-beta dual
    signing verifier (the leaf carries its own per-submission
    ECDSA-P-256 pubkey + signature, verified directly against
    expected_manifest_canonical_bytes).

    # __session81_rekor_verify_detail_v1__
    """
    errors: list[str] = []

    if anchor.provider != "sigstore-rekor":
        return RekorVerifyDetail(
            pubkey_in_allowlist=False,
            set_signature_ok=False,
            inclusion_body_ok=False,
            errors=[f"unknown_provider: {anchor.provider}"],
        )

    allowlist = (
        KNOWN_REKOR_PUBLIC_KEYS
        if known_rekor_public_keys is None
        else known_rekor_public_keys
    )
    pubkey_in_allowlist = anchor.rekor_public_key_pem in allowlist
    if not pubkey_in_allowlist:
        errors.append("rekor_public_key_not_in_allowlist")

    set_signature_ok = False
    try:
        rekor_pub = _load_ecdsa_p256_public_key(
            anchor.rekor_public_key_pem
        )
        payload_bytes = _canonical_set_payload(anchor)
        signature_der = base64.b64decode(
            anchor.signed_entry_timestamp_b64, validate=True
        )
        rekor_pub.verify(
            signature_der, payload_bytes, ECDSA(hashes.SHA256())
        )
        set_signature_ok = True
    except InvalidSignature:
        errors.append("set_signature_invalid")
    except Exception as exc:
        errors.append(
            f"set_signature_check_error: {type(exc).__name__}"
        )

    inclusion_body_ok = False
    try:
        leaf_body_raw = base64.b64decode(anchor.body_b64, validate=True)
        leaf_body = json.loads(leaf_body_raw)
        if not isinstance(leaf_body, dict):
            raise ValueError("leaf body is not a dict")
        if leaf_body.get("kind") != "hashedrekord":
            raise ValueError(
                f"leaf kind != hashedrekord: {leaf_body.get('kind')!r}"
            )
        spec = leaf_body.get("spec")
        if not isinstance(spec, dict):
            raise ValueError("leaf spec missing or not a dict")

        expected_payload_sha256 = hashlib.sha256(
            expected_manifest_canonical_bytes
        ).hexdigest()
        hash_block = spec.get("data", {}).get("hash", {})
        if hash_block.get("algorithm") != "sha256":
            raise ValueError(
                "leaf hash algorithm != sha256: "
                f"{hash_block.get('algorithm')!r}"
            )
        if hash_block.get("value") != expected_payload_sha256:
            raise ValueError(
                "leaf hash does not match expected manifest sha256"
            )

        sig_block = spec.get("signature", {})
        submitter_sig_b64 = sig_block.get("content", "")
        submitter_pem_b64 = sig_block.get("publicKey", {}).get(
            "content", ""
        )
        if not submitter_sig_b64 or not submitter_pem_b64:
            raise ValueError(
                "leaf submitter signature or pubkey missing"
            )

        submitter_pem = base64.b64decode(
            submitter_pem_b64, validate=True
        ).decode("utf-8")
        submitter_pub = serialization.load_pem_public_key(
            submitter_pem.encode("utf-8")
        )
        if not isinstance(submitter_pub, ec.EllipticCurvePublicKey):
            raise ValueError("submitter pubkey is not EC")
        if not isinstance(submitter_pub.curve, ec.SECP256R1):
            raise ValueError("submitter pubkey curve is not P-256")

        submitter_sig_der = base64.b64decode(
            submitter_sig_b64, validate=True
        )
        submitter_pub.verify(
            submitter_sig_der,
            expected_manifest_canonical_bytes,
            ECDSA(hashes.SHA256()),
        )
        inclusion_body_ok = True
    except InvalidSignature:
        errors.append("submitter_signature_invalid")
    except Exception as exc:
        errors.append(
            f"inclusion_body_check_error: {type(exc).__name__}: {exc}"
        )

    return RekorVerifyDetail(
        pubkey_in_allowlist=pubkey_in_allowlist,
        set_signature_ok=set_signature_ok,
        inclusion_body_ok=inclusion_body_ok,
        errors=errors,
    )


def verify_rekor_anchor_offline(
    anchor: RekorAnchor,
    expected_manifest_canonical_bytes: bytes,
    expected_manifest_signature_b64: str,
    expected_manifest_public_key_b64: str,
    known_rekor_public_keys: Optional[list[str]] = None,
) -> bool:
    """Verify a RekorAnchor offline against expected manifest bytes.

    Returns True iff all three independent checks succeed:
        pubkey_in_allowlist AND set_signature_ok AND inclusion_body_ok.

    Refactored in S81 to delegate to
    verify_rekor_anchor_offline_detail(). Outcome is byte-equivalent
    to the S80 implementation; asserted in
    tests/test_rekor_anchor.py.

    # __session81_verify_dossier_endpoint_v1__
    """
    detail = verify_rekor_anchor_offline_detail(
        anchor=anchor,
        expected_manifest_canonical_bytes=(
            expected_manifest_canonical_bytes
        ),
        expected_manifest_signature_b64=(
            expected_manifest_signature_b64
        ),
        expected_manifest_public_key_b64=(
            expected_manifest_public_key_b64
        ),
        known_rekor_public_keys=known_rekor_public_keys,
    )
    return (
        detail.pubkey_in_allowlist
        and detail.set_signature_ok
        and detail.inclusion_body_ok
    )
