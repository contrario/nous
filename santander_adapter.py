"""Santander mech-gov DecisionResult evidence adapter (DARK, opt-in).

Consume-only integration. Parses a Santander mech-gov DecisionResult.to_dict()
JSONL line by KEY (never imports the mech-gov package) and emits a NOUS evidence
dossier over it: a signed, drop-when-None adapter manifest binding two digests
(upstream + projection) plus an E3 entropy leg, whose root commitment rides the
shipped envelope ledger under a producer-side domain tag (the single Witness
Network join) exactly as the closure surface does. An optional Rekor v2 anchor of
the entropy nonce rides the same shipped anchor primitives.

Honest boundary (inviolable):
  - EVIDENCES, never proves. The dossier evidences that a DecisionResult with this
    structure and this entropy nonce was produced. It does NOT prove the decision
    correct, fair, unbiased, single-shot, or non-gamed. "proves" is reserved for
    Z3/Farkas.
  - MONITOR, not guard. Consumes the record after the fact; enforces nothing on
    the mech-gov; blocks no decision.
  - HASHES, not raw. Free-text and metadata fields are carried as sha256 only; no
    special-category data enters the signed payload. Raw values are the auditor's
    out-of-band pack, sha-gated by the carried commitments.
  - REKOR ANCHOR: entropy nonce publicly logged and log-ordered (Rekor v2
    inclusion); observation time self-asserted (untrusted); inclusion
    independently verifiable offline. There is NO trusted time on this path (no
    RFC 3161 token is captured); manifest.timestamp_utc is NOUS-self-asserted.
    The Rekor leaf digest == sha256(nonce) == upstream e3_nonce_hash: the anchor
    binds the SAME nonce the E3 commit-reveal uses.
  - The name-to-key binding is OPERATOR-ASSERTED; NOUS runs no CA.

Composes over manifest (Ed25519 signer), envelope_ledger (commit surface),
closure_witness (the mirrored producer-tag pattern), rekor_anchor_v2 /
rekor_verify_v2 (the shipped Rekor v2 write / read path). Adds no new cryptography
and no new claim class. Writes nothing unless NOUS_SANTANDER_ADAPTER is set.
"""
# __s216_rekor_anchor_v1__
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


SANTANDER_ADAPTER_SCHEMA_VERSION: int = 1
SANTANDER_SOURCE_KIND: str = "santander/mech-gov/decision"
SANTANDER_PROJECTION_VERSION: str = "1"
# Producer-side envelope-ledger domain tag. Follows the shipped closure grammar
# nous/<name>/v1| (closure_witness.CLOSURE_COMMIT_TAG). Placeholder until a
# persistent-key signature ships (axiom 2: permanent once signed).
SANTANDER_COMMIT_TAG: bytes = b"nous/santander-decision/v1|"
_OPT_IN_ENV: str = "NOUS_SANTANDER_ADAPTER"

# The section-2.1 DecisionResult schema (20 keys), bound live S1. The left set is
# the arbiter of totality; a record missing any key is a typed refusal (axiom 5).
_VALUE_FIELDS: tuple[str, ...] = (
    "case_id",
    "regime",
    "decision",
    "gates_triggered",
    "cefl_candidates",
    "cefl_candidate_scores",
    "i6q_passed",
    "modification_proposed",
    "modification_accepted",
    "drift_budget_remaining",
)
# drop-when-None VALUE fields (regime-specific / optional); absent from the payload
# when None so unrelated dossiers stay byte-identical (axiom 2).
_VALUE_DROP_WHEN_NONE: frozenset[str] = frozenset({
    "cefl_candidates",
    "cefl_candidate_scores",
    "i6q_passed",
    "modification_proposed",
    "modification_accepted",
    "drift_budget_remaining",
})
# HASH fields: free text / lists carried as sha256 only (raw -> auditor pack).
_HASH_FIELDS: tuple[str, ...] = (
    "rationale",
    "pro_arguments",
    "con_arguments",
    "deferral_text",
    "conditions_text",
    "llm_raw_response",
)
# nullable HASH fields: drop-when-None (no commitment entry when absent).
_HASH_DROP_WHEN_NONE: frozenset[str] = frozenset({
    "deferral_text",
    "conditions_text",
})
# metadata is hashed as a REMAINDER: the E3 commit subfields are lifted into the
# entropy leg (clear), everything else (incl. PII-derived counts) is sha256'd.
_METADATA_FIELD: str = "metadata"
_METADATA_LEG_KEYS: tuple[str, ...] = ("e3_nonce_hash", "e3_verified")
# DROP fields: execution telemetry, non-structural. Excluded from the signed
# projection; still covered by upstream_digest over the full record.
_DROP_FIELDS: tuple[str, ...] = ("processing_time_ms", "tokens_used")
# Entropy temporal leg source.
_ENTROPY_NONCE_FIELD: str = "entropy_nonce"

