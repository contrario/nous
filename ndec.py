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
import re
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
    "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJPZmZsaW5lIHZlcmlmaWNhdGlvbiBvZiBhIE5PVVMgLm5kZWMgZGVjaXNpb24gYXR0ZXN0YXRpb24uCgpVc2FnZTogcHl0aG9uMyAtSSB2ZXJpZnlfbmRlYy5weSAtLWV4cGVjdC1zaWduZXIgQkFTRTY0CkV4aXQ6ICAwID0gUEFTUywgMSA9IElOVEVHUklUWSwgMiA9IEVOVklST05NRU5ULCAzID0gT1VUU0lERSAoTlQtR0FURS0xCiAgICAgICBENCkuIFRoZSBsYXN0IGxpbmUgb24gc3Rkb3V0IG5hbWVzIHRoZSBjbGFzcy4gTm8gUEFTUyB3aXRob3V0CiAgICAgICAtLWV4cGVjdC1zaWduZXIsIHRoZSAubmRlYyBzaWduZXIncyBrZXksIGZyb20gdGhlIGF1ZGl0b3IuClJlcXVpcmVzOiBjcnlwdG9ncmFwaHkgKG5vIE5PVVMgaW5zdGFsbCBuZWVkZWQpLgoKV2hhdCB0aGlzIHZlcmlmaWVzLCBmYWlsLWNsb3NlZCwgaW4gb3JkZXI6CiAgMS4gRFNTRSBlbnZlbG9wZTogRWQyNTUxOSBvdmVyIFBBRShwYXlsb2FkVHlwZSwgYm9keSk7IHBheWxvYWRUeXBlIGFuZAogICAgIHByZWRpY2F0ZVR5cGUgbXVzdCBiZSB0aGUgTk9VUyBkZWNpc2lvbiB0eXBlczsga2V5aWQgPT0gc2hhMjU2KHB1YmtleSkuCiAgMi4gU3ViamVjdCBiaW5kaW5nOiBzaGEyNTYgb2YgdGhlIGNhbm9uaWNhbCBkb3NzaWVyL21hbmlmZXN0Lmpzb24gYm9keQogICAgIChzaWduYXR1cmUgKyB0cmFuc3BhcmVuY3lfbG9nIHN0cmlwcGVkKSA9PSBzdGF0ZW1lbnQgc3ViamVjdCBkaWdlc3QuCiAgMy4gQXJ0aWZhY3QgYmluZGluZzogZXZlcnkgZGlnZXN0IGluIHRoZSBzaWduZWQgcHJlZGljYXRlIC0tIElOQ0xVRElORyB0aGUKICAgICBkb3NzaWVyIHZlcmlmaWVyIGl0c2VsZiAodmVyaWZ5X29mZmxpbmVfc2hhMjU2KSAtLSBtYXRjaGVzIHRoZSBjYXJyaWVkCiAgICAgZmlsZSBieXRlcy4KICA0LiBJbm5lciBwcm9vZjogcnVucyBkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5IGFzIGEgc3VicHJvY2VzcyB3aXRoCiAgICAgLS1leHBlY3Qtc2lnbmVyIHNldCB0byB0aGUgbWFuaWZlc3QncyBvd24ga2V5LCB3aGljaCB0aGUgZW52ZWxvcGUKICAgICBiaW5kcyB0aHJvdWdoIG1hbmlmZXN0X3NoYTI1NiAocmVxdWlyZWQpLCBhbmQgbWFwcyBpdHMgZXhpdCBjb2RlCiAgICAgKDAgUEFTUyAvIDEgSU5URUdSSVRZIC8gMiBFTlZJUk9OTUVOVCAvIDMgT1VUU0lERSkuCgpUcnVzdCBub3RlOiB0aGUgcHJlZGljYXRlJ3Mgc2lnbmVyIGtleSBtdXN0IGVxdWFsIC0tZXhwZWN0LXNpZ25lciwgd2hpY2ggdGhlCmF1ZGl0b3Igc3VwcGxpZXMgZnJvbSBvdXRzaWRlIHRoaXMgYnVuZGxlOyB3aG8gaG9sZHMgaXQgaXMgZXN0YWJsaXNoZWQgb3V0IG9mCmJhbmQuIFRoaXMgY29uZmlybXMgdGhlIGJ1bmRsZSBpcyBpbnRlcm5hbGx5IGNvbnNpc3RlbnQgYW5kIHRoZSBjYXJyaWVkCmRvc3NpZXIgdmVyaWZpZXIgaXMgdGhlIG9uZSB0aGF0IHNpZ25lciBjb21taXR0ZWQgdG8sIHRoZW4gcnVucyBpdCBpc29sYXRlZAoocHl0aG9uIC1JKS4gUnVuIHRoaXMgZmlsZSB3aXRoIHB5dGhvbjMgLUkgYXMgd2VsbDogdGhlIGJ1bmRsZSdzIHNlbmRlcgpjb250cm9scyBpdHMgZGlyZWN0b3J5LiBgbm91cyBuZGVjIHZlcmlmeSA8ZmlsZT4ubmRlYyAtLWV4cGVjdC1zaWduZXIgQkFTRTY0YApjaGVja3MgdGhlIGVudmVsb3BlIGFuZCBiaW5kaW5ncyB3aXRoIGluc3RhbGxlZCBjb2RlIGFuZCBhbHNvIGNvbmZpcm1zIHRoZQpjYXJyaWVkIGRvc3NpZXIgdmVyaWZpZXIgYWdhaW5zdCB0aGUgaW5zdGFsbGVkIGNhbm9uaWNhbCB0ZW1wbGF0ZXMgYmVmb3JlIGl0CnJ1bnMgaXQ7IGl0IHN0aWxsIHJ1bnMgaXQuIFRoZQplbnZlbG9wZSBpcyBpbnRlcm9wZXJhYmxlOyB0aGUgZ3VhcmFudGVlIGlzOiBQUk9WRVMgdGhlCmNvc3QvY292ZXJhZ2UgZW52ZWxvcGUgKHozIC8gRmFya2FzLCB2aWEgdGhlIGlubmVyIHZlcmlmaWVyKSwgRVZJREVOQ0VTCnByb3ZlbmFuY2UgYW5kIGlzc3VlciBub24tdGFtcGVyaW5nIChFZDI1NTE5KS4gSXQgZG9lcyBOT1QgcHJvdmUgZGVjaXNpb24KY29ycmVjdG5lc3MsIGxlZ2FsIHN1ZmZpY2llbmN5LCBvciByZWd1bGF0b3J5IGNvbXBsaWFuY2UuCiIiIgpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IGFubm90YXRpb25zCgppbXBvcnQgYmFzZTY0CmltcG9ydCBoYXNobGliCmltcG9ydCBqc29uCmltcG9ydCBzdWJwcm9jZXNzCmltcG9ydCBzeXMKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgpST09UID0gUGF0aChfX2ZpbGVfXykucGFyZW50CgpTVEFURU1FTlRfVFlQRSA9ICJodHRwczovL2luLXRvdG8uaW8vU3RhdGVtZW50L3YxIgpQQVlMT0FEX1RZUEUgPSAiYXBwbGljYXRpb24vdm5kLmluLXRvdG8ranNvbiIKUFJFRElDQVRFX1RZUEUgPSAiaHR0cHM6Ly9ub3VzLWxhbmcub3JnL2F0dGVzdGF0aW9uL2RlY2lzaW9uL3YxIgoKQVJUSUZBQ1RfRklMRVMgPSB7CiAgICAibWFuaWZlc3Rfc2hhMjU2IjogIm1hbmlmZXN0Lmpzb24iLAogICAgInNvdXJjZV9zaGEyNTYiOiAic291cmNlLm5vdXMiLAogICAgInByaWNpbmdfc2hhMjU2IjogInByaWNpbmcudG9tbCIsCiAgICAiY292ZXJhZ2Vfc210Ml9zaGEyNTYiOiAiY292ZXJhZ2Uuc210MiIsCiAgICAiY292ZXJhZ2VfZmFya2FzX3NoYTI1NiI6ICJjb3ZlcmFnZS5mYXJrYXMuanNvbiIsCiAgICAiY29zdF9mYXJrYXNfc2hhMjU2IjogImNvc3QuZmFya2FzLmpzb24iLAogICAgImFubmV4X2l2X21hcF9zaGEyNTYiOiAiYW5uZXhfaXZfbWFwLmpzb24iLAogICAgInZlcmlmeV9vZmZsaW5lX3NoYTI1NiI6ICJ2ZXJpZnlfb2ZmbGluZS5weSIsCn0KCgpkZWYgX2ZhaWwobXNnKToKICAgIHByaW50KCJGQUlMOiAiICsgbXNnLCBmaWxlPXN5cy5zdGRlcnIpCiAgICByZXR1cm4gMQoKCmRlZiBfcGFlKHBheWxvYWRfdHlwZSwgYm9keSk6CiAgICBwdCA9IHBheWxvYWRfdHlwZS5lbmNvZGUoInV0Zi04IikKICAgIHJldHVybiAoCiAgICAgICAgYiJEU1NFdjEiCiAgICAgICAgKyBiIiAiICsgc3RyKGxlbihwdCkpLmVuY29kZSgiYXNjaWkiKSArIGIiICIgKyBwdAogICAgICAgICsgYiIgIiArIHN0cihsZW4oYm9keSkpLmVuY29kZSgiYXNjaWkiKSArIGIiICIgKyBib2R5CiAgICApCgoKZGVmIF9jYW5vbmljYWxfYm9keV9ieXRlcyhtYW5pZmVzdCk6CiAgICBib2R5ID0gewogICAgICAgIGs6IHYKICAgICAgICBmb3IgaywgdiBpbiBtYW5pZmVzdC5pdGVtcygpCiAgICAgICAgaWYgayBub3QgaW4gKCJzaWduYXR1cmUiLCAidHJhbnNwYXJlbmN5X2xvZyIpCiAgICB9CiAgICByZXR1cm4ganNvbi5kdW1wcygKICAgICAgICBib2R5LCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oIiwiLCAiOiIpCiAgICApLmVuY29kZSgidXRmLTgiKQoKCiMgLS0tIHYzIHZlcmRpY3QgY2xhc3NlcyBlbWJlZCAoc2hhcmVkIHRleHQ7IGNhbm9uaWNhbCBjb3B5OiBjb25mb3JtYW5jZV92ZXJpZmllci5weSkgLS0tCiMgRXZlcnkgb2ZmbGluZSB2ZXJpZmllciBpbiBOVC1HQVRFLTEgVjMncyBzY29wZSBjYXJyaWVzIHRoaXMgcmVnaW9uCiMgYnl0ZS1mb3ItYnl0ZTsgdGVzdHMvdGVzdF9udF92M19jbGFzc2VzLnB5IG5hbWVzIGFueSBjb3B5IHRoYXQgZHJpZnRzLgojIEV4aXQgY2xhc3NlcyAoRDQgYXMgYW1lbmRlZCk6IDAgUEFTUywgMSBJTlRFR1JJVFksIDIgRU5WSVJPTk1FTlQsCiMgMyBPVVRTSURFOyB0aGUgbGFzdCBsaW5lIG9uIHN0ZG91dCBuYW1lcyB0aGUgY2xhc3MuIE5vIFBBU1Mgd2l0aG91dAojIGEgcHVibGljIGtleSB0aGUgYXVkaXRvciBzdXBwbGllcyAoLS1leHBlY3Qtc2lnbmVyKS4gU3RhbmRhcmQKIyBsaWJyYXJ5IG9ubHkuIF9fbnRfdjNfY2xhc3Nlc192MV9fCl9WM19DTEFTU0VTID0gezA6ICJQQVNTIiwgMTogIklOVEVHUklUWSIsIDI6ICJFTlZJUk9OTUVOVCIsIDM6ICJPVVRTSURFIn0KX1YzX1NUQVRFID0geyJwaW4iOiBOb25lLCAiZmxhZ3MiOiBmcm96ZW5zZXQoKSwgImtleXMiOiB7fSwKICAgICAgICAgICAgICJvdXRzaWRlIjogRmFsc2V9Cl9WM19OT19QSU4gPSAoCiAgICAibm8gLS1leHBlY3Qtc2lnbmVyOiB0aGlzIHZlcmlmaWVyIGdpdmVzIG5vIFBBU1Mgd2l0aG91dCBhIHB1YmxpYyAiCiAgICAia2V5IHRoZSBhdWRpdG9yIHN1cHBsaWVzIGZyb20gb3V0c2lkZSB0aGUgZXZpZGVuY2UiCikKX1YzX05PVF9DTEFJTUVEID0gewogICAgInJ1bnRpbWUiOiAoCiAgICAgICAgImNvbXBsZXRlbmVzczogdGhhdCB0aGUgcmVjb3JkZWQgZXZlbnRzIGFyZSBhbGwgdGhlIGV2ZW50czsgdGhlICIKICAgICAgICAicmVjb3JkZXIgcnVucyBpbiB0aGUgb3BlcmF0b3IncyBwcm9jZXNzIiwKICAgICAgICAidG9rZW4gY291bnRzOiBwcm92aWRlci1yZXBvcnRlZDsgdW5hdHRlc3RlZCB1bmxlc3MgIgogICAgICAgICJwcm92aWRlcl90b2tlbl9pbnRlZ3JpdHkgaXMgdGVlX2F0dGVzdGVkLCBhbmQgbm8gcmVjZWlwdCBpcyAiCiAgICAgICAgInZlcmlmaWVkIGhlcmUiLAogICAgICAgICJ0aGUgc2VydmVkIG1vZGVsOiB0aGUgcmVjb3JkZXIgcmVjb3JkcyB0aGUgcmVxdWVzdGVkIG1vZGVsIiwKICAgICAgICAidG9vbCBsYWJlbHMgaW4gYSB3b3JsZCB0aGF0IGRlY2xhcmVzIG5vIGV2ZW50czogdW5jaGVja2VkIiwKICAgICAgICAib2JsaWdhdGlvbnMgb3V0c2lkZSB0aGUgcmVjb21wdXRlZCBzY29wZTogcmVwb3J0ZWQgYXMgbm90ICIKICAgICAgICAicmVjb21wdXRlZCwgbmV2ZXIgZm9sZGVkIGludG8gUEFTUyIsCiAgICAgICAgInByaWNlcyBvdXRzaWRlIHRoZSB0YWJsZSdzIHJhdGUgbW9kZWw6IGNhY2hlIHdyaXRlcywgYmF0Y2ggIgogICAgICAgICJ0aWVycywgZmFpbGVkIGF0dGVtcHRzIiwKICAgICAgICAidGltZTogdGhhdCB0aGUgZGVjbGFyZWQgcHJvZ3JhbSBleGlzdGVkIGJlZm9yZSB0aGUgcnVuIiwKICAgICAgICAiaWRlbnRpdHk6IHRoZSBrZXkgbmFtZXMgYSBwYXJ0eSBvbmx5IHRocm91Z2ggdGhlIGF1ZGl0b3IncyBwaW4iLAogICAgICAgICJ0aGUgb3BlcmF0b3IncyBob25lc3R5OiB0aGUgb3BlcmF0b3IgaG9sZHMgdGhlIGtleSwgcnVucyB0aGUgIgogICAgICAgICJyZWNvcmRlciBhbmQgd3JpdGVzIHRoZSBudW1iZXJzIiwKICAgICAgICAiY29udHJvbDogbm9uZS4gQSBtb25pdG9yLiIsCiAgICAgICAgInJlZ3VsYXRvcnkgc3RhdHVzOiBub25lIiwKICAgICksCiAgICAiZG9zc2llciI6ICgKICAgICAgICAiZGVjbGFyZWQgZXN0aW1hdGVzOiB0aGUgY29zdCBib3VuZCBpcyBvdmVyIHRoZSBkZWNsYXJlZCB0b2tlbiAiCiAgICAgICAgImVzdGltYXRlcyBhbmQgcHJpY2VzOyBhIGRvc3NpZXIgb2JzZXJ2ZXMgbm8gcnVuIiwKICAgICAgICAiaWRlbnRpdHk6IHRoZSBrZXkgbmFtZXMgYSBwYXJ0eSBvbmx5IHRocm91Z2ggdGhlIGF1ZGl0b3IncyBwaW4iLAogICAgICAgICJ0aGUgb3BlcmF0b3IncyBob25lc3R5OiB0aGUgb3BlcmF0b3Igd3JpdGVzIHRoZSBzb3VyY2UgYW5kIGhvbGRzICIKICAgICAgICAidGhlIGtleSIsCiAgICAgICAgImNvbnRyb2w6IG5vbmUuIEEgbW9uaXRvci4iLAogICAgICAgICJyZWd1bGF0b3J5IHN0YXR1czogbm9uZSIsCiAgICApLAp9CgoKZGVmIF92M19waW5fcmF3KGI2NCk6CiAgICBpbXBvcnQgYmFzZTY0CiAgICBpZiBub3QgaXNpbnN0YW5jZShiNjQsIHN0cik6CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIHRyeToKICAgICAgICByYXcgPSBiYXNlNjQuYjY0ZGVjb2RlKGI2NCwgdmFsaWRhdGU9VHJ1ZSkKICAgIGV4Y2VwdCAoVmFsdWVFcnJvciwgVHlwZUVycm9yKToKICAgICAgICByZXR1cm4gTm9uZQogICAgcmV0dXJuIHJhdyBpZiBsZW4ocmF3KSA9PSAzMiBlbHNlIE5vbmUKCgpkZWYgX3YzX2FyZ3MoYXJndiwgZmxhZ3M9KCksIGtleWVkPSgpKToKICAgICMgRXhhY3RseSBvbmUgLS1leHBlY3Qtc2lnbmVyLCBlYWNoIG9wdGlvbiBvZiBrZXllZCBhdCBtb3N0IG9uY2UsCiAgICAjIGVhY2ggd2l0aCBhIGJhc2U2NCByYXcgMzItYnl0ZSBrZXk7IGVhY2ggb2YgZmxhZ3MgYXQgbW9zdCBvbmNlOwogICAgIyBub3RoaW5nIGVsc2UuIFJldHVybnMgKHBpbiwgZmxhZ3Nfc2Vlbiwga2V5cywgIiIpIG9yCiAgICAjIChOb25lLCBOb25lLCBOb25lLCB3aHkpLgogICAga2V5cyA9IHt9CiAgICBzZWVuID0gc2V0KCkKICAgIGkgPSAwCiAgICB3aGlsZSBpIDwgbGVuKGFyZ3YpOgogICAgICAgIGEgPSBhcmd2W2ldCiAgICAgICAgaWYgYSA9PSAiLS1leHBlY3Qtc2lnbmVyIiBvciBhIGluIGtleWVkOgogICAgICAgICAgICBpZiBhIGluIGtleXMgb3IgaSArIDEgPj0gbGVuKGFyZ3YpOgogICAgICAgICAgICAgICAgcmV0dXJuIE5vbmUsIE5vbmUsIE5vbmUsICgKICAgICAgICAgICAgICAgICAgICBhICsgIiBtdXN0IGJlIGdpdmVuIG9uY2UsIHdpdGggYSBrZXkiKQogICAgICAgICAgICByYXcgPSBfdjNfcGluX3Jhdyhhcmd2W2kgKyAxXSkKICAgICAgICAgICAgaWYgcmF3IGlzIE5vbmU6CiAgICAgICAgICAgICAgICByZXR1cm4gTm9uZSwgTm9uZSwgTm9uZSwgKAogICAgICAgICAgICAgICAgICAgIGEgKyAiIGlzIG5vdCBhIGJhc2U2NCByYXcgMzItYnl0ZSBFZDI1NTE5IHB1YmxpYyBrZXkiKQogICAgICAgICAgICBrZXlzW2FdID0gcmF3CiAgICAgICAgICAgIGkgKz0gMgogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGlmIGEgaW4gZmxhZ3MgYW5kIGEgbm90IGluIHNlZW46CiAgICAgICAgICAgIHNlZW4uYWRkKGEpCiAgICAgICAgICAgIGkgKz0gMQogICAgICAgICAgICBjb250aW51ZQogICAgICAgIHJldHVybiBOb25lLCBOb25lLCBOb25lLCAidW5leHBlY3RlZCBhcmd1bWVudCAiICsgcmVwcihhKQogICAgcGluID0ga2V5cy5wb3AoIi0tZXhwZWN0LXNpZ25lciIsIE5vbmUpCiAgICBpZiBwaW4gaXMgTm9uZToKICAgICAgICByZXR1cm4gTm9uZSwgTm9uZSwgTm9uZSwgX1YzX05PX1BJTgogICAgcmV0dXJuIHBpbiwgZnJvemVuc2V0KHNlZW4pLCBrZXlzLCAiIgoKCmRlZiBfdjNfa2V5KG9wdCk6CiAgICAjIFRoZSBhdWRpdG9yJ3Mga2V5IGZvciBvcHQsIGVsc2UgdGhlIC0tZXhwZWN0LXNpZ25lciBrZXkuCiAgICByZXR1cm4gX1YzX1NUQVRFWyJrZXlzIl0uZ2V0KG9wdCkgb3IgX1YzX1NUQVRFWyJwaW4iXQoKCmRlZiBfdjNfaXNfcGlubmVkKHB1Yl9iNjQsIG9wdD0iLS1leHBlY3Qtc2lnbmVyIik6CiAgICBpbXBvcnQgYmFzZTY0CiAgICBwaW4gPSBfdjNfa2V5KG9wdCkKICAgIGlmIHBpbiBpcyBOb25lIG9yIG5vdCBpc2luc3RhbmNlKHB1Yl9iNjQsIHN0cik6CiAgICAgICAgcmV0dXJuIEZhbHNlCiAgICB0cnk6CiAgICAgICAgcmV0dXJuIGJhc2U2NC5iNjRkZWNvZGUocHViX2I2NCwgdmFsaWRhdGU9VHJ1ZSkgPT0gcGluCiAgICBleGNlcHQgKFZhbHVlRXJyb3IsIFR5cGVFcnJvcik6CiAgICAgICAgcmV0dXJuIEZhbHNlCgoKZGVmIF92M19waW5fYjY0KG9wdD0iLS1leHBlY3Qtc2lnbmVyIik6CiAgICBpbXBvcnQgYmFzZTY0CiAgICByZXR1cm4gYmFzZTY0LmI2NGVuY29kZShfdjNfa2V5KG9wdCkpLmRlY29kZSgiYXNjaWkiKQoKCmRlZiBfdjNfbWFuaWZlc3RfYm9keShkb2MpOgogICAgaW1wb3J0IGpzb24KICAgIGJvZHkgPSB7CiAgICAgICAgazogdiBmb3IgaywgdiBpbiBkb2MuaXRlbXMoKQogICAgICAgIGlmIGsgbm90IGluICgic2lnbmF0dXJlIiwgInRyYW5zcGFyZW5jeV9sb2ciKQogICAgfQogICAgcmV0dXJuIGpzb24uZHVtcHMoYm9keSwgc29ydF9rZXlzPVRydWUsIHNlcGFyYXRvcnM9KCIsIiwgIjoiKSkuZW5jb2RlKAogICAgICAgICJ1dGYtOCIpCgoKZGVmIF92M19ub3RfY2xhaW1lZChraW5kKToKICAgIHByaW50KCkKICAgIHByaW50KCJOT1QgQ0xBSU1FRCAoTlQtR0FURS0xIDUuNSk6IikKICAgIGZvciBsaW5lIGluIF9WM19OT1RfQ0xBSU1FRFtraW5kXToKICAgICAgICBwcmludCgiICAtICIgKyBsaW5lKQoKCmRlZiBfdjNfb3V0c2lkZV9tYW5pZmVzdChtYW5pZmVzdCk6CiAgICAjIE1hcmtzIHRoZSBydW4gT1VUU0lERTsgbWFpbiBzdGlsbCByZXR1cm5zIDAgYWZ0ZXIgZXZlcnkgcmVtYWluaW5nCiAgICAjIGNoZWNrLCBhbmQgX3YzX3J1biB0dXJucyB0aGF0IDAgaW50byAzLiBBIGxhdGVyIGZhaWxpbmcgY2hlY2sKICAgICMgc3RpbGwgcmV0dXJucyAxIChJTlRFR1JJVFkgZmlyc3QpLgogICAgX1YzX1NUQVRFWyJvdXRzaWRlIl0gPSBUcnVlCiAgICB2ID0gbWFuaWZlc3QuZ2V0KCJ2ZXJkaWN0IikKICAgIHByaW50KCkKICAgIHByaW50KCJWRVJESUNUOiBPVVRTSURFIChhdXRoZW50aWMgbWFuaWZlc3QgdW5kZXIgdGhlIGV4cGVjdGVkIGtleTsgIgogICAgICAgICAgInRoZSBzb2x2ZXIgdmVyZGljdCBpcyAiICsgcmVwcih2KSArICIsIG5vdCAncHJvdmVuJywgc28gdGhlICIKICAgICAgICAgICJkZWNsYXJlZCBib3VuZCBpcyBub3QgZXN0YWJsaXNoZWQpIikKICAgIHByaW50KCIgIHdvcmxkOiAgICAgICIgKyBzdHIobWFuaWZlc3QuZ2V0KCJ3b3JsZF9uYW1lIiwgIj8iKSkpCiAgICBwcmludCgiICB2ZXJkaWN0OiAgICAiICsgc3RyKHYpKQoKCmRlZiBfdjNfcnVuKG1haW5fZm4sIGZsYWdzPSgpLCBwYXNzX2FyZ3Y9RmFsc2UsIHVzYWdlPSIiLCBrZXllZD0oKSk6CiAgICBpbXBvcnQgc3lzCiAgICBwaW4sIHNlZW4sIGtleXMsIHdoeSA9IF92M19hcmdzKHN5cy5hcmd2WzE6XSwgZmxhZ3MsIGtleWVkKQogICAgaWYgd2h5OgogICAgICAgIGlmIHVzYWdlOgogICAgICAgICAgICBwcmludCh1c2FnZSwgZmlsZT1zeXMuc3RkZXJyKQogICAgICAgIHByaW50KCJFUlJPUjogIiArIHdoeSwgZmlsZT1zeXMuc3RkZXJyKQogICAgICAgIHByaW50KCJDTEFTUzogRU5WSVJPTk1FTlQiKQogICAgICAgIHJldHVybiAyCiAgICBfVjNfU1RBVEVbInBpbiJdID0gcGluCiAgICBfVjNfU1RBVEVbImZsYWdzIl0gPSBzZWVuCiAgICBfVjNfU1RBVEVbImtleXMiXSA9IGtleXMKICAgIHRyeToKICAgICAgICByYyA9IG1haW5fZm4oc3lzLmFyZ3ZbMTpdKSBpZiBwYXNzX2FyZ3YgZWxzZSBtYWluX2ZuKCkKICAgIGV4Y2VwdCBTeXN0ZW1FeGl0IGFzIGV4YzoKICAgICAgICByYyA9IGV4Yy5jb2RlIGlmIGlzaW5zdGFuY2UoZXhjLmNvZGUsIGludCkgZWxzZSAxCiAgICBleGNlcHQgSW1wb3J0RXJyb3IgYXMgZXhjOgogICAgICAgIHByaW50KCJFUlJPUjogYSBtb2R1bGUgdGhpcyB2ZXJpZmllciBuZWVkcyBpcyBtaXNzaW5nICgiICsgc3RyKGV4YykKICAgICAgICAgICAgICArICIpOyBpbnN0YWxsOiBwaXAgaW5zdGFsbCAnY3J5cHRvZ3JhcGh5Pj00MiciLAogICAgICAgICAgICAgIGZpbGU9c3lzLnN0ZGVycikKICAgICAgICByYyA9IDIKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZXhjOgogICAgICAgIHByaW50KCJGQUlMOiB1bmhhbmRsZWQgIiArIHR5cGUoZXhjKS5fX25hbWVfXyArICI6ICIgKyBzdHIoZXhjKSwKICAgICAgICAgICAgICBmaWxlPXN5cy5zdGRlcnIpCiAgICAgICAgcmMgPSAxCiAgICBpZiBpc2luc3RhbmNlKHJjLCBib29sKSBvciByYyBub3QgaW4gX1YzX0NMQVNTRVM6CiAgICAgICAgcmMgPSAxCiAgICBpZiByYyA9PSAwIGFuZCBfVjNfU1RBVEVbIm91dHNpZGUiXToKICAgICAgICByYyA9IDMKICAgIHByaW50KCJDTEFTUzogIiArIF9WM19DTEFTU0VTW3JjXSkKICAgIHJldHVybiByYwojIC0tLSBlbmQgdjMgdmVyZGljdCBjbGFzc2VzIGVtYmVkIC0tLQoKCmRlZiBtYWluKCk6ICAjIF9fbnRfdjNfbmRlY19jYXJyaWVkX3YxX18KICAgIHRyeToKICAgICAgICBmcm9tIGNyeXB0b2dyYXBoeS5oYXptYXQucHJpbWl0aXZlcy5hc3ltbWV0cmljLmVkMjU1MTkgaW1wb3J0ICgKICAgICAgICAgICAgRWQyNTUxOVB1YmxpY0tleSwKICAgICAgICApCiAgICAgICAgZnJvbSBjcnlwdG9ncmFwaHkuZXhjZXB0aW9ucyBpbXBvcnQgSW52YWxpZFNpZ25hdHVyZQogICAgZXhjZXB0IEltcG9ydEVycm9yOgogICAgICAgIHByaW50KAogICAgICAgICAgICAiRVJST1I6IGNyeXB0b2dyYXBoeSBsaWJyYXJ5IHJlcXVpcmVkLlxuIgogICAgICAgICAgICAiSW5zdGFsbDogcGlwIGluc3RhbGwgJ2NyeXB0b2dyYXBoeT49NDInIiwKICAgICAgICAgICAgZmlsZT1zeXMuc3RkZXJyLAogICAgICAgICkKICAgICAgICByZXR1cm4gMgoKICAgIGVudl9wYXRoID0gUk9PVCAvICJhdHRlc3RhdGlvbi5pbnRvdG8uanNvbiIKICAgIGlmIG5vdCBlbnZfcGF0aC5pc19maWxlKCk6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJhdHRlc3RhdGlvbi5pbnRvdG8uanNvbiBub3QgZm91bmQgaW4gIiArIHN0cihST09UKSkKICAgIHRyeToKICAgICAgICBlbnZlbG9wZSA9IGpzb24ubG9hZHMoZW52X3BhdGgucmVhZF90ZXh0KGVuY29kaW5nPSJ1dGYtOCIpKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgiYXR0ZXN0YXRpb24uaW50b3RvLmpzb24gcGFyc2UgZXJyb3I6ICIgKyBzdHIoZSkpCiAgICBpZiBub3QgaXNpbnN0YW5jZShlbnZlbG9wZSwgZGljdCk6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJlbnZlbG9wZSBpcyBub3QgYSBKU09OIG9iamVjdCIpCiAgICBpZiBlbnZlbG9wZS5nZXQoInBheWxvYWRUeXBlIikgIT0gUEFZTE9BRF9UWVBFOgogICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgInVuc3VwcG9ydGVkIHBheWxvYWRUeXBlOiAiICsgcmVwcihlbnZlbG9wZS5nZXQoInBheWxvYWRUeXBlIikpCiAgICAgICAgKQogICAgcGF5bG9hZF9iNjQgPSBlbnZlbG9wZS5nZXQoInBheWxvYWQiKQogICAgc2lnbmF0dXJlcyA9IGVudmVsb3BlLmdldCgic2lnbmF0dXJlcyIpCiAgICBpZiBub3QgaXNpbnN0YW5jZShwYXlsb2FkX2I2NCwgc3RyKToKICAgICAgICByZXR1cm4gX2ZhaWwoImVudmVsb3BlIHBheWxvYWQgbWlzc2luZyIpCiAgICBpZiBub3QgaXNpbnN0YW5jZShzaWduYXR1cmVzLCBsaXN0KSBvciBub3Qgc2lnbmF0dXJlczoKICAgICAgICByZXR1cm4gX2ZhaWwoImVudmVsb3BlIHNpZ25hdHVyZXMgbWlzc2luZyIpCiAgICB0cnk6CiAgICAgICAgYm9keSA9IGJhc2U2NC5iNjRkZWNvZGUocGF5bG9hZF9iNjQsIHZhbGlkYXRlPVRydWUpCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJwYXlsb2FkIGJhc2U2NCBkZWNvZGUgZmFpbGVkOiAiICsgc3RyKGUpKQogICAgc2lnX2VudHJ5ID0gc2lnbmF0dXJlc1swXQogICAgaWYgbm90IGlzaW5zdGFuY2Uoc2lnX2VudHJ5LCBkaWN0KSBvciBub3QgaXNpbnN0YW5jZSgKICAgICAgICBzaWdfZW50cnkuZ2V0KCJzaWciKSwgc3RyCiAgICApOgogICAgICAgIHJldHVybiBfZmFpbCgic2lnbmF0dXJlIGVudHJ5IG1hbGZvcm1lZCIpCiAgICB0cnk6CiAgICAgICAgc2lnbmF0dXJlID0gYmFzZTY0LmI2NGRlY29kZShzaWdfZW50cnlbInNpZyJdLCB2YWxpZGF0ZT1UcnVlKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgic2lnbmF0dXJlIGJhc2U2NCBkZWNvZGUgZmFpbGVkOiAiICsgc3RyKGUpKQoKICAgIHRyeToKICAgICAgICBzdGF0ZW1lbnQgPSBqc29uLmxvYWRzKGJvZHkuZGVjb2RlKCJ1dGYtOCIpKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgidmVyaWZpZWQgYm9keSBpcyBub3QgdmFsaWQgSlNPTjogIiArIHN0cihlKSkKICAgIGlmIG5vdCBpc2luc3RhbmNlKHN0YXRlbWVudCwgZGljdCk6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJzdGF0ZW1lbnQgaXMgbm90IGEgSlNPTiBvYmplY3QiKQogICAgaWYgc3RhdGVtZW50LmdldCgiX3R5cGUiKSAhPSBTVEFURU1FTlRfVFlQRToKICAgICAgICByZXR1cm4gX2ZhaWwoInN0YXRlbWVudCBfdHlwZSBpcyBub3QgaW4tdG90byB2MSIpCiAgICBpZiBzdGF0ZW1lbnQuZ2V0KCJwcmVkaWNhdGVUeXBlIikgIT0gUFJFRElDQVRFX1RZUEU6CiAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAicHJlZGljYXRlVHlwZSBpcyBub3QgdGhlIE5PVVMgZGVjaXNpb24gdHlwZTogIgogICAgICAgICAgICArIHJlcHIoc3RhdGVtZW50LmdldCgicHJlZGljYXRlVHlwZSIpKQogICAgICAgICkKICAgIHByZWRpY2F0ZSA9IHN0YXRlbWVudC5nZXQoInByZWRpY2F0ZSIpCiAgICBpZiBub3QgaXNpbnN0YW5jZShwcmVkaWNhdGUsIGRpY3QpOgogICAgICAgIHJldHVybiBfZmFpbCgicHJlZGljYXRlIGlzIG5vdCBhIEpTT04gb2JqZWN0IikKICAgIHNpZ25lcl9iNjQgPSBwcmVkaWNhdGUuZ2V0KCJzaWduZXJfcHVibGljX2tleV9iNjQiLCAiIikKICAgIGlmIG5vdCBzaWduZXJfYjY0OgogICAgICAgIHJldHVybiBfZmFpbCgicHJlZGljYXRlIGNhcnJpZXMgbm8gc2lnbmVyX3B1YmxpY19rZXlfYjY0IikKICAgIGlmIG5vdCBfdjNfaXNfcGlubmVkKHNpZ25lcl9iNjQpOgogICAgICAgIHJldHVybiBfZmFpbCgibmRlYyBzaWduZXIgaXMgbm90IHRoZSBleHBlY3RlZCBrZXkgKC0tZXhwZWN0LXNpZ25lcikiKQogICAgdHJ5OgogICAgICAgIHB1Yl9yYXcgPSBiYXNlNjQuYjY0ZGVjb2RlKHNpZ25lcl9iNjQsIHZhbGlkYXRlPVRydWUpCiAgICAgICAgcHViX2tleSA9IEVkMjU1MTlQdWJsaWNLZXkuZnJvbV9wdWJsaWNfYnl0ZXMocHViX3JhdykKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoInNpZ25lciBwdWJsaWMga2V5IGRlY29kZSBlcnJvcjogIiArIHN0cihlKSkKCiAgICBleHBlY3RlZF9rZXlpZCA9IGhhc2hsaWIuc2hhMjU2KHB1Yl9yYXcpLmhleGRpZ2VzdCgpCiAgICBpZiBzaWdfZW50cnkuZ2V0KCJrZXlpZCIpICE9IGV4cGVjdGVkX2tleWlkOgogICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgImtleWlkIGRvZXMgbm90IG1hdGNoIHNoYTI1NiBvZiB0aGUgcHJlZGljYXRlIHNpZ25lciBrZXkiCiAgICAgICAgKQogICAgdHJ5OgogICAgICAgIHB1Yl9rZXkudmVyaWZ5KHNpZ25hdHVyZSwgX3BhZShQQVlMT0FEX1RZUEUsIGJvZHkpKQogICAgZXhjZXB0IEludmFsaWRTaWduYXR1cmU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJEU1NFIEVkMjU1MTkgc2lnbmF0dXJlIGRvZXMgbm90IHZlcmlmeSIpCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJEU1NFIHZlcmlmaWNhdGlvbiBlcnJvcjogIiArIHN0cihlKSkKICAgIHByaW50KCJPSyAgIERTU0UgZW52ZWxvcGUgRWQyNTUxOSBzaWduYXR1cmUgdmVyaWZpZWQiKQoKICAgIHN1YmplY3QgPSBzdGF0ZW1lbnQuZ2V0KCJzdWJqZWN0IikKICAgIGlmIG5vdCBpc2luc3RhbmNlKHN1YmplY3QsIGxpc3QpIG9yIGxlbihzdWJqZWN0KSAhPSAxOgogICAgICAgIHJldHVybiBfZmFpbCgic3RhdGVtZW50IHN1YmplY3QgbXVzdCBiZSBleGFjdGx5IG9uZSBlbnRyeSIpCiAgICBzdWJqX2RpZ2VzdCA9IHN1YmplY3RbMF0uZ2V0KCJkaWdlc3QiLCB7fSkuZ2V0KCJzaGEyNTYiLCAiIikKCiAgICBtYW5fcGF0aCA9IFJPT1QgLyAiZG9zc2llciIgLyAibWFuaWZlc3QuanNvbiIKICAgIGlmIG5vdCBtYW5fcGF0aC5pc19maWxlKCk6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL21hbmlmZXN0Lmpzb24gbm90IGZvdW5kIikKICAgIHRyeToKICAgICAgICBtYW5pZmVzdCA9IGpzb24ubG9hZHMobWFuX3BhdGgucmVhZF90ZXh0KGVuY29kaW5nPSJ1dGYtOCIpKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJldHVybiBfZmFpbCgiZG9zc2llci9tYW5pZmVzdC5qc29uIHBhcnNlIGVycm9yOiAiICsgc3RyKGUpKQogICAgcmVjb21wdXRlZCA9IGhhc2hsaWIuc2hhMjU2KF9jYW5vbmljYWxfYm9keV9ieXRlcyhtYW5pZmVzdCkpLmhleGRpZ2VzdCgpCiAgICBpZiByZWNvbXB1dGVkICE9IHN1YmpfZGlnZXN0OgogICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgInN1YmplY3QgZGlnZXN0IGRvZXMgbm90IGJpbmQgZG9zc2llci9tYW5pZmVzdC5qc29uOiAiCiAgICAgICAgICAgICJzdWJqZWN0PSIgKyBzdHIoc3Vial9kaWdlc3QpWzoxNl0gKyAiLi4uIHJlY29tcHV0ZWQ9IgogICAgICAgICAgICArIHJlY29tcHV0ZWRbOjE2XSArICIuLi4iCiAgICAgICAgKQogICAgcHJpbnQoIk9LICAgc3ViamVjdCBkaWdlc3QgYmluZHMgZG9zc2llci9tYW5pZmVzdC5qc29uIikKCiAgICBhcnRpZmFjdHMgPSBwcmVkaWNhdGUuZ2V0KCJhcnRpZmFjdHMiKQogICAgaWYgbm90IGlzaW5zdGFuY2UoYXJ0aWZhY3RzLCBkaWN0KSBvciBub3QgYXJ0aWZhY3RzOgogICAgICAgIHJldHVybiBfZmFpbCgicHJlZGljYXRlIGFydGlmYWN0cyBtaXNzaW5nIikKICAgIGNoZWNrZWQgPSAwCiAgICBmb3Iga2V5LCBmbmFtZSBpbiBBUlRJRkFDVF9GSUxFUy5pdGVtcygpOgogICAgICAgIGRlY2xhcmVkID0gYXJ0aWZhY3RzLmdldChrZXkpCiAgICAgICAgaWYgZGVjbGFyZWQgaXMgTm9uZToKICAgICAgICAgICAgY29udGludWUKICAgICAgICBmcGF0aCA9IFJPT1QgLyAiZG9zc2llciIgLyBmbmFtZQogICAgICAgIGlmIG5vdCBmcGF0aC5pc19maWxlKCk6CiAgICAgICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgICAgICJwcmVkaWNhdGUgZGVjbGFyZXMgIiArIGtleSArICIgYnV0IGRvc3NpZXIvIiArIGZuYW1lCiAgICAgICAgICAgICAgICArICIgaXMgbWlzc2luZyIKICAgICAgICAgICAgKQogICAgICAgIGFjdHVhbCA9IGhhc2hsaWIuc2hhMjU2KGZwYXRoLnJlYWRfYnl0ZXMoKSkuaGV4ZGlnZXN0KCkKICAgICAgICBpZiBhY3R1YWwgIT0gZGVjbGFyZWQ6CiAgICAgICAgICAgIHJldHVybiBfZmFpbCgKICAgICAgICAgICAgICAgICJhcnRpZmFjdCBkaWdlc3QgbWlzbWF0Y2ggZm9yIGRvc3NpZXIvIiArIGZuYW1lCiAgICAgICAgICAgICAgICArICI6IHByZWRpY2F0ZT0iICsgZGVjbGFyZWRbOjE2XSArICIuLi4gZmlsZT0iCiAgICAgICAgICAgICAgICArIGFjdHVhbFs6MTZdICsgIi4uLiIKICAgICAgICAgICAgKQogICAgICAgIGNoZWNrZWQgKz0gMQogICAgaWYgInZlcmlmeV9vZmZsaW5lX3NoYTI1NiIgbm90IGluIGFydGlmYWN0czoKICAgICAgICByZXR1cm4gX2ZhaWwoCiAgICAgICAgICAgICJwcmVkaWNhdGUgZG9lcyBub3QgcGluIHZlcmlmeV9vZmZsaW5lX3NoYTI1NjsgdGhlIGNhcnJpZWQgIgogICAgICAgICAgICAiZG9zc2llciB2ZXJpZmllciBpcyBub3QgYm91bmQgYnkgdGhlIHNpZ25hdHVyZSAocmVmdXNlZCkiCiAgICAgICAgKQogICAgZm9yIF9rIGluICgidmVyaWZ5X29mZmxpbmVfc2hhMjU2IiwgIm1hbmlmZXN0X3NoYTI1NiIpOgogICAgICAgIF92ID0gYXJ0aWZhY3RzLmdldChfaykKICAgICAgICBpZiBub3QgKGlzaW5zdGFuY2UoX3YsIHN0cikgYW5kIGxlbihfdikgPT0gNjQKICAgICAgICAgICAgICAgIGFuZCBhbGwoYyBpbiAiMDEyMzQ1Njc4OWFiY2RlZiIgZm9yIGMgaW4gX3YpKToKICAgICAgICAgICAgcmV0dXJuIF9mYWlsKCJwcmVkaWNhdGUgIiArIF9rICsgIiBpcyBub3QgNjQgaGV4IikKICAgIGlmICJtYW5pZmVzdF9zaGEyNTYiIG5vdCBpbiBhcnRpZmFjdHM6CiAgICAgICAgcmV0dXJuIF9mYWlsKAogICAgICAgICAgICAicHJlZGljYXRlIGRvZXMgbm90IHBpbiBtYW5pZmVzdF9zaGEyNTY7IHRoZSBtYW5pZmVzdCdzICIKICAgICAgICAgICAgInNpZ25lciBpcyBub3QgYm91bmQgYnkgdGhlIHNpZ25hdHVyZSAocmVmdXNlZCkiCiAgICAgICAgKQogICAgcHJpbnQoCiAgICAgICAgIk9LICAgIiArIHN0cihjaGVja2VkKSArICIgY2FycmllZCBhcnRpZmFjdChzKSBtYXRjaCB0aGUgc2lnbmVkICIKICAgICAgICAicHJlZGljYXRlIChpbmNsdWRpbmcgdGhlIGRvc3NpZXIgdmVyaWZpZXIpIgogICAgKQoKICAgIHZlcmlmaWVyID0gUk9PVCAvICJkb3NzaWVyIiAvICJ2ZXJpZnlfb2ZmbGluZS5weSIKICAgIGlmIG5vdCB2ZXJpZmllci5pc19maWxlKCk6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL3ZlcmlmeV9vZmZsaW5lLnB5IG5vdCBmb3VuZCIpCiAgICBtc2lnID0gbWFuaWZlc3QuZ2V0KCJzaWduYXR1cmUiKQogICAgbWFuX2tleSA9IG1zaWcuZ2V0KCJwdWJsaWNfa2V5X2I2NCIpIGlmIGlzaW5zdGFuY2UobXNpZywgZGljdCkgZWxzZSBOb25lCiAgICBpZiBub3QgaXNpbnN0YW5jZShtYW5fa2V5LCBzdHIpIG9yIF92M19waW5fcmF3KG1hbl9rZXkpIGlzIE5vbmU6CiAgICAgICAgcmV0dXJuIF9mYWlsKCJkb3NzaWVyL21hbmlmZXN0Lmpzb24gY2FycmllcyBubyB2YWxpZCBzaWduZXIga2V5IikKICAgIHRyeToKICAgICAgICBwcm9jID0gc3VicHJvY2Vzcy5ydW4oCiAgICAgICAgICAgIFtzeXMuZXhlY3V0YWJsZSwgIi1JIiwgIi1CIiwgc3RyKHZlcmlmaWVyKSwKICAgICAgICAgICAgICItLWV4cGVjdC1zaWduZXIiLCBtYW5fa2V5XSwKICAgICAgICAgICAgY3dkPXN0cihST09UIC8gImRvc3NpZXIiKSwKICAgICAgICAgICAgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwKICAgICAgICAgICAgdGV4dD1UcnVlLAogICAgICAgICAgICB0aW1lb3V0PTEyMCwKICAgICAgICApCiAgICBleGNlcHQgc3VicHJvY2Vzcy5UaW1lb3V0RXhwaXJlZDoKICAgICAgICByZXR1cm4gX2ZhaWwoImRvc3NpZXIvdmVyaWZ5X29mZmxpbmUucHkgdGltZWQgb3V0IikKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gX2ZhaWwoImRvc3NpZXIvdmVyaWZ5X29mZmxpbmUucHkgaW52b2NhdGlvbiBlcnJvcjogIiArIHN0cihlKSkKICAgIHN5cy5zdGRvdXQud3JpdGUocHJvYy5zdGRvdXQpCiAgICBpZiBwcm9jLnN0ZGVycjoKICAgICAgICBzeXMuc3RkZXJyLndyaXRlKHByb2Muc3RkZXJyKQogICAgcmMgPSBwcm9jLnJldHVybmNvZGUKICAgIGlmIHJjID09IDI6CiAgICAgICAgcHJpbnQoCiAgICAgICAgICAgICJOT1RFIGlubmVyIGRvc3NpZXIgdmVyaWZpZXIgZXhpdGVkIDIgKEVOVklST05NRU5UKTsgIgogICAgICAgICAgICAiY3J5cHRvICsgYmluZGluZyBnYXRlcyBhYm92ZSBQQVNTRUQiCiAgICAgICAgKQogICAgICAgIHJldHVybiAyCiAgICBpZiByYyA9PSAzOgogICAgICAgIHByaW50KCkKICAgICAgICBwcmludCgKICAgICAgICAgICAgIlZFUkRJQ1Q6IE9VVFNJREUgKC5uZGVjIGRlY2lzaW9uIGF0dGVzdGF0aW9uOiBhdXRoZW50aWMgIgogICAgICAgICAgICAidW5kZXIgdGhlIGV4cGVjdGVkIGtleSwgdGhlIHNvbHZlciB2ZXJkaWN0IGlzIG5vdCBwcm92ZW4pIgogICAgICAgICkKICAgICAgICByZXR1cm4gMwogICAgaWYgcmMgIT0gMDoKICAgICAgICByZXR1cm4gX2ZhaWwoCiAgICAgICAgICAgICJpbm5lciBkb3NzaWVyIHZlcmlmaWVyIHJldHVybmVkICIgKyBzdHIocmMpCiAgICAgICAgICAgICsgIiAodGhlIHByb29mIGFydGlmYWN0cyBkbyBub3QgdmVyaWZ5KSIKICAgICAgICApCgogICAgaWYgbWFuaWZlc3QuZ2V0KCJ2ZXJkaWN0IikgIT0gInByb3ZlbiI6CiAgICAgICAgcHJpbnQoKQogICAgICAgIHByaW50KAogICAgICAgICAgICAiVkVSRElDVDogT1VUU0lERSAoLm5kZWMgZGVjaXNpb24gYXR0ZXN0YXRpb246IHRoZSAiCiAgICAgICAgICAgICJzaWduZWQgbWFuaWZlc3QncyBzb2x2ZXIgdmVyZGljdCBpcyAiCiAgICAgICAgICAgICsgcmVwcihtYW5pZmVzdC5nZXQoInZlcmRpY3QiKSkgKyAiLCBub3QgJ3Byb3ZlbicpIgogICAgICAgICkKICAgICAgICByZXR1cm4gMwogICAgcHJpbnQoKQogICAgcHJpbnQoIlZFUkRJQ1Q6IFBBU1MgKC5uZGVjIGRlY2lzaW9uIGF0dGVzdGF0aW9uKSIpCiAgICBwcmludCgiICB3b3JsZDogICAgICAgICIgKyBzdHIocHJlZGljYXRlLmdldCgid29ybGRfbmFtZSIsICI/IikpKQogICAgcHJpbnQoIiAgdmVyZGljdDogICAgICAiICsgc3RyKHByZWRpY2F0ZS5nZXQoInZlcmRpY3QiLCAiPyIpKSkKICAgIHByaW50KCIgIG5vdXNfdmVyc2lvbjogIiArIHN0cihwcmVkaWNhdGUuZ2V0KCJub3VzX3ZlcnNpb24iLCAiPyIpKSkKICAgIHByaW50KCIgIHByb3ZlczogICAgICAgb25seSB3aGF0IHRoZSBkb3NzaWVyIHZlcmlmaWVyIGFib3ZlICIKICAgICAgICAgICJwcmludGVkIGFzIFBST1ZFTiIpCiAgICBwcmludCgiICBldmlkZW5jZXM6ICAgIHByb3ZlbmFuY2UgKyBpc3N1ZXIgbm9uLXRhbXBlcmluZyIpCiAgICBwcmludCgKICAgICAgICAiICBub3RfY2xhaW1lZDogIGRlY2lzaW9uIGNvcnJlY3RuZXNzLCBsZWdhbCBzdWZmaWNpZW5jeSwgIgogICAgICAgICJjb21wbGlhbmNlIgogICAgKQogICAgcmV0dXJuIDAKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgc3lzLmV4aXQoX3YzX3J1bihtYWluKSkK"
).decode("utf-8")

