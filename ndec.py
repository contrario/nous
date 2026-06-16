"""NDEC -- portable proof-carrying AI-decision attestation envelope.
# __s147_u1_ndec_module_v1__

Wraps an existing, byte-identical NOUS dossier in a standard DSSE v1 envelope
over an in-toto v1 Statement, with a NOUS-defined proof-carrying predicate
(predicateType https://nous-lang.org/attestation/decision/v1). The envelope is
interoperable with DSSE / in-toto / cosign tooling; the predicate commits, by
sha256 digest, to the dossier's own proof artifacts (SMT cost spec, Farkas /
SMT coverage), which the NOUS verifier re-derives rather than trusts.

This module models the in-toto Statement and DSSE envelope as plain dicts
serialized with deterministic sorted-keys compact JSON, NOT as Pydantic models.
Documented relaxation of the Pydantic-strict default: DSSE requires the signed
body to be byte-preserved and verified as an opaque blob; routing it through a
Pydantic model risks re-serialization drift that would break byte-identity of
the signed payload. Determinism comes from json.dumps(sort_keys, compact).

The DSSE signature is a SECOND, independent Ed25519 signature over PAE bytes,
distinct from the inner manifest's Ed25519 signature over canonical JSON. The
inner dossier and its signature are never modified by this module.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

NDEC_STATEMENT_TYPE: str = "https://in-toto.io/Statement/v1"
NDEC_PAYLOAD_TYPE: str = "application/vnd.in-toto+json"
NDEC_PREDICATE_TYPE: str = "https://nous-lang.org/attestation/decision/v1"
NDEC_MEDIA_TYPE: str = "application/vnd.nous.decision+zip"
DSSE_VERSION: bytes = b"DSSEv1"

DECISION_SCOPE: dict = {
    "proves": [
        "cost_envelope_within_declared_cap",
        "coverage_of_declared_blocking_net",
    ],
    "evidences": [
        "artifact_provenance",
        "issuer_non_tampering",
        "token_provenance_if_tee_attested",
    ],
    "not_claimed": [
        "decision_correctness",
        "legal_sufficiency",
        "regulatory_compliance_conferred",
        "enclave_internal_honesty",
        "monitors_are_guards",
    ],
}


class NdecError(ValueError):
    """Malformed envelope, statement, or signature; fail-closed."""


def pae(payload_type: str, body: bytes) -> bytes:
    pt: bytes = payload_type.encode("utf-8")
    return (
        DSSE_VERSION
        + b" " + str(len(pt)).encode("ascii") + b" " + pt
        + b" " + str(len(body)).encode("ascii") + b" " + body
    )


def manifest_canonical_sha256(manifest: dict) -> str:
    body: dict = {
        k: v
        for k, v in manifest.items()
        if k not in ("signature", "transparency_log")
    }
    body_bytes: bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(body_bytes).hexdigest()


def keyid_for(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def build_decision_predicate(
    *,
    manifest: dict,
    artifacts: dict,
    signer_public_key_b64: str,
    attestation: Optional[dict] = None,
    transparency: Optional[dict] = None,
) -> dict:
    if "nous_version" not in manifest or "world_name" not in manifest:
        raise NdecError(
            "manifest missing required field nous_version or world_name"
        )
    if "verdict" not in manifest:
        raise NdecError("manifest missing required field verdict")
    if not isinstance(artifacts, dict) or not artifacts:
        raise NdecError("artifacts digest map is empty or not a dict")
    predicate: dict = {
        "nous_version": manifest["nous_version"],
        "world_name": manifest["world_name"],
        "verdict": manifest["verdict"],
        "artifacts": dict(artifacts),
        "signer_public_key_b64": signer_public_key_b64,
        "scope": DECISION_SCOPE,
    }
    for optional_key in (
        "source_kind",
        "evidence_kind",
        "cost_binding",
        "cost_cap_usd",
    ):
        value = manifest.get(optional_key)
        if value is not None:
            predicate[optional_key] = value
    if attestation is not None:
        predicate["attestation"] = attestation
    if transparency is not None:
        predicate["transparency"] = transparency
    return predicate


def build_statement(*, manifest: dict, predicate: dict) -> dict:
    return {
        "_type": NDEC_STATEMENT_TYPE,
        "subject": [
            {
                "name": str(manifest["world_name"]),
                "digest": {"sha256": manifest_canonical_sha256(manifest)},
            }
        ],
        "predicateType": NDEC_PREDICATE_TYPE,
        "predicate": predicate,
    }


def serialize_body(statement: dict) -> bytes:
    return json.dumps(
        statement, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sign_envelope(*, statement: dict, private_key: Ed25519PrivateKey) -> dict:
    body: bytes = serialize_body(statement)
    signature: bytes = private_key.sign(pae(NDEC_PAYLOAD_TYPE, body))
    public_key: Ed25519PublicKey = private_key.public_key()
    return {
        "payload": base64.b64encode(body).decode("ascii"),
        "payloadType": NDEC_PAYLOAD_TYPE,
        "signatures": [
            {
                "keyid": keyid_for(public_key),
                "sig": base64.b64encode(signature).decode("ascii"),
            }
        ],
    }


def verify_envelope(*, envelope: dict, public_key: Ed25519PublicKey) -> dict:
    if not isinstance(envelope, dict):
        raise NdecError("envelope is not a JSON object")
    payload_type = envelope.get("payloadType")
    if payload_type != NDEC_PAYLOAD_TYPE:
        raise NdecError("unsupported payloadType: " + repr(payload_type))
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str):
        raise NdecError("envelope payload is missing or not a string")
    if not isinstance(signatures, list) or not signatures:
        raise NdecError("envelope signatures missing or empty")
    try:
        body: bytes = base64.b64decode(payload_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise NdecError("payload base64 decode failed: " + str(exc))
    sig_entry = signatures[0]
    if not isinstance(sig_entry, dict) or not isinstance(
        sig_entry.get("sig"), str
    ):
        raise NdecError("signature entry malformed")
    try:
        signature: bytes = base64.b64decode(sig_entry["sig"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise NdecError("signature base64 decode failed: " + str(exc))
    try:
        public_key.verify(signature, pae(NDEC_PAYLOAD_TYPE, body))
    except InvalidSignature:
        raise NdecError("DSSE Ed25519 signature does not verify")
    try:
        statement = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdecError("verified body is not valid JSON: " + str(exc))
    if not isinstance(statement, dict):
        raise NdecError("verified statement is not a JSON object")
    if statement.get("_type") != NDEC_STATEMENT_TYPE:
        raise NdecError(
            "statement _type is not in-toto v1: "
            + repr(statement.get("_type"))
        )
    if statement.get("predicateType") != NDEC_PREDICATE_TYPE:
        raise NdecError(
            "predicateType is not the NOUS decision type: "
            + repr(statement.get("predicateType"))
        )
    return statement


# __s147_u2_ndec_container_v1__
import dataclasses
import io
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

VERIFY_NDEC_PY: str = base64.b64decode(
    "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJPZmZsaW5lIHZlcmlmaWNhdGlvbiBvZiBhIE5PVVMgLm5kZWMgZGVjaXNpb24gYXR0ZXN0YXRpb24uCgpVc2FnZTogcHl0aG9uMyB2ZXJpZnlfbmRlYy5weQpFeGl0OiAgMCA9IFBBU1MsIDEgPSBGQUlMLCAyID0gZW52aXJvbm1lbnQgZXJyb3IuClJlcXVpcmVzOiBjcnlwdG9ncmFwaHkgKG5vIE5PVVMgaW5zdGFsbCBuZWVkZWQpLgoKV2hhdCB0aGlzIHZlcmlmaWVzLCBmYWlsLWNsb3NlZCwgaW4gb3JkZXI6CiAgMS4gRFNTRSBlbnZlbG9wZTogRWQyNTUxOSBvdmVyIFBBRShwYXlsb2FkVHlwZSwgYm9keSk7IHBheWxvYWRUeXBlIGFuZAogICAgIHByZWRpY2F0ZVR5cGUgbXVzdCBiZSB0aGUgTk9VUyBkZWNpc2lvbiB0eXBlczsga2V5aWQgPT0gc2hhMjU2KHB1YmtleSkuCiAgMi4gU3ViamVjdCBiaW5kaW5nOiBzaGEyNTYgb2YgdGhlIGNhbm9uaWNhbCBkb3NzaWVyL21hbmlmZXN0Lmpzb24gYm9keQogICAgIChzaWduYXR1cmUgKyB0cmFuc3BhcmVuY3lfbG9nIHN0cmlwcGVkKSA9PSBzdGF0ZW1lbnQgc3ViamVjdCBkaWdlc3QuCiAgMy4gQXJ0aWZhY3QgYmluZGluZzogZXZlcnkgZGlnZXN0IGluIHRoZSBzaWduZWQgcHJlZGljYXRlIC0tIElOQ0xVRElORyB0aGUKICAgICBkb3NzaWVyIHZlcmlmaWVyIGl0c2VsZiAodmVyaWZ5X29mZmxpbmVfc2hhMjU2KSAtLSBtYXRjaGVzIHRoZSBjYXJyaWVkCiAgICAgZmlsZSBieXRlcy4KICA0LiBJbm5lciBwcm9vZjogcnVucyBkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5IGFzIGEgc3VicHJvY2VzcyBhbmQgbWFwcyBpdHMKICAgICBleGl0IGNvZGUgKDAgUEFTUyAvIDEgRkFJTCAvIDIgZW52aXJvbm1lbnQtbGltaXRlZCkuCgpUcnVzdCBub3RlOiB0aGUgc2lnbmVyIHB1YmxpYyBrZXkgaXMgcmVhZCBmcm9tIHRoZSBzaWduZWQgcHJlZGljYXRlCihzaWduZXItYXNzZXJ0ZWQpLiBUaGlzIGNvbmZpcm1zIHRoZSBidW5kbGUgaXMgaW50ZXJuYWxseSBjb25zaXN0ZW50IGFuZCB0aGUKY2FycmllZCBkb3NzaWVyIHZlcmlmaWVyIGlzIHRoZSBvbmUgdGhlIHNpZ25lciBjb21taXR0ZWQgdG8sIHRoZW4gcnVucyBpdC4gSWYKeW91IGRvIG5vdCB0cnVzdCB0aGUgcHJvdmVuYW5jZSBvZiB0aGlzIC5uZGVjLCBpbnN0YWxsIG5vdXMtbGFuZyBhbmQgcnVuCmBub3VzIHZlcmlmeWAsIG9yIGNvbmZpcm0gdmVyaWZ5X29mZmxpbmVfc2hhMjU2IGFnYWluc3QgdGhlIHB1Ymxpc2hlZCBOT1VTCnZlcmlmaWVyIHJlZ2lzdHJ5LiBUaGUgZW52ZWxvcGUgaXMgaW50ZXJvcGVyYWJsZTsgdGhlIGd1YXJhbnRlZSBpczogUFJPVkVTIHRoZQpjb3N0L2NvdmVyYWdlIGVudmVsb3BlICh6MyAvIEZhcmthcywgdmlhIHRoZSBpbm5lciB2ZXJpZmllciksIEVWSURFTkNFUwpwcm92ZW5hbmNlIGFuZCBpc3N1ZXIgbm9uLXRhbXBlcmluZyAoRWQyNTUxOSkuIEl0IGRvZXMgTk9UIHByb3ZlIGRlY2lzaW9uCmNvcnJlY3RuZXNzLCBsZWdhbCBzdWZmaWNpZW5jeSwgb3IgcmVndWxhdG9yeSBjb21wbGlhbmNlLgoiIiIKZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGJhc2U2NAppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgc3VicHJvY2VzcwppbXBvcnQgc3lzCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAoKUk9PVCA9IFBhdGgoX19maWxlX18pLnBhcmVudAoKU1RBVEVNRU5UX1RZUEUgPSAiaHR0cHM6Ly9pbi10b3RvLmlvL1N0YXRlbWVudC92MSIKUEFZTE9BRF9UWVBFID0gImFwcGxpY2F0aW9uL3ZuZC5pbi10b3RvK2pzb24iClBSRURJQ0FURV9UWVBFID0gImh0dHBzOi8vbm91cy1sYW5nLm9yZy9hdHRlc3RhdGlvbi9kZWNpc2lvbi92MSIKCkFSVElGQUNUX0ZJTEVTID0gewogICAgIm1hbmlmZXN0X3NoYTI1NiI6ICJtYW5pZmVzdC5qc29uIiwKICAgICJzb3VyY2Vfc2hhMjU2IjogInNvdXJjZS5ub3VzIiwKICAgICJwcmljaW5nX3NoYTI1NiI6ICJwcmljaW5nLnRvbWwiLAogICAgImNvdmVyYWdlX3NtdDJfc2hhMjU2IjogImNvdmVyYWdlLnNtdDIiLAogICAgImNvdmVyYWdlX2Zhcmthc19zaGEyNTYiOiAiY292ZXJhZ2UuZmFya2FzLmpzb24iLAogICAgImFubmV4X2l2X21hcF9zaGEyNTYiOiAiYW5uZXhfaXZfbWFwLmpzb24iLAogICAgInZlcmlmeV9vZmZsaW5lX3NoYTI1NiI6ICJ2ZXJpZnlfb2ZmbGluZS5weSIsCn0KCgpkZWYgX2ZhaWwobXNnKToKICAgIHByaW50KCJGQUlMOiAiICsgbXNnLCBmaWxlPXN5cy5zdGRlcnIpCiAgICByZXR1cm4gMQoKCmRlZiBfcGFlKHBheWxvYWRfdHlwZSwgYm9keSk6CiAgICBwdCA9IHBheWxvYWRfdHlwZS5lbmNvZGUoInV0Zi04IikKICAgIHJldHVybiAoCiAgICAgICAgYiJEU1NFdjEiCiAgICAgICAgKyBiIiAiICsgc3RyKGxlbihwdCkpLmVuY29kZSgiYXNjaWkiKSArIGIiICIgKyBwdAogICAgICAgICsgYiIgIiArIHN0cihsZW4oYm9keSkpLmVuY29kZSgiYXNjaWkiKSArIGIiICIgKyBib2R5CiAgICApCgoKZGVmIF9jYW5vbmljYWxfYm9keV9ieXRlcyhtYW5pZmVzdCk6CiAgICBib2R5ID0gewogICAgICAgIGs6IHYKICAgICAgICBmb3IgaywgdiBpbiBtYW5pZmVzdC5pdGVtcygpCiAgICAgICAgaWYgayBub3QgaW4gKCJzaWduYXR1cmUiLCAidHJhbnNwYXJlbmN5X2xvZyIpCiAgICB9CiAgICByZXR1cm4ganNvbi5kdW1wcygKICAgICAgICBib2R5LCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oIiwiLCAiOiIpCiAgICApLmVuY29kZSgidXRmLTgiKQoKCmRlZiBtYWluKCk6CiAgICB0cnk6CiAgICAgICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMuYXN5bW1ldHJpYy5lZDI1NTE5IGltcG9ydCAoCiAgICAgICAgICAgIEVkMjU1MTlQdWJsaWNLZXksCiAgICAgICAgKQogICAgICAgIGZyb20gY3J5cHRvZ3JhcGh5LmV4Y2VwdGlvbnMgaW1wb3J0IEludmFsaWRTaWduYXR1cmUKICAgIGV4Y2VwdCBJbXBvcnRFcnJvcjoKICAgICAgICBwcmludCgKICAgICAgICAgICAgIkVSUk9SOiBjcnlwdG9ncmFwaHkgbGlicmFyeSByZXF1aXJlZC5cbiIKICAgICAgICAgICAgIkluc3RhbGw6IHBpcCBpbnN0YWxsICdjcnlwdG9ncmFwaHk+PTQyJyIsCiAgICAgICAgICAgIGZpbGU9c3lzLnN0ZGVyciwKICAgICAgICApCiAgICAgICAgcmV0dXJuIDIKCiAgICBlbnZfcGF0aCA9IFJPT1QgLyAiYXR0ZXN0YXRpb24uaW50b3RvLmpzb24iCiAgICBpZiBub3QgZW52X3BhdGguaXNfZmlsZSgpOgogICAgICAgIHJldHVybiBfZmFpbCgiYXR0ZXN0YXRpb24uaW50b3RvLmpzb24gbm90IGZvdW5kIGluICIgKyBzdHIoUk9PVCkpCiAgICB0cnk6CiAgICAgICAgZW52ZWxvcGUgPSBqc29uLmxvYWRzKGVudl9wYXRoLnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKSkKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoImF0dGVzdGF0aW9uLmludG90by5qc29uIHBhcnNlIGVycm9yOiAiICsgc3RyKGUpKQogICAgaWYgbm90IGlzaW5zdGFuY2UoZW52ZWxvcGUsIGRpY3QpOgogICAgICAgIHJldHVybiBfZmFpbCgiZW52ZWxvcGUgaXMgbm90IGEgSlNPTiBvYmplY3QiKQogICAgaWYgZW52ZWxvcGUuZ2V0KCJwYXlsb2FkVHlwZSIpICE9IFBBWUxPQURfVFlQRToKICAgICAgICByZXR1cm4gX2ZhaWwoCiAgICAgICAgICAgICJ1bnN1cHBvcnRlZCBwYXlsb2FkVHlwZTogIiArIHJlcHIoZW52ZWxvcGUuZ2V0KCJwYXlsb2FkVHlwZSIpKQogICAgICAgICkKICAgIHBheWxvYWRfYjY0ID0gZW52ZWxvcGUuZ2V0KCJwYXlsb2FkIikKICAgIHNpZ25hdHVyZXMgPSBlbnZlbG9wZS5nZXQoInNpZ25hdHVyZXMiKQogICAgaWYgbm90IGlzaW5zdGFuY2UocGF5bG9hZF9iNjQsIHN0cik6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJlbnZlbG9wZSBwYXlsb2FkIG1pc3NpbmciKQogICAgaWYgbm90IGlzaW5zdGFuY2Uoc2lnbmF0dXJlcywgbGlzdCkgb3Igbm90IHNpZ25hdHVyZXM6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJlbnZlbG9wZSBzaWduYXR1cmVzIG1pc3NpbmciKQogICAgdHJ5OgogICAgICAgIGJvZHkgPSBiYXNlNjQuYjY0ZGVjb2RlKHBheWxvYWRfYjY0LCB2YWxpZGF0ZT1UcnVlKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgicGF5bG9hZCBiYXNlNjQgZGVjb2RlIGZhaWxlZDogIiArIHN0cihlKSkKICAgIHNpZ19lbnRyeSA9IHNpZ25hdHVyZXNbMF0KICAgIGlmIG5vdCBpc2luc3RhbmNlKHNpZ19lbnRyeSwgZGljdCkgb3Igbm90IGlzaW5zdGFuY2UoCiAgICAgICAgc2lnX2VudHJ5LmdldCgic2lnIiksIHN0cgogICAgKToKICAgICAgICByZXR1cm4gX2ZhaWwoInNpZ25hdHVyZSBlbnRyeSBtYWxmb3JtZWQiKQogICAgdHJ5OgogICAgICAgIHNpZ25hdHVyZSA9IGJhc2U2NC5iNjRkZWNvZGUoc2lnX2VudHJ5WyJzaWciXSwgdmFsaWRhdGU9VHJ1ZSkKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoInNpZ25hdHVyZSBiYXNlNjQgZGVjb2RlIGZhaWxlZDogIiArIHN0cihlKSkKCiAgICB0cnk6CiAgICAgICAgc3RhdGVtZW50ID0ganNvbi5sb2Fkcyhib2R5LmRlY29kZSgidXRmLTgiKSkKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoInZlcmlmaWVkIGJvZHkgaXMgbm90IHZhbGlkIEpTT046ICIgKyBzdHIoZSkpCiAgICBpZiBub3QgaXNpbnN0YW5jZShzdGF0ZW1lbnQsIGRpY3QpOgogICAgICAgIHJldHVybiBfZmFpbCgic3RhdGVtZW50IGlzIG5vdCBhIEpTT04gb2JqZWN0IikKICAgIGlmIHN0YXRlbWVudC5nZXQoIl90eXBlIikgIT0gU1RBVEVNRU5UX1RZUEU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJzdGF0ZW1lbnQgX3R5cGUgaXMgbm90IGluLXRvdG8gdjEiKQogICAgaWYgc3RhdGVtZW50LmdldCgicHJlZGljYXRlVHlwZSIpICE9IFBSRURJQ0FURV9UWVBFOgogICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgInByZWRpY2F0ZVR5cGUgaXMgbm90IHRoZSBOT1VTIGRlY2lzaW9uIHR5cGU6ICIKICAgICAgICAgICAgKyByZXByKHN0YXRlbWVudC5nZXQoInByZWRpY2F0ZVR5cGUiKSkKICAgICAgICApCiAgICBwcmVkaWNhdGUgPSBzdGF0ZW1lbnQuZ2V0KCJwcmVkaWNhdGUiKQogICAgaWYgbm90IGlzaW5zdGFuY2UocHJlZGljYXRlLCBkaWN0KToKICAgICAgICByZXR1cm4gX2ZhaWwoInByZWRpY2F0ZSBpcyBub3QgYSBKU09OIG9iamVjdCIpCiAgICBzaWduZXJfYjY0ID0gcHJlZGljYXRlLmdldCgic2lnbmVyX3B1YmxpY19rZXlfYjY0IiwgIiIpCiAgICBpZiBub3Qgc2lnbmVyX2I2NDoKICAgICAgICByZXR1cm4gX2ZhaWwoInByZWRpY2F0ZSBjYXJyaWVzIG5vIHNpZ25lcl9wdWJsaWNfa2V5X2I2NCIpCiAgICB0cnk6CiAgICAgICAgcHViX3JhdyA9IGJhc2U2NC5iNjRkZWNvZGUoc2lnbmVyX2I2NCwgdmFsaWRhdGU9VHJ1ZSkKICAgICAgICBwdWJfa2V5ID0gRWQyNTUxOVB1YmxpY0tleS5mcm9tX3B1YmxpY19ieXRlcyhwdWJfcmF3KQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgic2lnbmVyIHB1YmxpYyBrZXkgZGVjb2RlIGVycm9yOiAiICsgc3RyKGUpKQoKICAgIGV4cGVjdGVkX2tleWlkID0gaGFzaGxpYi5zaGEyNTYocHViX3JhdykuaGV4ZGlnZXN0KCkKICAgIGlmIHNpZ19lbnRyeS5nZXQoImtleWlkIikgIT0gZXhwZWN0ZWRfa2V5aWQ6CiAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAia2V5aWQgZG9lcyBub3QgbWF0Y2ggc2hhMjU2IG9mIHRoZSBwcmVkaWNhdGUgc2lnbmVyIGtleSIKICAgICAgICApCiAgICB0cnk6CiAgICAgICAgcHViX2tleS52ZXJpZnkoc2lnbmF0dXJlLCBfcGFlKFBBWUxPQURfVFlQRSwgYm9keSkpCiAgICBleGNlcHQgSW52YWxpZFNpZ25hdHVyZToKICAgICAgICByZXR1cm4gX2ZhaWwoIkRTU0UgRWQyNTUxOSBzaWduYXR1cmUgZG9lcyBub3QgdmVyaWZ5IikKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoIkRTU0UgdmVyaWZpY2F0aW9uIGVycm9yOiAiICsgc3RyKGUpKQogICAgcHJpbnQoIk9LICAgRFNTRSBlbnZlbG9wZSBFZDI1NTE5IHNpZ25hdHVyZSB2ZXJpZmllZCIpCgogICAgc3ViamVjdCA9IHN0YXRlbWVudC5nZXQoInN1YmplY3QiKQogICAgaWYgbm90IGlzaW5zdGFuY2Uoc3ViamVjdCwgbGlzdCkgb3IgbGVuKHN1YmplY3QpICE9IDE6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJzdGF0ZW1lbnQgc3ViamVjdCBtdXN0IGJlIGV4YWN0bHkgb25lIGVudHJ5IikKICAgIHN1YmpfZGlnZXN0ID0gc3ViamVjdFswXS5nZXQoImRpZ2VzdCIsIHt9KS5nZXQoInNoYTI1NiIsICIiKQoKICAgIG1hbl9wYXRoID0gUk9PVCAvICJkb3NzaWVyIiAvICJtYW5pZmVzdC5qc29uIgogICAgaWYgbm90IG1hbl9wYXRoLmlzX2ZpbGUoKToKICAgICAgICByZXR1cm4gX2ZhaWwoImRvc3NpZXIvbWFuaWZlc3QuanNvbiBub3QgZm91bmQiKQogICAgdHJ5OgogICAgICAgIG1hbmlmZXN0ID0ganNvbi5sb2FkcyhtYW5fcGF0aC5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04IikpCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL21hbmlmZXN0Lmpzb24gcGFyc2UgZXJyb3I6ICIgKyBzdHIoZSkpCiAgICByZWNvbXB1dGVkID0gaGFzaGxpYi5zaGEyNTYoX2Nhbm9uaWNhbF9ib2R5X2J5dGVzKG1hbmlmZXN0KSkuaGV4ZGlnZXN0KCkKICAgIGlmIHJlY29tcHV0ZWQgIT0gc3Vial9kaWdlc3Q6CiAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAic3ViamVjdCBkaWdlc3QgZG9lcyBub3QgYmluZCBkb3NzaWVyL21hbmlmZXN0Lmpzb246ICIKICAgICAgICAgICAgInN1YmplY3Q9IiArIHN0cihzdWJqX2RpZ2VzdClbOjE2XSArICIuLi4gcmVjb21wdXRlZD0iCiAgICAgICAgICAgICsgcmVjb21wdXRlZFs6MTZdICsgIi4uLiIKICAgICAgICApCiAgICBwcmludCgiT0sgICBzdWJqZWN0IGRpZ2VzdCBiaW5kcyBkb3NzaWVyL21hbmlmZXN0Lmpzb24iKQoKICAgIGFydGlmYWN0cyA9IHByZWRpY2F0ZS5nZXQoImFydGlmYWN0cyIpCiAgICBpZiBub3QgaXNpbnN0YW5jZShhcnRpZmFjdHMsIGRpY3QpIG9yIG5vdCBhcnRpZmFjdHM6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJwcmVkaWNhdGUgYXJ0aWZhY3RzIG1pc3NpbmciKQogICAgY2hlY2tlZCA9IDAKICAgIGZvciBrZXksIGZuYW1lIGluIEFSVElGQUNUX0ZJTEVTLml0ZW1zKCk6CiAgICAgICAgZGVjbGFyZWQgPSBhcnRpZmFjdHMuZ2V0KGtleSkKICAgICAgICBpZiBkZWNsYXJlZCBpcyBOb25lOgogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGZwYXRoID0gUk9PVCAvICJkb3NzaWVyIiAvIGZuYW1lCiAgICAgICAgaWYgbm90IGZwYXRoLmlzX2ZpbGUoKToKICAgICAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAgICAgInByZWRpY2F0ZSBkZWNsYXJlcyAiICsga2V5ICsgIiBidXQgZG9zc2llci8iICsgZm5hbWUKICAgICAgICAgICAgICAgICsgIiBpcyBtaXNzaW5nIgogICAgICAgICAgICApCiAgICAgICAgYWN0dWFsID0gaGFzaGxpYi5zaGEyNTYoZnBhdGgucmVhZF9ieXRlcygpKS5oZXhkaWdlc3QoKQogICAgICAgIGlmIGFjdHVhbCAhPSBkZWNsYXJlZDoKICAgICAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAgICAgImFydGlmYWN0IGRpZ2VzdCBtaXNtYXRjaCBmb3IgZG9zc2llci8iICsgZm5hbWUKICAgICAgICAgICAgICAgICsgIjogcHJlZGljYXRlPSIgKyBkZWNsYXJlZFs6MTZdICsgIi4uLiBmaWxlPSIKICAgICAgICAgICAgICAgICsgYWN0dWFsWzoxNl0gKyAiLi4uIgogICAgICAgICAgICApCiAgICAgICAgY2hlY2tlZCArPSAxCiAgICBpZiAidmVyaWZ5X29mZmxpbmVfc2hhMjU2IiBub3QgaW4gYXJ0aWZhY3RzOgogICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgInByZWRpY2F0ZSBkb2VzIG5vdCBwaW4gdmVyaWZ5X29mZmxpbmVfc2hhMjU2OyB0aGUgY2FycmllZCAiCiAgICAgICAgICAgICJkb3NzaWVyIHZlcmlmaWVyIGlzIG5vdCBib3VuZCBieSB0aGUgc2lnbmF0dXJlIChyZWZ1c2VkKSIKICAgICAgICApCiAgICBwcmludCgKICAgICAgICAiT0sgICAiICsgc3RyKGNoZWNrZWQpICsgIiBjYXJyaWVkIGFydGlmYWN0KHMpIG1hdGNoIHRoZSBzaWduZWQgIgogICAgICAgICJwcmVkaWNhdGUgKGluY2x1ZGluZyB0aGUgZG9zc2llciB2ZXJpZmllcikiCiAgICApCgogICAgdmVyaWZpZXIgPSBST09UIC8gImRvc3NpZXIiIC8gInZlcmlmeV9vZmZsaW5lLnB5IgogICAgaWYgbm90IHZlcmlmaWVyLmlzX2ZpbGUoKToKICAgICAgICByZXR1cm4gX2ZhaWwoImRvc3NpZXIvdmVyaWZ5X29mZmxpbmUucHkgbm90IGZvdW5kIikKICAgIHRyeToKICAgICAgICBwcm9jID0gc3VicHJvY2Vzcy5ydW4oCiAgICAgICAgICAgIFtzeXMuZXhlY3V0YWJsZSwgc3RyKHZlcmlmaWVyKV0sCiAgICAgICAgICAgIGN3ZD1zdHIoUk9PVCAvICJkb3NzaWVyIiksCiAgICAgICAgICAgIGNhcHR1cmVfb3V0cHV0PVRydWUsCiAgICAgICAgICAgIHRleHQ9VHJ1ZSwKICAgICAgICAgICAgdGltZW91dD0xMjAsCiAgICAgICAgKQogICAgZXhjZXB0IHN1YnByb2Nlc3MuVGltZW91dEV4cGlyZWQ6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5IHRpbWVkIG91dCIpCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5IGludm9jYXRpb24gZXJyb3I6ICIgKyBzdHIoZSkpCiAgICBzeXMuc3Rkb3V0LndyaXRlKHByb2Muc3Rkb3V0KQogICAgaWYgcHJvYy5zdGRlcnI6CiAgICAgICAgc3lzLnN0ZGVyci53cml0ZShwcm9jLnN0ZGVycikKICAgIHJjID0gcHJvYy5yZXR1cm5jb2RlCiAgICBpZiByYyA9PSAyOgogICAgICAgIHByaW50KAogICAgICAgICAgICAiTk9URSBpbm5lciBwcm9vZiBlbnZpcm9ubWVudC1saW1pdGVkIChleGl0IDIpOyBjcnlwdG8gKyAiCiAgICAgICAgICAgICJiaW5kaW5nIGdhdGVzIGFib3ZlIFBBU1NFRCwgaW5uZXIgc2VtYW50aWMgbm90IGZ1bGx5ICIKICAgICAgICAgICAgInJlLWRlcml2ZWQgaW4gdGhpcyBlbnZpcm9ubWVudCIKICAgICAgICApCiAgICAgICAgcmV0dXJuIDIKICAgIGlmIHJjICE9IDA6CiAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAiaW5uZXIgZG9zc2llciB2ZXJpZmllciByZXR1cm5lZCAiICsgc3RyKHJjKQogICAgICAgICAgICArICIgKHRoZSBwcm9vZiBhcnRpZmFjdHMgZG8gbm90IHZlcmlmeSkiCiAgICAgICAgKQoKICAgIHByaW50KCkKICAgIHByaW50KCJWRVJESUNUOiBQQVNTICgubmRlYyBkZWNpc2lvbiBhdHRlc3RhdGlvbikiKQogICAgcHJpbnQoIiAgd29ybGQ6ICAgICAgICAiICsgc3RyKHByZWRpY2F0ZS5nZXQoIndvcmxkX25hbWUiLCAiPyIpKSkKICAgIHByaW50KCIgIHZlcmRpY3Q6ICAgICAgIiArIHN0cihwcmVkaWNhdGUuZ2V0KCJ2ZXJkaWN0IiwgIj8iKSkpCiAgICBwcmludCgiICBub3VzX3ZlcnNpb246ICIgKyBzdHIocHJlZGljYXRlLmdldCgibm91c192ZXJzaW9uIiwgIj8iKSkpCiAgICBwcmludCgiICBwcm92ZXM6ICAgICAgIGNvc3QgZW52ZWxvcGUgKyBjb3ZlcmFnZSBvZiBkZWNsYXJlZCBuZXQiKQogICAgcHJpbnQoIiAgZXZpZGVuY2VzOiAgICBwcm92ZW5hbmNlICsgaXNzdWVyIG5vbi10YW1wZXJpbmciKQogICAgcHJpbnQoCiAgICAgICAgIiAgbm90X2NsYWltZWQ6ICBkZWNpc2lvbiBjb3JyZWN0bmVzcywgbGVnYWwgc3VmZmljaWVuY3ksICIKICAgICAgICAiY29tcGxpYW5jZSIKICAgICkKICAgIHJldHVybiAwCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHN5cy5leGl0KG1haW4oKSkK"
).decode("utf-8")

README_NDEC_TXT: str = base64.b64decode(
    "Tk9VUyAubmRlYyAtLSBQb3J0YWJsZSBQcm9vZi1DYXJyeWluZyBBSS1EZWNpc2lvbiBBdHRlc3RhdGlvbgo9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgpUaGlzIGZpbGUgaXMgYSBaSVAgY29udGFpbmVyLiBJdCB3cmFwcyBhIE5PVVMgZG9zc2llciBpbiBhIHN0YW5kYXJkIERTU0UKZW52ZWxvcGUgb3ZlciBhbiBpbi10b3RvIHYxIFN0YXRlbWVudCwgd2l0aCBhIE5PVVMgcHJvb2YtY2FycnlpbmcgcHJlZGljYXRlLgoKVG8gdmVyaWZ5IG9mZmxpbmUgKG5vIE5PVVMgaW5zdGFsbCBuZWVkZWQ7IHJlcXVpcmVzIHRoZSBjcnlwdG9ncmFwaHkgbGlicmFyeSk6CgogICAgdW56aXAgPGZpbGU+Lm5kZWMgLWQgb3V0CiAgICBjZCBvdXQKICAgIHB5dGhvbjMgdmVyaWZ5X25kZWMucHkKCkV4aXQgMCA9IFBBU1MsIDEgPSBGQUlMLCAyID0gZW52aXJvbm1lbnQtbGltaXRlZCAoZS5nLiB6MyBhYnNlbnQgZm9yIGFuClNNVC1vbmx5IGNvdmVyYWdlIHByb29mOyB0aGUgRmFya2FzIHBhdGggbmVlZHMgb25seSB0aGUgc3RkbGliKS4KCnZlcmlmeV9uZGVjLnB5IGNoZWNrcyB0aGUgRFNTRSBzaWduYXR1cmUsIHRoYXQgdGhlIHN1YmplY3QgZGlnZXN0IGJpbmRzIHRoZQpjYXJyaWVkIG1hbmlmZXN0LCBhbmQgdGhhdCBldmVyeSBjYXJyaWVkIGFydGlmYWN0IC0tIGluY2x1ZGluZyB0aGUgZG9zc2llcgp2ZXJpZmllciAodmVyaWZ5X29mZmxpbmUucHkpIC0tIG1hdGNoZXMgdGhlIHNpZ25lZCBwcmVkaWNhdGUsIHRoZW4gcnVucwpkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5LgoKVGhlIGVudmVsb3BlIGlzIGludGVyb3BlcmFibGUgd2l0aCBEU1NFIC8gaW4tdG90byAvIGNvc2lnbiB0b29saW5nLiBUaGUKZ3VhcmFudGVlOiBpdCBQUk9WRVMgdGhlIGRlY2xhcmVkIGNvc3QvY292ZXJhZ2UgZW52ZWxvcGUgKHozIG9yIEZhcmthcykgYW5kCkVWSURFTkNFUyBwcm92ZW5hbmNlIGFuZCBpc3N1ZXIgbm9uLXRhbXBlcmluZyAoRWQyNTUxOSkuIEl0IGRvZXMgTk9UIHByb3ZlIHRoZQpkZWNpc2lvbiB3YXMgY29ycmVjdCwgdGhhdCB0aGUgZG9zc2llciBpcyBsZWdhbGx5IHN1ZmZpY2llbnQsIG9yIHRoYXQKcmVndWxhdG9yeSBjb21wbGlhbmNlIGlzIGNvbmZlcnJlZC4gVGhlIHNpZ25lciBrZXkgaXMgYXNzZXJ0ZWQgaW4gdGhlCnByZWRpY2F0ZTsgdHJ1c3RpbmcgaXQgaXMgeW91ciBkZWNpc2lvbi4gVG8gdmVyaWZ5IHdpdGhvdXQgdHJ1c3RpbmcgdGhpcwpidW5kbGUsIGluc3RhbGwgbm91cy1sYW5nIGFuZCBydW4gYG5vdXMgdmVyaWZ5YC4K"
).decode("utf-8")

_ARTIFACT_FILES: dict = {
    "manifest_sha256": "manifest.json",
    "source_sha256": "source.nous",
    "pricing_sha256": "pricing.toml",
    "coverage_smt2_sha256": "coverage.smt2",
    "coverage_farkas_sha256": "coverage.farkas.json",
    "annex_iv_map_sha256": "annex_iv_map.json",
    "verify_offline_sha256": "verify_offline.py",
}


@dataclasses.dataclass(frozen=True)
class NdecResult:
    path: Path
    files: tuple
    artifacts: dict


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_dossier_consistency(dossier_dir: Path, man: dict) -> None:
    sig = man.get("signature")
    if not isinstance(sig, dict):
        raise NdecError("dossier manifest has no signature block")
    pub_b64 = sig.get("public_key_b64", "")
    sig_b64 = sig.get("signature_b64", "")
    if not pub_b64 or not sig_b64:
        raise NdecError("dossier manifest signature incomplete")
    body = {
        k: v
        for k, v in man.items()
        if k not in ("signature", "transparency_log")
    }
    body_bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pub_b64)
        ).verify(base64.b64decode(sig_b64), body_bytes)
    except InvalidSignature:
        raise NdecError(
            "dossier manifest Ed25519 signature does not verify; "
            "refusing to wrap"
        )
    for fname, field in (
        ("source.nous", "source_sha256"),
        ("coverage.smt2", "coverage_smt2_sha256"),
        ("coverage.farkas.json", "coverage_farkas_sha256"),
    ):
        declared = man.get(field)
        if declared:
            p = dossier_dir / fname
            if not p.is_file():
                raise NdecError(
                    "manifest declares " + field + " but " + fname
                    + " is missing"
                )
            if _file_sha256(p) != declared:
                raise NdecError(
                    fname + " sha256 mismatch vs manifest " + field
                    + "; refusing to wrap"
                )


def _dossier_artifacts(dossier_dir: Path, man: dict) -> dict:
    arts: dict = {}
    for key, fname in _ARTIFACT_FILES.items():
        p = dossier_dir / fname
        if p.is_file():
            arts[key] = _file_sha256(p)
    if "manifest_sha256" not in arts:
        raise NdecError("dossier has no manifest.json")
    if "verify_offline_sha256" not in arts:
        raise NdecError("dossier has no verify_offline.py")
    arts["manifest_canonical_sha256"] = manifest_canonical_sha256(man)
    return arts


def _build_zip_bytes(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for arcname in sorted(entries):
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, entries[arcname])
    return buf.getvalue()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def build_ndec(
    dossier_dir,
    *,
    key_path=None,
    output=None,
) -> NdecResult:
    dossier_dir = Path(dossier_dir).resolve()
    if not dossier_dir.is_dir():
        raise NdecError("dossier dir not found: " + str(dossier_dir))
    man_path = dossier_dir / "manifest.json"
    if not man_path.is_file():
        raise NdecError("manifest.json not found in " + str(dossier_dir))
    man = json.loads(man_path.read_text(encoding="utf-8"))
    _verify_dossier_consistency(dossier_dir, man)
    artifacts = _dossier_artifacts(dossier_dir, man)

    import manifest as _manifest_module

    priv, pub, _kp = _manifest_module.load_or_create_keypair(
        Path(key_path) if key_path is not None else None
    )
    signer_b64 = base64.b64encode(
        pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")

    transparency = None
    tlog = man.get("transparency_log")
    if isinstance(tlog, dict) and "log_index" in tlog:
        transparency = {
            "rekor_log_index": tlog.get("log_index"),
            "rekor_log_id": tlog.get("log_id"),
        }

    predicate = build_decision_predicate(
        manifest=man,
        artifacts=artifacts,
        signer_public_key_b64=signer_b64,
        transparency=transparency,
    )
    statement = build_statement(manifest=man, predicate=predicate)
    envelope = sign_envelope(statement=statement, private_key=priv)

    entries: dict = {}
    for child in sorted(dossier_dir.iterdir()):
        if child.is_file():
            entries["dossier/" + child.name] = child.read_bytes()
    entries["attestation.intoto.json"] = json.dumps(
        envelope, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    entries["verify_ndec.py"] = VERIFY_NDEC_PY.encode("utf-8")
    entries["README.ndec.txt"] = README_NDEC_TXT.encode("utf-8")

    if output is None:
        output = dossier_dir.parent / (dossier_dir.name + ".ndec")
    output = Path(output)
    _atomic_write_bytes(output, _build_zip_bytes(entries))
    return NdecResult(
        path=output, files=tuple(sorted(entries)), artifacts=artifacts
    )


# __s147_u3_verify_file_v1__
def verify_ndec_file(ndec_path, *, public_key=None, strict_canonical: bool = False) -> int:  # __s147_u4_strict_param_v1__
    """Installed trusted-path verification of a .ndec file.

    Envelope, subject binding, and artifact binding (including the carried
    dossier verifier, pinned via verify_offline_sha256) are checked by this
    installed module -- not by any bytes carried in the archive. The pinned
    carried verify_offline.py is then executed in a temp extraction as a
    subprocess (process isolation; honours the dossier verifier contract).

    Returns 0 PASS / 1 FAIL / 2 environment-limited.
    """
    import shutil
    import sys

    ndec_path = Path(ndec_path)
    if not ndec_path.is_file():
        print("verify: .ndec not found: " + str(ndec_path), file=sys.stderr)
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="ndec_verify_"))
    try:
        with zipfile.ZipFile(ndec_path) as zf:
            for name in zf.namelist():
                parts = Path(name).parts
                if name.startswith("/") or ".." in parts:
                    print(
                        "verify: unsafe path in archive: " + name,
                        file=sys.stderr,
                    )
                    return 1
            zf.extractall(tmp)
        env_path = tmp / "attestation.intoto.json"
        if not env_path.is_file():
            print("verify: attestation.intoto.json missing", file=sys.stderr)
            return 1
        man_path = tmp / "dossier" / "manifest.json"
        if not man_path.is_file():
            print("verify: dossier/manifest.json missing", file=sys.stderr)
            return 1
        try:
            envelope = json.loads(env_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print("verify: envelope parse error: " + str(exc), file=sys.stderr)
            return 1

        if public_key is None:
            try:
                peek = json.loads(
                    base64.b64decode(envelope["payload"]).decode("utf-8")
                )
                signer_b64 = peek.get("predicate", {}).get(
                    "signer_public_key_b64", ""
                )
            except Exception:
                signer_b64 = ""
            if not signer_b64:
                print(
                    "verify: predicate carries no signer key", file=sys.stderr
                )
                return 1
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(signer_b64)
            )

        try:
            statement = verify_envelope(
                envelope=envelope, public_key=public_key
            )
        except NdecError as exc:
            print("verify: " + str(exc), file=sys.stderr)
            return 1
        print("OK   DSSE envelope Ed25519 signature verified")

        man = json.loads(man_path.read_text(encoding="utf-8"))
        subject = statement.get("subject")
        if not isinstance(subject, list) or len(subject) != 1:
            print("verify: subject must be one entry", file=sys.stderr)
            return 1
        subj = subject[0].get("digest", {}).get("sha256", "")
        if manifest_canonical_sha256(man) != subj:
            print(
                "verify: subject digest does not bind manifest",
                file=sys.stderr,
            )
            return 1
        print("OK   subject digest binds dossier/manifest.json")

        artifacts = statement.get("predicate", {}).get("artifacts", {})
        if "verify_offline_sha256" not in artifacts:
            print(
                "verify: predicate does not pin verify_offline_sha256",
                file=sys.stderr,
            )
            return 1
        checked = 0
        for key, fname in _ARTIFACT_FILES.items():
            declared = artifacts.get(key)
            if declared is None:
                continue
            fpath = tmp / "dossier" / fname
            if not fpath.is_file():
                print(
                    "verify: predicate declares " + key
                    + " but dossier/" + fname + " missing",
                    file=sys.stderr,
                )
                return 1
            if _file_sha256(fpath) != declared:
                print(
                    "verify: artifact digest mismatch dossier/" + fname,
                    file=sys.stderr,
                )
                return 1
            checked += 1
        print(
            "OK   " + str(checked) + " carried artifact(s) match the signed "
            "predicate (including the dossier verifier)"
        )

        verifier = tmp / "dossier" / "verify_offline.py"
        if not verifier.is_file():
            print("verify: dossier/verify_offline.py missing", file=sys.stderr)
            return 1
        # __s147_u4_canonical_check_v1__
        carried_vsha = _file_sha256(verifier)
        canon = canonical_verifier_digests()
        canon_name = None
        for _cname, _cdig in canon.items():
            if _cdig == carried_vsha:
                canon_name = _cname
                break
        if canon_name is not None:
            print(
                "OK   verify_offline.py is a canonical NOUS verifier "
                "template (" + canon_name + "); trusting-trust closed"
            )
        else:
            if strict_canonical:
                print(
                    "verify: carried verify_offline.py is not in this "
                    "installed version's canonical verifier set and "
                    "--strict-canonical is set; refused",
                    file=sys.stderr,
                )
                return 1
            print(
                "NOTE verify_offline.py is NOT in this installed "
                "version's canonical verifier set (different NOUS "
                "version or non-canonical); it remains bound by the "
                "signed predicate, but trusting-trust is NOT closed -- "
                "trust reduces to the signer key plus the pin"
            )
        try:
            proc = subprocess.run(
                [sys.executable, str(verifier)],
                cwd=str(tmp / "dossier"),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("verify: inner verifier timed out", file=sys.stderr)
            return 1
        sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        rc = proc.returncode
        if rc == 2:
            print(
                "NOTE inner proof environment-limited (exit 2); crypto + "
                "binding gates PASSED"
            )
            return 2
        if rc != 0:
            print(
                "verify: inner dossier verifier returned " + str(rc),
                file=sys.stderr,
            )
            return 1
        predicate = statement.get("predicate", {})
        print()
        print("VERDICT: PASS (.ndec via installed verifier)")
        print("  world:        " + str(predicate.get("world_name", "?")))
        print("  verdict:      " + str(predicate.get("verdict", "?")))
        print("  nous_version: " + str(predicate.get("nous_version", "?")))
        print("  proves:       cost envelope + coverage of declared net")
        print("  evidences:    provenance + issuer non-tampering")
        # __s147_u4_verifier_footer_v1__
        print(
            "  verifier:     " + (
                "canonical:" + canon_name if canon_name
                else "signature-pinned (not confirmed canonical)"
            )
        )
        print(
            "  not_claimed:  decision correctness, legal sufficiency, "
            "compliance"
        )
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# __s147_u4_canonical_digests_v1__
def canonical_verifier_digests() -> dict:
    """Map template-name -> sha256 for every installed dossier
    verify_offline.py template. The installed allowlist: a carried
    verifier whose sha is in this set is provably an unmodified
    official NOUS verifier (exact-sha; a doctored verifier cannot
    match). Best-effort across the static VERIFY_OFFLINE_PY* template
    constants; the rare composed chain+net-full verifier is not
    enumerated and degrades to signature-pinned in this version.
    """
    import dossier
    out: dict = {}
    for name, val in vars(dossier).items():
        if name.startswith("VERIFY_OFFLINE_PY") and isinstance(
            val, str
        ):
            out[name] = hashlib.sha256(
                val.encode("utf-8")
            ).hexdigest()
    return out
