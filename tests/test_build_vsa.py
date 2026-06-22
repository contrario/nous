from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import build_vsa as bv

WHL = b"WHEEL-BYTES-5.60.1"
SD = b"SDIST-BYTES-5.60.1"
WHL_NAME = "nous_lang-5.60.1-py3-none-any.whl"
SD_NAME = "nous_lang-5.60.1.tar.gz"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ext() -> dict:
    return {
        "boundary": (
            "evidences operator endorsement; federation legs named not "
            "re-derived offline"
        ),
        "verifierRole": "release-operator (federation delegate)",
    }


def _valid_statement() -> dict:
    return bv.assemble_build_vsa_statement(
        subjects=[
            {"name": WHL_NAME, "sha256": _sha(WHL)},
            {"name": SD_NAME, "sha256": _sha(SD)},
        ],
        input_attestations=[
            {
                "uri": "https://api.github.com/repos/contrario/nous/"
                "attestations/sha256:" + _sha(WHL),
                "sha256": "a" * 64,
            },
            {
                "uri": "https://pypi.org/integrity/nous-lang/5.60.1/"
                + WHL_NAME
                + "/provenance",
                "sha256": "b" * 64,
            },
        ],
        verified_levels=["SLSA_BUILD_LEVEL_2"],
        ext=_ext(),
        resource_uri="pkg:pypi/nous-lang@5.60.1",
        time_verified="2026-06-22T01:00:00Z",
    )


def test_policy_fingerprint_stable_and_recomputable():
    fp = bv.build_policy_fingerprint()
    assert len(fp) == 64 and int(fp, 16) >= 0
    obj = {
        "policy_id": bv.POLICY_ID,
        "requires": sorted(bv._POLICY_REQUIRES),
        "version": 1,
    }
    expect = hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert fp == expect


def test_assemble_structure():
    stmt = _valid_statement()
    assert stmt["_type"] == bv.IN_TOTO_STATEMENT_TYPE
    assert stmt["predicateType"] == bv.VSA_PREDICATE_TYPE
    pred = stmt["predicate"]
    assert pred["verifier"]["id"] == bv.NOUS_RELEASE_VERIFIER_ID
    assert pred["policy"]["digest"]["sha256"] == bv.build_policy_fingerprint()
    assert pred["verificationResult"] == "PASSED"
    assert pred["verifiedLevels"] == ["SLSA_BUILD_LEVEL_2"]
    assert pred["slsaVersion"] == bv.SLSA_VERSION
    assert pred[bv.NOUS_BUILD_VSA_EXT_KEY]["verifierRole"]
    assert stmt["subject"][0]["digest"]["sha256"] == _sha(WHL)


def test_assemble_is_deterministic():
    a = bv._canon(_valid_statement())
    b = bv._canon(_valid_statement())
    assert a == b


@pytest.mark.parametrize(
    "mutate",
    [
        lambda kw: kw.update(subjects=[]),
        lambda kw: kw.update(
            subjects=[{"name": WHL_NAME, "sha256": "xyz"}]
        ),
        lambda kw: kw.update(subjects=[{"name": "", "sha256": "a" * 64}]),
        lambda kw: kw.update(input_attestations=[]),
        lambda kw: kw.update(
            input_attestations=[{"uri": "u", "sha256": "short"}]
        ),
        lambda kw: kw.update(verified_levels=[]),
        lambda kw: kw.update(verified_levels=[123]),
        lambda kw: kw.update(ext="not-a-dict"),
        lambda kw: kw.update(resource_uri=""),
        lambda kw: kw.update(time_verified=""),
    ],
)
def test_assemble_refuses_malformed(mutate):
    kw = dict(
        subjects=[{"name": WHL_NAME, "sha256": _sha(WHL)}],
        input_attestations=[{"uri": "u", "sha256": "a" * 64}],
        verified_levels=["SLSA_BUILD_LEVEL_2"],
        ext=_ext(),
        resource_uri="pkg:pypi/nous-lang@5.60.1",
        time_verified="2026-06-22T01:00:00Z",
    )
    mutate(kw)
    with pytest.raises(bv.BuildVsaError):
        bv.assemble_build_vsa_statement(**kw)


def test_sign_envelope_shape_and_seed_guard():
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    env = bv.sign_build_vsa(_valid_statement(), seed)
    assert env["payloadType"] == bv.DSSE_PAYLOAD_TYPE
    assert env["signatures"] and env["signatures"][0]["sig"]
    payload = base64.b64decode(env["payload"])
    assert json.loads(payload)["predicateType"] == bv.VSA_PREDICATE_TYPE
    with pytest.raises(bv.BuildVsaError):
        bv.sign_build_vsa(_valid_statement(), b"short-seed")


@pytest.mark.parametrize(
    "bad", ["__NOUS_RELEASE_PINNED_PUBKEY_B64__", "", "not!base64!", None]
)
def test_emit_refuses_bad_pin(bad):
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(bv.BuildVsaError):
            bv.emit_build_vsa_verifier(d, bad)


def test_emit_refuses_wrong_length_key():
    short = base64.b64encode(b"\x01" * 16).decode()
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(bv.BuildVsaError):
            bv.emit_build_vsa_verifier(d, short)


def _emit_and_run(d, seed_for_sign, pin_pub, write_files=True):
    env = bv.sign_build_vsa(_valid_statement(), seed_for_sign)
    with open(os.path.join(d, "build-vsa.intoto.json"), "w") as f:
        json.dump(env, f)
    if write_files:
        with open(os.path.join(d, WHL_NAME), "wb") as f:
            f.write(WHL)
        with open(os.path.join(d, SD_NAME), "wb") as f:
            f.write(SD)
    bv.emit_build_vsa_verifier(d, pin_pub)
    r = subprocess.run(
        [sys.executable, os.path.join(d, "verify_build_vsa_offline.py"), d],
        capture_output=True,
        text=True,
    )
    return r


def test_end_to_end_emitted_verifier_pass():
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    pub = base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes_raw()
    ).decode()
    with tempfile.TemporaryDirectory() as d:
        r = _emit_and_run(d, seed, pub)
        assert r.returncode == 0, r.stderr
        assert "VERDICT: PASS" in r.stdout
        # the emitted verifier left no sentinel
        emitted = open(os.path.join(d, "verify_build_vsa_offline.py")).read()
        assert "__NOUS_RELEASE_PINNED_PUBKEY_B64__" not in emitted


def test_end_to_end_wrong_pin_fails():
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    other_pub = base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    ).decode()
    with tempfile.TemporaryDirectory() as d:
        r = _emit_and_run(d, seed, other_pub)
        assert r.returncode == 1
        assert "does NOT verify" in r.stderr


def test_emitted_verifier_policy_matches_module():
    # the embedded verifier must recompute the SAME policy fingerprint
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    pub = base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes_raw()
    ).decode()
    with tempfile.TemporaryDirectory() as d:
        bv.emit_build_vsa_verifier(d, pub)
        src = open(os.path.join(d, "verify_build_vsa_offline.py")).read()
        import importlib.util

        p = os.path.join(d, "verify_build_vsa_offline.py")
        spec = importlib.util.spec_from_file_location("vbvo", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        assert m._policy_fingerprint() == bv.build_policy_fingerprint()
        assert bv.RELEASE_PIN_PLACEHOLDER not in src