README_NDEC_TXT: str = base64.b64decode(
    "Tk9VUyAubmRlYyAtLSBQb3J0YWJsZSBQcm9vZi1DYXJyeWluZyBBSS1EZWNpc2lvbiBBdHRlc3RhdGlvbgo9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgpUaGlzIGZpbGUgaXMgYSBaSVAgY29udGFpbmVyLiBJdCB3cmFwcyBhIE5PVVMgZG9zc2llciBpbiBhIHN0YW5kYXJkIERTU0UKZW52ZWxvcGUgb3ZlciBhbiBpbi10b3RvIHYxIFN0YXRlbWVudCwgd2l0aCBhIE5PVVMgcHJvb2YtY2FycnlpbmcgcHJlZGljYXRlLgoKVG8gdmVyaWZ5IG9mZmxpbmUgKG5vIE5PVVMgaW5zdGFsbCBuZWVkZWQ7IHJlcXVpcmVzIHRoZSBjcnlwdG9ncmFwaHkgbGlicmFyeSk6CgogICAgdW56aXAgPGZpbGU+Lm5kZWMgLWQgb3V0CiAgICBjZCBvdXQKICAgIHB5dGhvbjMgLUkgdmVyaWZ5X25kZWMucHkgLS1leHBlY3Qtc2lnbmVyIDxzaWduZXIga2V5LCBiYXNlNjQ+CgpUaGUga2V5IGlzIHRoZSAubmRlYyBzaWduZXIncyByYXcgRWQyNTUxOSBwdWJsaWMga2V5LCB0YWtlbiBvdXQgb2YgYmFuZCwKbm90IGZyb20gdGhpcyBidW5kbGU7IHdpdGhvdXQgaXQgdGhlcmUgaXMgbm8gUEFTUyAoZXhpdCAyKS4gRXhpdCAwID0gUEFTUywKMSA9IElOVEVHUklUWSwgMiA9IEVOVklST05NRU5UIChubyBrZXk7IG9yIGUuZy4gejMgYWJzZW50IGZvciBhbiBTTVQtb25seQpjb3ZlcmFnZSBwcm9vZjsgdGhlIEZhcmthcyBwYXRoIG5lZWRzIG9ubHkgdGhlIHN0ZGxpYiksIDMgPSBPVVRTSURFCihhdXRoZW50aWMsIHRoZSBzb2x2ZXIgdmVyZGljdCBpcyBub3QgcHJvdmVuKS4gVGhlIGxhc3QgbGluZSBvZiBvdXRwdXQKbmFtZXMgdGhlIGNsYXNzLgoKdmVyaWZ5X25kZWMucHkgY2hlY2tzIHRoZSBEU1NFIHNpZ25hdHVyZSwgdGhhdCB0aGUgc3ViamVjdCBkaWdlc3QgYmluZHMgdGhlCmNhcnJpZWQgbWFuaWZlc3QsIGFuZCB0aGF0IGV2ZXJ5IGNhcnJpZWQgYXJ0aWZhY3QgLS0gaW5jbHVkaW5nIHRoZSBkb3NzaWVyCnZlcmlmaWVyICh2ZXJpZnlfb2ZmbGluZS5weSkgLS0gbWF0Y2hlcyB0aGUgc2lnbmVkIHByZWRpY2F0ZSwgdGhlbiBydW5zCmRvc3NpZXIvdmVyaWZ5X29mZmxpbmUucHkuCgpUaGUgZW52ZWxvcGUgaXMgaW50ZXJvcGVyYWJsZSB3aXRoIERTU0UgLyBpbi10b3RvIC8gY29zaWduIHRvb2xpbmcuIFRoZQpndWFyYW50ZWU6IGl0IFBST1ZFUyB0aGUgZGVjbGFyZWQgY29zdC9jb3ZlcmFnZSBlbnZlbG9wZSAoejMgb3IgRmFya2FzKSBhbmQKRVZJREVOQ0VTIHByb3ZlbmFuY2UgYW5kIGlzc3VlciBub24tdGFtcGVyaW5nIChFZDI1NTE5KS4gSXQgZG9lcyBOT1QgcHJvdmUgdGhlCmRlY2lzaW9uIHdhcyBjb3JyZWN0LCB0aGF0IHRoZSBkb3NzaWVyIGlzIGxlZ2FsbHkgc3VmZmljaWVudCwgb3IgdGhhdApyZWd1bGF0b3J5IGNvbXBsaWFuY2UgaXMgY29uZmVycmVkLiBUaGUgc2lnbmVyIGtleSBtdXN0IGVxdWFsIHRoZSBvbmUgeW91CnBhc3M7IHdobyBob2xkcyBpdCBpcyBlc3RhYmxpc2hlZCBvdXQgb2YgYmFuZC4gUnVuIGl0IHdpdGggLUk6IHdpdGhvdXQgaXQKUHl0aG9uIGltcG9ydHMgbW9kdWxlcyBmcm9tIHRoaXMgZGlyZWN0b3J5LCB3aGljaCB0aGUgYnVuZGxlJ3Mgc2VuZGVyCmNvbnRyb2xzLiBXaXRoIG5vdXMtbGFuZyBpbnN0YWxsZWQsIGBub3VzIG5kZWMgdmVyaWZ5IDxmaWxlPi5uZGVjCi0tZXhwZWN0LXNpZ25lciA8a2V5PmAgY2hlY2tzIHRoZSBlbnZlbG9wZSBhbmQgYmluZGluZ3Mgd2l0aCBpbnN0YWxsZWQgY29kZQphbmQgY29uZmlybXMgdGhlIGNhcnJpZWQgZG9zc2llciB2ZXJpZmllciBhZ2FpbnN0IHRoZSBpbnN0YWxsZWQgY2Fub25pY2FsCnRlbXBsYXRlcyBiZWZvcmUgcnVubmluZyBpdCAoaXNvbGF0ZWQpOyBpdCBzdGlsbCBydW5zIGl0Lgo="
).decode("utf-8")

