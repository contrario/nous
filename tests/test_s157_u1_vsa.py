"""S157 U1 -- NOUS VSA module tests.  # __s157_u1_vsa_test_v1__"""
from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

import pytest

import vsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

_CODEGEN = "a" * 64
_SOURCE = "b" * 64
_MANIFEST = "c" * 64
_TRACE = "d" * 64
_CERT = "e" * 64
_FARKAS = "f" * 64


def _stmt(**over):
    base = dict(
        world_name="alpha",
        nous_version="5.55.0",
        issued_utc="2026-06-19T11:00:00Z",
        codegen_sha256=_CODEGEN,
        source_sha256=_SOURCE,
        manifest_canonical_sha256=_MANIFEST,
        trace_canonical_sha256=_TRACE,
        certificate_canonical_sha256=_CERT,
        conformant=True,
        errors=(),
        certificate_schema_version=4,
    )
    base.update(over)
    return vsa.build_vsa_statement(**base)


def test_statement_envelope_constants():
    s = _stmt()
    assert s["_type"] == "https://in-toto.io/Statement/v1"
    assert s["predicateType"] == "https://slsa.dev/verification_summary/v1"
    assert s["predicate"]["slsaVersion"] == "1.1"
    assert s["predicate"]["verifier"]["id"] == vsa.NOUS_VSA_VERIFIER_ID


def test_subject_digest_prefers_codegen():
    s = _stmt()
    assert s["subject"][0]["digest"]["sha256"] == _CODEGEN
    ext = s["predicate"][vsa.NOUS_EXT_KEY]
    assert ext["subjectDigestKind"] == "codegen_sha256"


def test_subject_digest_falls_back_to_source():
    s = _stmt(codegen_sha256=None)
    assert s["subject"][0]["digest"]["sha256"] == _SOURCE
    ext = s["predicate"][vsa.NOUS_EXT_KEY]
    assert ext["subjectDigestKind"] == "source_sha256"


def test_dependency_levels_omitted():
    s = _stmt()
    assert "dependencyLevels" not in s["predicate"]


def test_verified_levels_passed_vs_failed():
    assert _stmt(conformant=True)["predicate"]["verifiedLevels"] == [
        vsa.NOUS_CONFORMANT_LEVEL
    ]
    assert _stmt(conformant=False)["predicate"]["verifiedLevels"] == []
    assert (
        _stmt(conformant=True)["predicate"]["verificationResult"] == "PASSED"
    )
    assert (
        _stmt(conformant=False)["predicate"]["verificationResult"] == "FAILED"
    )


def test_input_attestations_three_without_coverage():
    s = _stmt()
    uris = [a["uri"] for a in s["predicate"]["inputAttestations"]]
    assert uris == ["manifest.json", "trace.json", "conformance.json"]


def test_coverage_proof_present_only_when_supplied():
    s_no = _stmt()
    assert "coverageProof" not in s_no["predicate"][vsa.NOUS_EXT_KEY]
    s_yes = _stmt(
        coverage_farkas_sha256=_FARKAS,
        coverage_farkas_doc={
            "fragment": "linear-real-single-comparison",
            "contradiction": "1 < 0",
        },
    )
    cp = s_yes["predicate"][vsa.NOUS_EXT_KEY]["coverageProof"]
    assert cp["method"] == "PROVES"
    assert cp["sha256"] == _FARKAS
    assert cp["fragment"] == "linear-real-single-comparison"
    uris = [a["uri"] for a in s_yes["predicate"]["inputAttestations"]]
    assert "coverage.farkas.json" in uris


def test_policy_violations_present_only_when_failed():
    s_ok = _stmt(conformant=True, errors=("x: bad",))
    assert "policyViolations" not in s_ok["predicate"][vsa.NOUS_EXT_KEY]
    s_bad = _stmt(
        conformant=False,
        errors=("codegen_binding: trace != manifest", "surface: extra"),
    )
    pv = s_bad["predicate"][vsa.NOUS_EXT_KEY]["policyViolations"]
    assert [v["name"] for v in pv] == ["codegen_binding", "surface"]


def test_obligation_methods_all_evidences():
    ext = _stmt()["predicate"][vsa.NOUS_EXT_KEY]
    methods = ext["obligationMethods"]
    assert set(methods) == set(vsa.OBLIGATION_NAMES)
    assert all(v == "EVIDENCES" for v in methods.values())


def test_policy_digest_deterministic_and_schema_bound():
    a = vsa.policy_digest(4)
    b = vsa.policy_digest(4)
    c = vsa.policy_digest(3)
    assert a == b
    assert a != c
    assert s_has(_stmt()["predicate"]["policy"]["digest"]["sha256"])


def s_has(value):
    return isinstance(value, str) and len(value) == 64


def test_pae_exact_bytes():
    body = b"hello world"
    out = vsa._pae("application/vnd.in-toto+json", body)
    expected = (
        b"DSSEv1 28 application/vnd.in-toto+json 11 hello world"
    )
    assert out == expected


def test_sign_verify_roundtrip():
    priv = Ed25519PrivateKey.generate()
    s = _stmt()
    env = vsa.sign_vsa(s, priv)
    assert env["payloadType"] == "application/vnd.in-toto+json"
    got = vsa.verify_vsa_envelope(env, priv.public_key())
    assert got == s


def test_verify_rejects_tampered_payload():
    priv = Ed25519PrivateKey.generate()
    env = vsa.sign_vsa(_stmt(), priv)
    raw = base64.b64decode(env["payload"])
    tampered = bytearray(raw)
    tampered[0] ^= 0x01
    env["payload"] = base64.b64encode(bytes(tampered)).decode("ascii")
    with pytest.raises(vsa.VSAError):
        vsa.verify_vsa_envelope(env, priv.public_key())


def test_verify_rejects_wrong_key():
    priv = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    env = vsa.sign_vsa(_stmt(), priv)
    with pytest.raises(vsa.VSAError):
        vsa.verify_vsa_envelope(env, other.public_key())


def test_verify_parses_same_verified_bytes():
    priv = Ed25519PrivateKey.generate()
    s = _stmt()
    env = vsa.sign_vsa(s, priv)
    verified = vsa.verify_vsa_envelope(env, priv.public_key())
    assert vsa._canon(verified) == base64.b64decode(env["payload"])


def test_verify_rejects_bad_payload_type():
    priv = Ed25519PrivateKey.generate()
    env = vsa.sign_vsa(_stmt(), priv)
    env["payloadType"] = "application/json"
    with pytest.raises(vsa.VSAError):
        vsa.verify_vsa_envelope(env, priv.public_key())


def test_keypair_create_then_load(tmp_path):
    kp = tmp_path / "vsa_signing.key"
    priv1, pub1, path1 = vsa.load_or_create_vsa_keypair(kp)
    assert path1 == kp
    assert kp.is_file()
    mode = stat.S_IMODE(os.stat(kp).st_mode)
    assert mode == 0o600
    priv2, pub2, _ = vsa.load_or_create_vsa_keypair(kp)
    assert vsa.public_key_raw_b64(pub1) == vsa.public_key_raw_b64(pub2)


def test_keyid_is_sha256_of_raw_pub():
    priv = Ed25519PrivateKey.generate()
    kid = vsa.vsa_keyid(priv.public_key())
    assert isinstance(kid, str) and len(kid) == 64
