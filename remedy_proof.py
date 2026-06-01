"""S109 U2 -- typed RemedyProof consumption view (parse-on-read).

A remedy_proof is ADVISORY-BUT-AUTHENTICATED. The embedded conformance
certificate, re-verified by the EXISTING S97/v5.13 offline verifier, proves only
two things: that a conformant run of a specific program happened (the cert binds
source_sha256 + smt_spec_sha256 + pricing_sha256 + trace_sha256, all signed), and
-- together with U3's program-declaration check -- that the promoted heal-path is
a rule the current program declares.

It does NOT prove that this heal-path was the path that executed in that run: the
signed trace records no heal-path (verified against live nous_trace.TraceEvent --
fields are seq, tick, soul, kind, tokens, tool_cost, action, authorization,
timestamp; none carries a heal digest). Admissibility does not require run-binding.
Promotion (Phase 2.0) selects among already-declared, closure-conformant
recoveries; an undeclared digest is rejected by the program-declaration check
(U3), and a declared one is legal by the static-envelope closure proof regardless
of which path historically ran. The boundary is therefore: the proof binds
"a conformant run of this program happened" and "the promoted heal-path is
declared by this program", NOT "this heal-path executed in that run".

This module is a CONSUMPTION VIEW only. MemoryEntry.remedy_proof stays
Optional[dict] (untyped) so existing v1 entry signatures are preserved
bit-for-bit; this view is parsed FROM that dict on read and never re-types the
stored field. The embedded certificate is carried as a verbatim dict, never
re-typed through Pydantic, because re-typing could reorder keys or coerce fields,
change certificate_canonical_body_bytes, and break the embedded Ed25519
signature. Parsing is fail-closed (refuse-over-guess): any malformed input, any
missing certificate key the offline verifier needs, raises RemedyProofError
before the proof reaches any verifier.

# __s109_u2_remedy_proof_module_v1__
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

REMEDY_PROOF_SCHEMA_VERSION: int = 1

_HEX64 = 64

_REQUIRED_CERTIFICATE_KEYS: tuple[str, ...] = (
    "source_sha256",
    "smt_spec_sha256",
    "pricing_sha256",
    "trace_sha256",
    "signature",
)


class RemedyProofError(RuntimeError):
    """Raised when a stored remedy_proof dict cannot be parsed into a
    RemedyProof view. The message starts with the cause."""


def _is_hex64(value: object) -> bool:
    if not isinstance(value, str) or len(value) != _HEX64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class RemedyProof(BaseModel):
    """Typed, frozen, strict parse-on-read view over a stored remedy_proof dict.

    Never constructed directly from untrusted bytes in production; use
    from_stored(), which validates fail-closed."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    remedy_proof_schema_version: int = Field(default=REMEDY_PROOF_SCHEMA_VERSION)
    promoted_heal_path_sha256: str = Field(min_length=_HEX64, max_length=_HEX64)
    certificate: dict

    @classmethod
    def from_stored(cls, stored: object) -> "RemedyProof":
        if not isinstance(stored, dict):
            raise RemedyProofError(
                "remedy_proof must be a dict, got " + type(stored).__name__
            )

        allowed = {
            "remedy_proof_schema_version",
            "promoted_heal_path_sha256",
            "certificate",
        }
        extra = set(stored.keys()) - allowed
        if extra:
            raise RemedyProofError(
                "unexpected remedy_proof keys: " + repr(sorted(extra))
            )

        version = stored.get(
            "remedy_proof_schema_version", REMEDY_PROOF_SCHEMA_VERSION
        )
        if not isinstance(version, int) or isinstance(version, bool):
            raise RemedyProofError(
                "remedy_proof_schema_version must be an int"
            )
        if version != REMEDY_PROOF_SCHEMA_VERSION:
            raise RemedyProofError(
                "unsupported remedy_proof_schema_version: " + repr(version)
            )

        digest = stored.get("promoted_heal_path_sha256")
        if not _is_hex64(digest):
            raise RemedyProofError(
                "promoted_heal_path_sha256 must be 64 lowercase-or-upper hex chars"
            )

        certificate = stored.get("certificate")
        if not isinstance(certificate, dict):
            raise RemedyProofError(
                "certificate must be a dict, got " + type(certificate).__name__
            )
        missing = [
            key for key in _REQUIRED_CERTIFICATE_KEYS if key not in certificate
        ]
        if missing:
            raise RemedyProofError(
                "certificate missing keys the offline verifier requires: "
                + repr(missing)
            )
        signature = certificate.get("signature")
        if not isinstance(signature, dict):
            raise RemedyProofError(
                "certificate.signature must be a dict (signed certificate "
                "required); got " + type(signature).__name__
            )

        return cls(
            remedy_proof_schema_version=version,
            promoted_heal_path_sha256=digest,
            certificate=certificate,
        )