_EXPECTED_KEYS: frozenset[str] = frozenset(
    _VALUE_FIELDS + _HASH_FIELDS + _DROP_FIELDS
    + (_METADATA_FIELD, _ENTROPY_NONCE_FIELD)
)


class SantanderAdapterError(RuntimeError):
    """Raised cause-first on a schema, projection, or verification violation."""


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_decision_jsonl(line: str) -> dict[str, Any]:
    """Consume-only parse of a DecisionResult.to_dict() JSONL line.

    Parses by key; never imports the mech-gov package. A malformed line or a
    record missing any expected section-2.1 key is a typed refusal (axiom 5),
    with zero output.
    """
    if not isinstance(line, str):
        raise SantanderAdapterError(
            "decision record must be a JSONL string, got: " + repr(type(line))
        )
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SantanderAdapterError(
            "decision record is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(record, dict):
        raise SantanderAdapterError(
            "decision record is not a JSON object, got: " + repr(type(record))
        )
    missing = sorted(_EXPECTED_KEYS - set(record.keys()))
    if missing:
        raise SantanderAdapterError(
            "decision record is missing expected section-2.1 keys: "
            + repr(missing) + " (refuse over guess)"
        )
    return record


def _hash_field(value: Any) -> str:
    return _sha256_hex(_canonical_bytes(value))


def project_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    """Total map DecisionResult record -> canonical decision-structural payload.

    VALUE fields carried in clear (drop-when-None where regime-specific); HASH
    fields carried as sha256 commitments; metadata carried as a remainder hash
    (E3 subfields lifted to the leg); DROP fields excluded (covered by
    upstream_digest); entropy handled by build_entropy_leg. Contains NO raw
    free-text or metadata plaintext.
    """
    for key in _EXPECTED_KEYS:
        if key not in record:
            raise SantanderAdapterError(
                "record missing expected key during projection: " + repr(key)
            )
    payload: dict[str, Any] = {}
    for name in _VALUE_FIELDS:
        val = record[name]
        if val is None and name in _VALUE_DROP_WHEN_NONE:
            continue
        payload[name] = val

    commitments: dict[str, str] = {}
    for name in _HASH_FIELDS:
        val = record[name]
        if val is None and name in _HASH_DROP_WHEN_NONE:
            continue
        commitments[name + "_sha256"] = _hash_field(val)

    metadata = record[_METADATA_FIELD]
    if not isinstance(metadata, dict):
        raise SantanderAdapterError(
            "metadata must be an object, got: " + repr(type(metadata))
        )
    remainder = {
        k: v for k, v in metadata.items() if k not in _METADATA_LEG_KEYS
    }
    commitments["metadata_sha256"] = _hash_field(remainder)

    payload["commitments"] = commitments
    return payload


def upstream_digest(jsonl_line: str) -> str:
    """sha256 of the exact to_dict() JSONL line as consumed (provenance leg)."""
    return _sha256_hex(jsonl_line.encode("utf-8"))


def projection_digest(payload: Mapping[str, Any]) -> str:
    """sha256 of the canonical projected payload (offline-verifiable identity)."""
    return _sha256_hex(_canonical_bytes(payload))


@dataclass(frozen=True)
class EntropyLeg:
    """The E3 commit-reveal binding NOUS signs. nonce = revealed N,
    nonce_hash = the upstream commit H(N), e3_verified = upstream reveal flag.
    Evidences that N existed and was committed. Proves nothing about the
    decision being single-shot or unbiased. When anchored (Rekor v2), the leaf
    digest == sha256(nonce) == nonce_hash: public, ordered, offline-checkable
    logging of the exact committed nonce -- NOT a trusted time.
    """
    nonce: str
    nonce_hash: str
    e3_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "e3_verified": self.e3_verified,
            "nonce": self.nonce,
            "nonce_hash": self.nonce_hash,
        }


