"""S109 U2 -- tests for the RemedyProof parse-on-read view.

Covers: happy-path parse from a real embedded certificate; fail-closed refusals
on every malformed shape (not-a-dict, extra keys, bad version, bad digest,
missing certificate, missing required certificate key, unsigned certificate);
verbatim certificate preservation (no re-typing); and the documented boundary
that the proof is program-bound, not run-bound (no assertion that the digest
matches anything inside the trace -- that binding does not exist).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from remedy_proof import (
    REMEDY_PROOF_SCHEMA_VERSION,
    RemedyProof,
    RemedyProofError,
)

_CERT_PATH = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "demos"
    / "cert-4679350"
    / "conformance.json"
)


def _real_cert() -> dict:
    return json.loads(_CERT_PATH.read_text(encoding="utf-8"))


def _valid_stored() -> dict:
    return {
        "remedy_proof_schema_version": REMEDY_PROOF_SCHEMA_VERSION,
        "promoted_heal_path_sha256": "b" * 64,
        "certificate": _real_cert(),
    }


def test_happy_path_parse() -> None:
    proof = RemedyProof.from_stored(_valid_stored())
    assert proof.promoted_heal_path_sha256 == "b" * 64
    assert proof.remedy_proof_schema_version == REMEDY_PROOF_SCHEMA_VERSION


def test_certificate_carried_verbatim() -> None:
    cert = _real_cert()
    stored = {
        "remedy_proof_schema_version": 1,
        "promoted_heal_path_sha256": "a" * 64,
        "certificate": cert,
    }
    proof = RemedyProof.from_stored(stored)
    assert proof.certificate == cert
    assert proof.certificate.get("signature") == cert.get("signature")


def test_version_defaults_when_absent() -> None:
    stored = {
        "promoted_heal_path_sha256": "c" * 64,
        "certificate": _real_cert(),
    }
    proof = RemedyProof.from_stored(stored)
    assert proof.remedy_proof_schema_version == REMEDY_PROOF_SCHEMA_VERSION


def test_refuse_not_a_dict() -> None:
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored("not a dict")


def test_refuse_extra_keys() -> None:
    stored = _valid_stored()
    stored["rogue"] = 1
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_bad_version() -> None:
    stored = _valid_stored()
    stored["remedy_proof_schema_version"] = 999
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_bool_version() -> None:
    stored = _valid_stored()
    stored["remedy_proof_schema_version"] = True
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_bad_digest_length() -> None:
    stored = _valid_stored()
    stored["promoted_heal_path_sha256"] = "abc"
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_non_hex_digest() -> None:
    stored = _valid_stored()
    stored["promoted_heal_path_sha256"] = "g" * 64
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_missing_certificate() -> None:
    stored = {
        "remedy_proof_schema_version": 1,
        "promoted_heal_path_sha256": "b" * 64,
    }
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_certificate_not_dict() -> None:
    stored = _valid_stored()
    stored["certificate"] = "not a dict"
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_certificate_missing_required_key() -> None:
    cert = _real_cert()
    del cert["trace_sha256"]
    stored = {
        "remedy_proof_schema_version": 1,
        "promoted_heal_path_sha256": "b" * 64,
        "certificate": cert,
    }
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_refuse_unsigned_certificate() -> None:
    cert = _real_cert()
    cert["signature"] = None
    stored = {
        "remedy_proof_schema_version": 1,
        "promoted_heal_path_sha256": "b" * 64,
        "certificate": cert,
    }
    with pytest.raises(RemedyProofError):
        RemedyProof.from_stored(stored)


def test_frozen_view() -> None:
    proof = RemedyProof.from_stored(_valid_stored())
    with pytest.raises(Exception):
        proof.promoted_heal_path_sha256 = "d" * 64
