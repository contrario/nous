"""Guardrails AI ValidationOutcome evidence adapter (DARK, opt-in).

Consume-only integration. Parses a Guardrails AI ValidationOutcome.to_dict()
by KEY (never imports the guardrails package) and emits a NOUS evidence dossier
over it: a signed, drop-when-None adapter manifest binding two digests
(upstream + projection), with an optional Rekor v2 anchor of the canonical
projected payload. Mirrors the shipped santander_adapter.py structure; the only
per-adapter differences are the projection map, the source_kind, the producer
tag, and the ABSENCE of an entropy-tie leg (a ValidationOutcome carries no
nonce, so the Rekor leaf digest == projection_digest directly).

Honest boundary (inviolable):
  - EVIDENCES, never proves. The dossier evidences that a ValidationOutcome
    with this structure was produced. It does NOT prove the validation correct,
    the validators sound, or the output safe. "proves" is reserved for Z3/Farkas.
  - MONITOR, not guard. Consumes the record after the fact; enforces nothing on
    the Guard; blocks no output.
  - HASHES, not raw. raw_llm_output, validated_output, and per-validator
    error_message can carry model output or user PII; they are carried as
    sha256 only. Raw values are the auditor's out-of-band pack.
  - REKOR ANCHOR (when present): the canonical projected payload is publicly
    logged and log-ordered (Rekor v2 inclusion); observation time self-asserted
    (untrusted). The leaf digest == sha256(canonical payload) == projection_digest.
  - The name-to-key binding is OPERATOR-ASSERTED; NOUS runs no CA.

Composes over the same shipped primitives santander_adapter uses (Ed25519
signer via cryptography, rekor_anchor_v2 / rekor_verify_v2). Adds no new
cryptography and no new claim class. Writes nothing unless
NOUS_GUARDRAILS_ADAPTER is set. VALUE-ADD is real ONLY because a Guardrails
ValidationOutcome is UNSIGNED.
"""
# __s219_guardrails_adapter_v1__
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


GUARDRAILS_ADAPTER_SCHEMA_VERSION: int = 1
GUARDRAILS_SOURCE_KIND: str = "guardrails-ai/validation/decision"
GUARDRAILS_PROJECTION_VERSION: str = "guardrails-validation/1"
# Producer-side envelope-ledger domain tag. FROZEN at S221 by a local genesis
# persistent-key signature (axiom 2: permanent once signed); the dedicated key
# guardrails-adapter.key binds these exact bytes. Present for parity with the
# santander commitment derivation; NOT part of the signed manifest.
# __s221_guardrails_tag_frozen_v1__
GUARDRAILS_COMMIT_TAG: bytes = b"nous/guardrails-validation/v1|"
_OPT_IN_ENV: str = "NOUS_GUARDRAILS_ADAPTER"

# Consume-only projection expects a dict with validator_results normalized to
# [{name, passed, on_fail?, error_message?}]. The left set is the totality
# arbiter; a record missing any expected key is a typed refusal (axiom 5).
_EXPECTED_KEYS: frozenset[str] = frozenset({
    "validation_passed",
    "validator_results",
})


class GuardrailsAdapterError(RuntimeError):
    """Raised cause-first on a schema, projection, or verification violation."""


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(data: Any) -> str:
    if data is None:
        return _sha256_hex("")
    if isinstance(data, (dict, list)):
        data = _canonical_bytes(data)
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise GuardrailsAdapterError(
            "missing expected key: " + repr(key) + " (refuse over guess)"
        )
    return record[key]


def project_guardrails(record: Mapping[str, Any]) -> dict[str, Any]:
    """Total map ValidationOutcome record -> canonical decision-structural
    payload. Decision + per-validator verdicts carried in clear; free-text
    fields carried as sha256 only; drop-when-None so unrelated dossiers stay
    byte-identical. Contains NO raw model output or error plaintext."""
    for key in _EXPECTED_KEYS:
        _require(record, key)
    passed = bool(record["validation_passed"])
    vres = record["validator_results"]
    if not isinstance(vres, list):
        raise GuardrailsAdapterError("validator_results must be a list")
    projection: dict[str, Any] = {
        "schema": "nous/guardrails-validation/v1",
        "projection_version": GUARDRAILS_PROJECTION_VERSION,
        "decision": "pass" if passed else "fail",
        "validators": [
            {
                "name": str(_require(v, "name")),
                "passed": bool(_require(v, "passed")),
                "on_fail": v.get("on_fail"),
                "error_sha256": (
                    _sha256_hex(v["error_message"])
                    if v.get("error_message")
                    else None
                ),
            }
            for v in vres
        ],
        "call_id": record.get("call_id"),
        "raw_output_sha256": _sha256_hex(record.get("raw_llm_output")),
        "validated_output_sha256": _sha256_hex(record.get("validated_output")),
    }
    return _drop_none(projection)


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def upstream_digest(record: Mapping[str, Any]) -> str:
    """sha256 of the full canonical record (provenance leg; recomputable only
    from the raw record, not from the dossier alone)."""
    return _sha256_hex(_canonical_bytes(record))