def build_entropy_leg(record: Mapping[str, Any]) -> Optional[EntropyLeg]:
    """Build the entropy leg, or None when the record carries no E3 nonce
    (drop-when-None; R1/text-only records have no entropy). Refuses if the
    revealed nonce does not match the carried commit H(N)."""
    nonce = record.get(_ENTROPY_NONCE_FIELD)
    if nonce is None:
        return None
    if not isinstance(nonce, str):
        raise SantanderAdapterError(
            "entropy_nonce must be a string, got: " + repr(type(nonce))
        )
    metadata = record.get(_METADATA_FIELD)
    if not isinstance(metadata, dict):
        raise SantanderAdapterError(
            "entropy_nonce present but metadata is not an object"
        )
    nonce_hash = metadata.get("e3_nonce_hash")
    if not isinstance(nonce_hash, str) or len(nonce_hash) != 64:
        raise SantanderAdapterError(
            "entropy leg requires metadata.e3_nonce_hash (64-hex), got: "
            + repr(nonce_hash)
        )
    if _sha256_hex(nonce.encode("ascii")) != nonce_hash:
        raise SantanderAdapterError(
            "E3 commit-reveal broken: sha256(entropy_nonce) != e3_nonce_hash "
            "(refuse over guess)"
        )
    e3_verified = bool(metadata.get("e3_verified", False))
    return EntropyLeg(nonce=nonce, nonce_hash=nonce_hash, e3_verified=e3_verified)


@dataclass(frozen=True)
class SantanderDossierManifest:
    """The signed adapter manifest. Frozen dataclass, sorted-keys compact JSON
    canonical serialization, drop-when-None (NOT Pydantic, NOT the SMT Manifest).
    """
    nous_version: str
    upstream_digest: str
    projection_digest: str
    timestamp_utc: str
    entropy_leg: Optional[EntropyLeg] = None
    schema_version: int = SANTANDER_ADAPTER_SCHEMA_VERSION
    source_kind: str = SANTANDER_SOURCE_KIND
    projection_version: str = SANTANDER_PROJECTION_VERSION

    def canonical_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "nous_version": self.nous_version,
            "projection_digest": self.projection_digest,
            "projection_version": self.projection_version,
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "timestamp_utc": self.timestamp_utc,
            "upstream_digest": self.upstream_digest,
        }
        if self.entropy_leg is not None:
            d["entropy_leg"] = self.entropy_leg.to_dict()
        return d

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.canonical_dict())

    def root_digest(self) -> str:
        return _sha256_hex(self.canonical_bytes())


def _public_body(manifest: SantanderDossierManifest) -> bytes:
    """Minimal non-sensitive witnessed identity: {root, source_kind}. root
    transitively binds both digests and the entropy leg via the signed manifest.
    Mirrors closure_witness.public_body minimalism."""
    doc = {
        "root": manifest.root_digest(),
        "source_kind": manifest.source_kind,
    }
    return _canonical_bytes(doc)