_ARTIFACT_FILES: dict = {
    "manifest_sha256": "manifest.json",
    "source_sha256": "source.nous",
    "pricing_sha256": "pricing.toml",
    "coverage_smt2_sha256": "coverage.smt2",
    "coverage_farkas_sha256": "coverage.farkas.json",
    "cost_farkas_sha256": "cost.farkas.json",  # __s170_leg5a_ndec_cost_v1__
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
        ("cost.farkas.json", "cost_farkas_sha256"),  # __s170_leg5a_ndec_cost_v1__
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
def _try_registry_confirm(registry_path, carried_vsha):  # __s148_u2_registry_helper_v1__
    import sys  # __s148_u2_hotfix_sys_v1__
    if registry_path is None:
        return None
    try:
        import verifier_registry
    except ImportError:
        return None
    try:
        reg = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            "NOTE verifier-digest registry could not be read (" + str(exc)
            + "); not consulted",
            file=sys.stderr,
        )
        return None
    conf = verifier_registry.confirm_digest(
        reg,
        carried_vsha,
        trusted_registry_keys_b64=verifier_registry.KNOWN_REGISTRY_PUBLIC_KEYS_B64,
        require_anchor=True,
    )
    if not conf.confirmed:
        print(
            "NOTE verifier-digest registry supplied but did not confirm the "
            "carried verifier at logged tier: " + conf.reason,
            file=sys.stderr,
        )
    return conf