def projection_digest(payload: Mapping[str, Any]) -> str:
    """sha256 of the canonical projected payload (offline-verifiable identity)."""
    return _sha256_hex(_canonical_bytes(payload))


@dataclass(frozen=True)
class GuardrailsDossierManifest:
    """The signed adapter manifest. Frozen dataclass, sorted-keys compact JSON
    canonical serialization, drop-when-None (NOT Pydantic, NOT the SMT Manifest).
    No entropy leg: a ValidationOutcome carries no nonce."""
    nous_version: str
    upstream_digest: str
    projection_digest: str
    timestamp_utc: str
    schema_version: int = GUARDRAILS_ADAPTER_SCHEMA_VERSION
    source_kind: str = GUARDRAILS_SOURCE_KIND
    projection_version: str = GUARDRAILS_PROJECTION_VERSION

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "nous_version": self.nous_version,
            "projection_digest": self.projection_digest,
            "projection_version": self.projection_version,
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "timestamp_utc": self.timestamp_utc,
            "upstream_digest": self.upstream_digest,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.canonical_dict())

    def root_digest(self) -> str:
        return _sha256_hex(self.canonical_bytes())


def _public_body(manifest: GuardrailsDossierManifest) -> bytes:
    doc = {
        "root": manifest.root_digest(),
        "source_kind": manifest.source_kind,
    }
    return _canonical_bytes(doc)


def dossier_commitment(manifest: GuardrailsDossierManifest) -> bytes:
    """32-byte envelope-ledger commitment: sha256(TAG || public_body). Mirrors
    santander_adapter.dossier_commitment; returned for parity but the adapter
    performs no envelope write itself."""
    return hashlib.sha256(
        GUARDRAILS_COMMIT_TAG + _public_body(manifest)
    ).digest()