def dossier_commitment(manifest: SantanderDossierManifest) -> bytes:
    """32-byte envelope-ledger commitment: sha256(TAG || public_body). Appends to
    the shipped EnvelopeLog under the producer tag, riding the single witness
    join (mirrors closure_witness.closure_commitment)."""
    return hashlib.sha256(SANTANDER_COMMIT_TAG + _public_body(manifest)).digest()


def _public_key_b64(public_key: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def anchor_entropy_nonce(
    record: Mapping[str, Any],
    *,
    client: "Optional[Any]" = None,
    _test_anchor: "Optional[Any]" = None,
) -> dict[str, Any]:
    """Anchor the entropy nonce N to Rekor v2 and return the detached anchor
    block (RekorAnchorV2.to_manifest_block()).

    IRREVERSIBLE (real Rekor write) unless _test_anchor is supplied. Anchors
    N.encode("ascii") -- the same bytes the E3 commit-reveal hashes -- so the
    resulting leaf digest == sha256(N) == metadata.e3_nonce_hash. Reuses the
    shipped anchor_manifest_to_rekor_v2 primitive; adds no new cryptography.
    Refuses (typed, zero output) when the record carries no E3 nonce.
    """
    leg = build_entropy_leg(record)
    if leg is None:
        raise SantanderAdapterError(
            "cannot anchor: record carries no entropy_nonce (E3 leg absent)"
        )
    if _test_anchor is not None:
        block = _test_anchor.to_manifest_block()
        return dict(block)
    from rekor_anchor_v2 import anchor_manifest_to_rekor_v2

    anchor = anchor_manifest_to_rekor_v2(
        leg.nonce.encode("ascii"), client=client
    )
    return dict(anchor.to_manifest_block())


def build_dossier(
    record: Mapping[str, Any],
    jsonl_line: str,
    private_key: Ed25519PrivateKey,
    timestamp_utc: str,
    nous_version: str,
    rekor_anchor: "Optional[Mapping[str, Any]]" = None,
) -> dict[str, Any]:
    """Build the full signed dossier document over a DecisionResult.

    timestamp_utc is the honestly-varying part supplied by the caller; every
    other output byte is a deterministic function of the record. rekor_anchor,
    when supplied, is attached under transparency_log AFTER signing -- the
    canonical body excludes transparency_log, so the signed body is byte-
    identical whether or not the dossier is anchored (drop-when-None).
    """
    payload = project_decision(record)
    manifest = SantanderDossierManifest(
        nous_version=nous_version,
        upstream_digest=upstream_digest(jsonl_line),
        projection_digest=projection_digest(payload),
        timestamp_utc=timestamp_utc,
        entropy_leg=build_entropy_leg(record),
    )
    signature = private_key.sign(manifest.canonical_bytes())
    public_key = private_key.public_key()
    doc: dict[str, Any] = manifest.canonical_dict()
    doc["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": _public_key_b64(public_key),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    if rekor_anchor is not None:
        doc["transparency_log"] = dict(rekor_anchor)
    return {
        "manifest_doc": doc,
        "payload": payload,
        "commitment": dossier_commitment(manifest).hex(),
    }


@dataclass(frozen=True)
class SantanderVerdict:
    """Total offline verdict. Every leg is a boolean; the verifier never raises
    on a well-formed other-kind, un-anchored, or tampered dossier -- it returns
    flags (verdict, not exception), mirroring closure_witness.ClosureWitnessVerdict.
    rekor_ok is vacuously True when the dossier carries no transparency_log."""
    kind_ok: bool
    signature_ok: bool
    projection_ok: bool
    entropy_ok: bool
    rekor_ok: bool

    @property
    def ok(self) -> bool:
        return (
            self.kind_ok
            and self.signature_ok
            and self.projection_ok
            and self.entropy_ok
            and self.rekor_ok
        )


def verify_santander_dossier(
    manifest_doc: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    trusted_log_keys: "Optional[Mapping[str, Any]]" = None,
) -> SantanderVerdict:
    """Verify a dossier offline with cryptography (Ed25519 + ECDSA) + sha256.
    TOTAL: a well-formed other-kind returns kind_ok=False (no raise); any tamper
    flags the affected leg False; the Rekor leg never raises (returns rekor_ok
    False on any malformation). rekor_ok is vacuously True when no
    transparency_log is present (drop-when-None)."""
    kind_ok = manifest_doc.get("source_kind") == SANTANDER_SOURCE_KIND

    signature_ok = False
    try:
        sig_block = manifest_doc["signature"]
        pub_raw = base64.b64decode(sig_block["public_key_b64"])
        sig = base64.b64decode(sig_block["signature_b64"])
        body = {
            k: v for k, v in manifest_doc.items()
            if k not in ("signature", "transparency_log")
        }
        body_bytes = _canonical_bytes(body)
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig, body_bytes)
        signature_ok = True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        signature_ok = False

    projection_ok = False
    try:
        projection_ok = (
            projection_digest(payload) == manifest_doc.get("projection_digest")
        )
    except (ValueError, TypeError):
        projection_ok = False

    entropy_ok = True
    leg = manifest_doc.get("entropy_leg")
    if leg is not None:
        try:
            entropy_ok = (
                isinstance(leg, dict)
                and _sha256_hex(str(leg["nonce"]).encode("ascii"))
                == leg["nonce_hash"]
            )
        except (KeyError, ValueError, TypeError):
            entropy_ok = False

    rekor_ok = True
    tlog = manifest_doc.get("transparency_log")
    if tlog is not None:
        rekor_ok = False
        try:
            leg_nonce = None
            if isinstance(leg, dict):
                leg_nonce = leg.get("nonce")
            if isinstance(leg_nonce, str) and leg_nonce:
                from rekor_verify_v2 import (
                    load_trusted_log_keys,
                    verify_rekor_v2_anchor,
                )

                keys = (
                    load_trusted_log_keys()
                    if trusted_log_keys is None
                    else dict(trusted_log_keys)
                )
                detail = verify_rekor_v2_anchor(
                    manifest_body_bytes=leg_nonce.encode("ascii"),
                    block=tlog,
                    trusted_log_keys=keys,
                )
                rekor_ok = bool(detail.ok)
        except Exception:
            rekor_ok = False

    return SantanderVerdict(
        kind_ok=kind_ok,
        signature_ok=signature_ok,
        projection_ok=projection_ok,
        entropy_ok=entropy_ok,
        rekor_ok=rekor_ok,
    )


_STANDALONE_VERIFIER: str = r'''#!/usr/bin/env python3
"""Offline verification of a NOUS Santander mech-gov decision dossier.

Usage: python3 verify_offline.py
Exit:  0 = verified, 1 = FAIL (tamper / wrong kind / broken E3 / bad anchor),
       2 = env.

Checks, fail-closed, in order:
  1. Ed25519 signature over the canonical manifest body bytes.
  2. source_kind == "santander/mech-gov/decision" (refuse any other kind).
  3. projection_digest == sha256(canonical payload.json).
  4. entropy leg (when present): sha256(nonce) == nonce_hash (E3 commit-reveal).
  5. Rekor v2 anchor (when transparency_log present): the entropy nonce is
     publicly logged and log-ordered -- leaf digest == sha256(nonce) ==
     e3_nonce_hash; leaf ECDSA over the nonce; C2SP checkpoint signed by the
     pinned Sigstore Rekor v2 log key; RFC 6962 inclusion under the cosigned
     root. cryptography + stdlib only.

BOUNDARY: a verified dossier EVIDENCES that this DecisionResult was produced,
and (when anchored) that the exact entropy nonce is publicly logged and log-
ordered. It does NOT establish a trusted time -- no RFC 3161 token is captured;
the observation time is manifest.timestamp_utc, NOUS-self-asserted (untrusted).
It does NOT prove the decision correct, fair, unbiased, single-shot, or
non-gamed. Requires: cryptography (Ed25519 + ECDSA-P256 only).
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_KIND = "santander/mech-gov/decision"

_REKOR_V2_LOG_ORIGIN = "log2025-1.rekor.sigstore.dev"
_REKOR_V2_LOG_KEY_B64 = "t8rlp1knGwjfbcXAYPYAkn0XiLz1x8O4t0YkEhie244="

_LEAF_HASH_PREFIX = b"\x00"
_NODE_HASH_PREFIX = b"\x01"


def _cb(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fail(msg):
    print("FAIL " + msg, file=sys.stderr)
    return 1


def _hleaf(b):
    return hashlib.sha256(_LEAF_HASH_PREFIX + b).digest()


def _hchild(l, r):
    return hashlib.sha256(_NODE_HASH_PREFIX + l + r).digest()


def _decomp(index, size):
    inner = (index ^ (size - 1)).bit_length()
    border = bin(index >> inner).count("1")
    return inner, border


def _chain_inner(seed, proof, index):
    acc = seed
    for i, h in enumerate(proof):
        if (index >> i) & 1 == 0:
            acc = _hchild(acc, h)
        else:
            acc = _hchild(h, acc)
    return acc


def _chain_border_right(seed, proof):
    acc = seed
    for h in proof:
        acc = _hchild(h, acc)
    return acc


def _verify_inclusion(body, index, size, proof, root):
    if not (0 <= index < size):
        raise ValueError("log_index out of range for tree_size")
    inner, border = _decomp(index, size)
    if len(proof) != inner + border:
        raise ValueError("inclusion proof wrong size")
    leaf_hash = _hleaf(body)
    mid = _chain_inner(leaf_hash, proof[:inner], index)
    calc = _chain_border_right(mid, proof[inner:])
    if calc != root:
        raise ValueError("inclusion root mismatch")
    return leaf_hash


def _parse_checkpoint(note):
    head, sep, tail = note.partition("\n\n")
    if not sep:
        raise ValueError("checkpoint missing text/signature separator")
    body = (head + "\n").encode("utf-8")
    lines = head.split("\n")
    if len(lines) < 3:
        raise ValueError("checkpoint body has too few lines")
    tree_size = int(lines[1])
    root_hash = base64.b64decode(lines[2])
    sigs = []
    for line in tail.split("\n"):
        if not line.strip():
            continue
        parts = line.split(" ")
        if len(parts) < 3 or parts[0] != "\u2014":
            continue
        blob = base64.b64decode(parts[2])
        sigs.append((parts[1], blob[:4], blob[4:]))
    if not sigs:
        raise ValueError("checkpoint carries no parseable signatures")
    return lines[0], tree_size, root_hash, body, sigs


def _verify_checkpoint_sig(body, sigs, log_key):
    from cryptography.exceptions import InvalidSignature
    for _name, _hint, sig in sigs:
        try:
            log_key.verify(sig, body)
            return True
        except InvalidSignature:
            continue
    return False


def _parse_v2_leaf(body):
    inner = body["spec"]["hashedRekordV002"]
    data = inner["data"]
    if data.get("algorithm") != "SHA2_256":
        raise ValueError("leaf hash algorithm is not SHA2_256")
    digest_hex = base64.b64decode(data["digest"], validate=True).hex()
    sig_der = base64.b64decode(inner["signature"]["content"], validate=True)
    pk_der = base64.b64decode(
        inner["signature"]["verifier"]["publicKey"]["rawBytes"], validate=True
    )
    return digest_hex, pk_der, sig_der


def _verify_rekor_anchor(tlog, nonce, e3_nonce_hash):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        load_der_public_key,
    )
    from cryptography.exceptions import InvalidSignature

    nonce_bytes = nonce.encode("ascii")
    body_b64 = tlog["body_b64"]
    body_bytes = base64.b64decode(body_b64, validate=True)
    leaf = json.loads(body_bytes)
    digest_hex, pk_der, sig_der = _parse_v2_leaf(leaf)

    want = hashlib.sha256(nonce_bytes).hexdigest()
    if digest_hex != want:
        return _fail(
            "Rekor leaf digest " + digest_hex[:16] + "... != sha256(nonce) "
            + want[:16] + "... (anchor names a different nonce)"
        )
    if e3_nonce_hash is not None and digest_hex != e3_nonce_hash:
        return _fail(
            "Rekor leaf digest != e3_nonce_hash (anchor and E3 commit disagree)"
        )

    leaf_pub = load_der_public_key(pk_der)
    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):
        return _fail("Rekor leaf public key is not an EC key")
    if not isinstance(leaf_pub.curve, ec.SECP256R1):
        return _fail("Rekor leaf public key curve is not P-256")
    try:
        leaf_pub.verify(sig_der, nonce_bytes, ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return _fail("Rekor leaf ECDSA signature does NOT verify over the nonce")

    origin, tree_size, root_hash, cp_body, sigs = _parse_checkpoint(
        tlog["checkpoint_envelope"]
    )
    if origin != _REKOR_V2_LOG_ORIGIN:
        return _fail(
            "checkpoint origin " + repr(origin) + " != pinned "
            + repr(_REKOR_V2_LOG_ORIGIN)
        )
    log_key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(_REKOR_V2_LOG_KEY_B64, validate=True)
    )
    if not _verify_checkpoint_sig(cp_body, sigs, log_key):
        return _fail(
            "checkpoint signature does NOT verify against the pinned Rekor v2 "
            "log key"
        )

    proof = [
        base64.b64decode(h, validate=True)
        for h in tlog["inclusion_proof_hashes"]
    ]
    try:
        _verify_inclusion(
            body_bytes, int(tlog["log_index"]), tree_size, proof, root_hash
        )
    except ValueError as exc:
        return _fail("Rekor inclusion proof does NOT verify: " + str(exc))

    print(
        "OK   Rekor v2 anchor: entropy nonce publicly logged and log-ordered "
        "(leaf digest == sha256(nonce) == e3_nonce_hash; log_index "
        + str(tlog["log_index"]) + ", tree_size " + str(tree_size)
        + ", origin " + origin + ")"
    )
    print(
        "     TEMPORAL: NO trusted time. Inclusion evidences public append-only "
        "logging + ordering; observation time is manifest.timestamp_utc, "
        "NOUS-self-asserted (untrusted). Inclusion independently verifiable "
        "offline."
    )
    return 0


def main():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        print("ERROR: pip install 'cryptography>=42'", file=sys.stderr)
        return 2

    mpath = ROOT / "manifest.json"
    ppath = ROOT / "payload.json"
    if not mpath.is_file() or not ppath.is_file():
        return _fail("manifest.json and payload.json required in " + str(ROOT))
    doc = json.loads(mpath.read_text(encoding="utf-8"))
    payload = json.loads(ppath.read_text(encoding="utf-8"))

    sig_block = doc.get("signature") or {}
    pub_b64 = sig_block.get("public_key_b64", "")
    sig_b64 = sig_block.get("signature_b64", "")
    if not pub_b64 or not sig_b64:
        return _fail("manifest signature block incomplete")
    body = {k: v for k, v in doc.items()
            if k not in ("signature", "transparency_log")}
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
        pub.verify(base64.b64decode(sig_b64), _cb(body))
    except InvalidSignature:
        return _fail("Ed25519 signature does NOT verify")
    except Exception as e:
        return _fail("signature verification error: " + str(e))
    print("OK   Ed25519 signature verified")

    if doc.get("source_kind") != SOURCE_KIND:
        return _fail("source_kind is " + repr(doc.get("source_kind"))
                     + ", not " + repr(SOURCE_KIND) + " (wrong claim kind)")
    print("OK   source_kind " + SOURCE_KIND)

    pd = hashlib.sha256(_cb(payload)).hexdigest()
    if pd != doc.get("projection_digest"):
        return _fail("projection_digest mismatch: payload=" + pd[:16]
                     + "... manifest=" + str(doc.get("projection_digest"))[:16]
                     + "... (payload tampered or substituted)")
    print("OK   projection_digest matches payload (" + pd[:16] + "...)")

    leg = doc.get("entropy_leg")
    e3_nonce_hash = None
    nonce = None
    if leg is not None:
        nonce = str(leg.get("nonce", ""))
        e3_nonce_hash = leg.get("nonce_hash", "")
        if hashlib.sha256(nonce.encode("ascii")).hexdigest() != e3_nonce_hash:
            return _fail("E3 commit-reveal broken: sha256(nonce) != nonce_hash")
        print("OK   E3 commit-reveal: sha256(nonce) == nonce_hash")

    tlog = doc.get("transparency_log")
    if tlog is not None:
        if not isinstance(leg, dict) or not nonce:
            return _fail(
                "transparency_log present but no entropy nonce to anchor "
                "(malformed dossier)"
            )
        rc = _verify_rekor_anchor(tlog, nonce, e3_nonce_hash)
        if rc != 0:
            return rc

    print()
    print("VERDICT: EVIDENCED (Ed25519 manifest + decision-structural payload"
          + ("; E3 entropy leg" if leg is not None else "")
          + ("; Rekor v2 anchor" if tlog is not None else "") + ")")
    print("result: decision-evidenced")
    print("boundary: evidences this DecisionResult was produced"
          + ("; entropy nonce publicly logged and log-ordered (Rekor v2 "
             "inclusion), observation time self-asserted (untrusted), "
             "inclusion independently verifiable offline"
             if tlog is not None else "")
          + "; NOT that the decision is correct, fair, unbiased, or "
          "single-shot; evidences-not-proves")
    print("  source_kind:       " + str(doc.get("source_kind")))
    print("  projection_version:" + str(doc.get("projection_version")))
    print("  upstream_digest:   " + str(doc.get("upstream_digest"))[:16] + "...")
    print("  timestamp:         " + str(doc.get("timestamp_utc"))
          + " (NOUS-self-asserted, untrusted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def emit_dossier_to_dir(
    record: Mapping[str, Any],
    jsonl_line: str,
    private_key: Ed25519PrivateKey,
    timestamp_utc: str,
    nous_version: str,
    out_dir: Path,
    rekor_anchor: "Optional[Mapping[str, Any]]" = None,
) -> list[str]:
    """DARK write path. Refuses unless NOUS_SANTANDER_ADAPTER is set; writes
    manifest.json, payload.json, and a self-contained verify_offline.py. When
    rekor_anchor is supplied it is carried under transparency_log (the anchor is
    a separate, explicit, irreversible ceremony -- never performed here). Raw
    sensitive values are NOT written here -- they belong to the out-of-band
    auditor pack, sha-gated by the carried commitments."""
    if not os.environ.get(_OPT_IN_ENV):
        raise SantanderAdapterError(
            "emit refused: opt-in env " + _OPT_IN_ENV + " is not set "
            "(the adapter writes nothing by default)"
        )
    built = build_dossier(
        record, jsonl_line, private_key, timestamp_utc, nous_version,
        rekor_anchor=rekor_anchor,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    (out_dir / "manifest.json").write_text(
        json.dumps(built["manifest_doc"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append("manifest.json")
    (out_dir / "payload.json").write_text(
        json.dumps(built["payload"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append("payload.json")
    (out_dir / "verify_offline.py").write_text(
        _STANDALONE_VERIFIER, encoding="utf-8"
    )
    written.append("verify_offline.py")
    return written
