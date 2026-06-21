from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import provenance_verifier as pv

DSSE_PT = "application/vnd.in-toto+json"
WHEEL = "nous_lang-5.58.0-py3-none-any.whl"
SDIST = "nous_lang-5.58.0.tar.gz"
ENV_NAME = "nous_lang-5.58.0.provenance.intoto.json"


def _pub_b64(priv: Ed25519PrivateKey) -> str:
    raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode()


def _pae(pt: str, payload: bytes) -> bytes:
    p = pt.encode()
    return (
        b"DSSEv1 "
        + str(len(p)).encode()
        + b" "
        + p
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def _make_env(
    priv: Ed25519PrivateKey,
    wheel_sha: str,
    sdist_sha: str,
    good_sig: bool = True,
) -> bytes:
    stmt = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": WHEEL, "digest": {"sha256": wheel_sha}},
            {"name": SDIST, "digest": {"sha256": sdist_sha}},
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {"buildType": "fixture"},
            "runDetails": {
                "builder": {
                    "id": "https://nous-lang.org/builders/release-script-adhoc/v1"
                },
                "metadata": {
                    "invocationId": "fix-1",
                    "startedOn": "2026-06-20T11:52:04Z",
                },
            },
        },
    }
    payload = json.dumps(stmt, sort_keys=True, separators=(",", ":")).encode()
    sig = priv.sign(_pae(DSSE_PT, payload)) if good_sig else bytes(64)
    return json.dumps(
        {
            "payloadType": DSSE_PT,
            "payload": base64.b64encode(payload).decode(),
            "signatures": [
                {"keyid": "hint", "sig": base64.b64encode(sig).decode()}
            ],
        },
        separators=(",", ":"),
    ).encode()


def _run(verifier: Path, search: Path | None = None):
    args = [sys.executable, str(verifier)]
    if search is not None:
        args.append(str(search))
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


@pytest.fixture()
def keyed(tmp_path):
    priv = Ed25519PrivateKey.generate()
    pk = _pub_b64(priv)
    wheel = b"WHEELBYTES\n" * 64
    sdist = b"SDISTBYTES\n" * 96
    wsha = hashlib.sha256(wheel).hexdigest()
    ssha = hashlib.sha256(sdist).hexdigest()
    return priv, pk, wheel, sdist, wsha, ssha


def test_emit_byte_equals_template_with_pin():
    priv = Ed25519PrivateKey.generate()
    pk = _pub_b64(priv)
    emitted = pv.emit_provenance_verifier(pk)
    expected = pv.PROVENANCE_VERIFY_OFFLINE_PY.replace(
        pv.BUILDER_PIN_PLACEHOLDER, pk
    )
    assert emitted == expected
    assert pv.BUILDER_PIN_PLACEHOLDER not in emitted
    assert emitted.startswith("#!/usr/bin/env python3\n")


def test_emit_rejects_invalid_keys():
    for bad in ("", "not-base64!!", base64.b64encode(b"short").decode()):
        with pytest.raises(pv.ProvenanceVerifierError):
            pv.emit_provenance_verifier(bad)


def test_template_has_exactly_one_placeholder():
    assert (
        pv.PROVENANCE_VERIFY_OFFLINE_PY.count(pv.BUILDER_PIN_PLACEHOLDER) == 1
    )


def test_emitted_verifier_compiles():
    pk = _pub_b64(Ed25519PrivateKey.generate())
    src = pv.emit_provenance_verifier(pk)
    compile(src, "verify_provenance_offline.py", "exec")


def test_pass_both_subjects(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel)
    (d / SDIST).write_bytes(sdist)
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 0, (out, err)
    assert "VERDICT: PASS" in out
    assert "subjects confirmed (2)" in out


def test_pass_one_subject_other_asserted(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / SDIST).write_bytes(sdist)
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 0, (out, err)
    assert "subjects confirmed (1)" in out
    assert "asserted, not re-derived (1)" in out


def test_fail_tampered_subject(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel + b"TAMPER")
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 1
    assert "does NOT match" in err


def test_fail_bad_signature(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel)
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha, good_sig=False))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 1
    assert "does NOT verify" in err


def test_fail_wrong_key(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel)
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    other = _pub_b64(Ed25519PrivateKey.generate())
    v.write_text(pv.emit_provenance_verifier(other))
    rc, out, err = _run(v)
    assert rc == 1
    assert "does NOT verify" in err


def test_incomplete_no_subjects_present(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 2
    assert "INCOMPLETE" in err
    assert "VERDICT: PASS" not in out


def test_env_unprovisioned_template_exits_2(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel)
    (d / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.PROVENANCE_VERIFY_OFFLINE_PY)  # placeholder intact
    rc, out, err = _run(v)
    assert rc == 2
    assert "not provisioned with a builder key" in err


def test_missing_envelope_exits_2(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    (d / WHEEL).write_bytes(wheel)
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v)
    assert rc == 2
    assert "no *.provenance.intoto.json" in err


def test_argv_search_dir_override(keyed):
    priv, pk, wheel, sdist, wsha, ssha = keyed
    d = Path(tempfile.mkdtemp())
    art = Path(tempfile.mkdtemp())
    (art / WHEEL).write_bytes(wheel)
    (art / SDIST).write_bytes(sdist)
    (art / ENV_NAME).write_bytes(_make_env(priv, wsha, ssha))
    v = d / "verify_provenance_offline.py"
    v.write_text(pv.emit_provenance_verifier(pk))
    rc, out, err = _run(v, search=art)
    assert rc == 0, (out, err)
    assert "subjects confirmed (2)" in out