def _public_key_b64(public_key: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def anchor_projection(
    payload: Mapping[str, Any],
    *,
    client: "Optional[Any]" = None,
    _test_anchor: "Optional[Any]" = None,
) -> dict[str, Any]:
    """Anchor the canonical projected payload to Rekor v2 and return the
    detached anchor block. IRREVERSIBLE (real Rekor write) unless _test_anchor
    is supplied. Anchors _canonical_bytes(payload) -- the same bytes the
    projection_digest hashes -- so the leaf digest == projection_digest. Reuses
    the shipped anchor_manifest_to_rekor_v2 primitive; adds no new cryptography."""
    if _test_anchor is not None:
        return dict(_test_anchor.to_manifest_block())
    from rekor_anchor_v2 import anchor_manifest_to_rekor_v2

    anchor = anchor_manifest_to_rekor_v2(
        _canonical_bytes(payload), client=client
    )
    return dict(anchor.to_manifest_block())


def build_dossier(
    record: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
    timestamp_utc: str,
    nous_version: str,
    rekor_anchor: "Optional[Mapping[str, Any]]" = None,
) -> dict[str, Any]:
    """Build the full signed dossier document over a ValidationOutcome record.

    timestamp_utc is the honestly-varying part supplied by the caller; every
    other output byte is a deterministic function of the record. rekor_anchor,
    when supplied, is attached under transparency_log AFTER signing -- the
    canonical body excludes transparency_log, so the signed body is byte-
    identical whether or not the dossier is anchored (drop-when-None)."""
    payload = project_guardrails(record)
    manifest = GuardrailsDossierManifest(
        nous_version=nous_version,
        upstream_digest=upstream_digest(record),
        projection_digest=projection_digest(payload),
        timestamp_utc=timestamp_utc,
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
class GuardrailsVerdict:
    """Total offline verdict. Every leg is a boolean; the verifier never raises
    on a well-formed other-kind, un-anchored, or tampered dossier -- it returns
    flags. rekor_ok is vacuously True when the dossier carries no
    transparency_log. No entropy leg (santander's entropy_ok is deleted here)."""
    kind_ok: bool
    signature_ok: bool
    projection_ok: bool
    rekor_ok: bool

    @property
    def ok(self) -> bool:
        return (
            self.kind_ok
            and self.signature_ok
            and self.projection_ok
            and self.rekor_ok
        )


def verify_guardrails_dossier(
    manifest_doc: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    trusted_log_keys: "Optional[Mapping[str, Any]]" = None,
) -> GuardrailsVerdict:
    """Verify a dossier offline with cryptography (Ed25519 + ECDSA) + sha256.
    TOTAL: a well-formed other-kind returns kind_ok=False (no raise); any tamper
    flags the affected leg False; the Rekor leg never raises. rekor_ok is
    vacuously True when no transparency_log is present (drop-when-None)."""
    kind_ok = manifest_doc.get("source_kind") == GUARDRAILS_SOURCE_KIND

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

    rekor_ok = True
    tlog = manifest_doc.get("transparency_log")
    if tlog is not None:
        rekor_ok = False
        try:
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
                manifest_body_bytes=_canonical_bytes(payload),
                block=tlog,
                trusted_log_keys=keys,
            )
            rekor_ok = bool(detail.ok)
        except Exception:
            rekor_ok = False

    return GuardrailsVerdict(
        kind_ok=kind_ok,
        signature_ok=signature_ok,
        projection_ok=projection_ok,
        rekor_ok=rekor_ok,
    )


_STANDALONE_VERIFIER: str = r'''#!/usr/bin/env python3
"""Offline verification of a NOUS Guardrails AI validation dossier.

Usage: python3 verify_offline.py
Exit:  0 = verified, 1 = FAIL, 2 = env.

Checks, fail-closed, in order:
  1. Ed25519 signature over the canonical manifest body bytes.
  2. source_kind == "guardrails-ai/validation/decision".
  3. projection_digest == sha256(canonical payload.json).
  4. Rekor v2 anchor (when transparency_log present): the canonical projected
     payload is publicly logged and log-ordered -- leaf digest == sha256(payload)
     == projection_digest; leaf ECDSA over the payload bytes; C2SP checkpoint
     signed by the pinned Rekor v2 log key; RFC 6962 inclusion under the
     cosigned root. cryptography + stdlib only.

BOUNDARY: a verified dossier EVIDENCES that this ValidationOutcome was produced,
and (when anchored) that the exact projected payload is publicly logged and
log-ordered. It does NOT establish a trusted time. It does NOT prove the
validation correct or the output safe. evidences-not-proves.
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_KIND = "guardrails-ai/validation/decision"

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


def _verify_rekor_anchor(tlog, payload_bytes, projection_digest_hex):
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

    body_b64 = tlog["body_b64"]
    body_bytes = base64.b64decode(body_b64, validate=True)
    leaf = json.loads(body_bytes)
    digest_hex, pk_der, sig_der = _parse_v2_leaf(leaf)

    want = hashlib.sha256(payload_bytes).hexdigest()
    if digest_hex != want:
        return _fail(
            "Rekor leaf digest " + digest_hex[:16] + "... != sha256(payload) "
            + want[:16] + "... (anchor names different bytes)"
        )
    if digest_hex != projection_digest_hex:
        return _fail(
            "Rekor leaf digest != projection_digest (anchor and manifest "
            "disagree)"
        )

    leaf_pub = load_der_public_key(pk_der)
    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):
        return _fail("Rekor leaf public key is not an EC key")
    if not isinstance(leaf_pub.curve, ec.SECP256R1):
        return _fail("Rekor leaf public key curve is not P-256")
    try:
        leaf_pub.verify(sig_der, payload_bytes, ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return _fail(
            "Rekor leaf ECDSA signature does NOT verify over the payload"
        )

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
        "OK   Rekor v2 anchor: projected payload publicly logged and "
        "log-ordered (leaf digest == sha256(payload) == projection_digest; "
        "log_index " + str(tlog["log_index"]) + ", tree_size "
        + str(tree_size) + ", origin " + origin + ")"
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

    tlog = doc.get("transparency_log")
    if tlog is not None:
        payload_bytes = _cb(payload)
        rc = _verify_rekor_anchor(tlog, payload_bytes, pd)
        if rc != 0:
            return rc

    print()
    print("VERDICT: EVIDENCED (Ed25519 manifest + decision-structural payload"
          + ("; Rekor v2 anchor" if tlog is not None else "") + ")")
    print("result: validation-evidenced")
    print("boundary: evidences this ValidationOutcome was produced"
          + ("; projected payload publicly logged and log-ordered (Rekor v2 "
             "inclusion), observation time self-asserted (untrusted), "
             "inclusion independently verifiable offline"
             if tlog is not None else "")
          + "; NOT that the validation is correct or the output safe; "
          "evidences-not-proves")
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
    private_key: Ed25519PrivateKey,
    timestamp_utc: str,
    nous_version: str,
    out_dir: Path,
    rekor_anchor: "Optional[Mapping[str, Any]]" = None,
) -> list[str]:
    """DARK write path. Refuses unless NOUS_GUARDRAILS_ADAPTER is set; writes
    manifest.json, payload.json, and a self-contained verify_offline.py. When
    rekor_anchor is supplied it is carried under transparency_log (the anchor is
    a separate, explicit, irreversible ceremony -- never performed here). Raw
    sensitive values are NOT written here -- they belong to the out-of-band
    auditor pack, sha-gated by the carried commitments."""
    if not os.environ.get(_OPT_IN_ENV):
        raise GuardrailsAdapterError(
            "emit refused: opt-in env " + _OPT_IN_ENV + " is not set "
            "(the adapter writes nothing by default)"
        )
    built = build_dossier(
        record, private_key, timestamp_utc, nous_version,
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