def verify_ndec_file(ndec_path, *, public_key=None, strict_canonical: bool = False, registry_path=None) -> int:  # __s147_u4_strict_param_v1__  # __s148_u2_registry_param_v1__
    """Installed trusted-path verification of a .ndec file.

    Envelope, subject binding, and artifact binding (including the carried
    dossier verifier, pinned via verify_offline_sha256) are checked by this
    installed module -- not by any bytes carried in the archive. The pinned
    carried verify_offline.py is then executed in a temp extraction as a
    subprocess (process isolation; honours the dossier verifier contract).

    Returns 0 PASS / 1 FAIL / 2 environment-limited / 3 OUTSIDE.
    The inner verifier is pinned (--expect-signer) to the
    manifest's own key only when the auditor supplied
    public_key, which authenticates manifest.json through the
    signed artifact digests.  # __nt_v3_classes_wire_v1__
    """
    import shutil
    import sys

    ndec_path = Path(ndec_path)
    auditor_pinned = public_key is not None  # __nt_v3_classes_wire_v1__
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
        if auditor_pinned:  # __nt_v3_review_v1__
            _why = _v3_signer_fields(envelope, statement, public_key)
            if _why:
                print("verify: " + _why, file=sys.stderr)
                return 1

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
        for _k in ("verify_offline_sha256", "manifest_sha256"):  # __nt_v3_review_v1__
            if not _v3_hex64(artifacts.get(_k)):
                print("verify: predicate " + _k + " is not 64 hex",
                      file=sys.stderr)
                return 1
        if "verify_offline_sha256" not in artifacts:
            print(
                "verify: predicate does not pin verify_offline_sha256",
                file=sys.stderr,
            )
            return 1
        if "manifest_sha256" not in artifacts:  # __nt_v3_ndec_carried_v1__
            print(
                "verify: predicate does not pin manifest_sha256; the "
                "manifest's signer is not bound by the signature",
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
        registry_conf = None  # __s148_u2_registry_conf_init_v1__
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
            registry_conf = _try_registry_confirm(  # __s148_u2_registry_attempt_v1__
                registry_path, carried_vsha
            )
            if registry_conf is not None and registry_conf.confirmed:
                print(
                    "OK   verify_offline.py confirmed via verifier-digest "
                    "registry (" + str(registry_conf.template_name) + "@"
                    + str(registry_conf.nous_version) + ", tier="
                    + str(registry_conf.tier) + "); publicly logged, "
                    "append-only -- trusting-trust closed across versions"
                )
            elif strict_canonical:
                print(
                    "verify: carried verify_offline.py is not in this "
                    "installed version's canonical verifier set and "
                    "--strict-canonical is set; refused",
                    file=sys.stderr,
                )
                return 1
            else:
                print(
                    "NOTE verify_offline.py is NOT in this installed "
                    "version's canonical verifier set (different NOUS "
                    "version or non-canonical); it remains bound by the "
                    "signed predicate, but trusting-trust is NOT closed -- "
                    "trust reduces to the signer key plus the pin"
                )
        if not auditor_pinned:  # __nt_v3_review_v1__
            print(
                "NOTE no auditor key: run nous ndec verify FILE "
                "--expect-signer BASE64 with the .ndec signer's "
                "key; without it there is no PASS (exit 2)"
            )
            return 2
        inner = _v3_inner_args(man)
        if not inner:
            print("verify: dossier/manifest.json carries no valid "
                  "signer key", file=sys.stderr)
            return 1
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", str(verifier)]
                + inner,  # __nt_v3_classes_wire_v1__
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
        if rc == 3:  # __nt_v3_classes_wire_v1__
            print(
                "VERDICT: OUTSIDE (.ndec via installed verifier: "
                "authentic, the solver verdict is not proven)"
            )
            return 3
        if rc != 0:
            print(
                "verify: inner dossier verifier returned " + str(rc),
                file=sys.stderr,
            )
            return 1
        if man.get("verdict") != "proven":  # __nt_v3_review_v1__
            print(
                "VERDICT: OUTSIDE (.ndec via installed verifier: the "
                "signed manifest's solver verdict is "
                + repr(man.get("verdict")) + ", not 'proven')"
            )
            return 3
        predicate = statement.get("predicate", {})
        print()
        print("VERDICT: PASS (.ndec via installed verifier)")
        print("  world:        " + str(predicate.get("world_name", "?")))
        print("  verdict:      " + str(predicate.get("verdict", "?")))
        print("  nous_version: " + str(predicate.get("nous_version", "?")))
        print("  proves:       only what the dossier verifier above "
              "printed as PROVEN")  # __nt_v3_review_v1__
        print("  evidences:    provenance + issuer non-tampering")
        # __s147_u4_verifier_footer_v1__
        if canon_name:  # __s148_u2_footer_v1__
            _vstate = "canonical:" + canon_name
        elif registry_conf is not None and registry_conf.confirmed:
            _vstate = (
                "registry:" + str(registry_conf.tier) + ":"
                + str(registry_conf.template_name) + "@"
                + str(registry_conf.nous_version)
            )
        else:
            _vstate = "signature-pinned (not confirmed canonical)"
        print("  verifier:     " + _vstate)
        print(
            "  not_claimed:  decision correctness, legal sufficiency, "
            "compliance"
        )
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _v3_inner_args(man):  # __nt_v3_classes_wire_v1__
    """--expect-signer for the inner dossier verifier: the
    manifest's own key, bound by the auditor-pinned envelope
    through manifest_sha256; [] unless it is base64 of 32 bytes."""
    if not isinstance(man, dict):
        return []
    sig = man.get("signature")
    pub = sig.get("public_key_b64") if isinstance(sig, dict) else None
    if not isinstance(pub, str) or not pub:
        return []
    try:  # __nt_v3_review_v1__
        if len(base64.b64decode(pub, validate=True)) != 32:
            return []
    except (binascii.Error, ValueError):
        return []
    return ["--expect-signer", pub]


def _v3_hex64(value):  # __nt_v3_review_v1__
    return isinstance(value, str) and re.fullmatch(
        "[0-9a-f]{64}", value) is not None


def _v3_signer_fields(envelope, statement, public_key):  # __nt_v3_review_v1__
    """With the auditor's key: the predicate names that key and the
    envelope's keyid is its sha256. Returns "" or the reason."""
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    named = statement.get("predicate", {}).get("signer_public_key_b64")
    if named != base64.b64encode(raw).decode("ascii"):
        return "predicate signer is not the expected key"
    sigs = envelope.get("signatures") or [{}]
    if not isinstance(sigs[0], dict) or sigs[0].get("keyid") != \
            hashlib.sha256(raw).hexdigest():
        return "envelope keyid is not sha256 of the expected key"
    return ""


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
