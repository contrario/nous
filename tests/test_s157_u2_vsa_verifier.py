"""S157 U2 -- NOUS VSA offline verifier tests (materialize + subprocess).
# __s157_u2_vsa_verifier_test_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

import vsa
import vsa_verifier

_FARKAS = {
    "fragment": "linear-real-single-comparison",
    "constraints": [
        {"coeffs": {"": "1", "x": "1"}, "strict": False},
        {"coeffs": {"": "1", "x": "-1"}, "strict": False},
    ],
    "multipliers": ["1", "1"],
    "contradiction": "2 < 0",
}


def _pub_b64(priv):
    raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _manifest_canon(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _trace_canon(doc):
    body = {k: v for k, v in doc.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _cert_canon(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _sign(doc, priv, canon, algorithm=True):
    sig = priv.sign(canon(doc))
    block = {
        "public_key_b64": _pub_b64(priv),
        "signature_b64": base64.b64encode(sig).decode("ascii"),
    }
    if algorithm:
        block["algorithm"] = "ed25519"
    out = dict(doc)
    out["signature"] = block
    return out


def _run(dirp):
    r = subprocess.run(
        [sys.executable, str(dirp / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(dirp),
    )
    return r.returncode, r.stdout, r.stderr


def _bundle(dirp, *, conformant=True, with_coverage=True, codegen=True):
    mk = Ed25519PrivateKey.generate()
    tk = Ed25519PrivateKey.generate()
    ck = Ed25519PrivateKey.generate()
    vk = Ed25519PrivateKey.generate()
    src, smt, pri, cg = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    far_bytes = json.dumps(
        _FARKAS, sort_keys=True, separators=(",", ":")
    ).encode()
    far_sha = hashlib.sha256(far_bytes).hexdigest()

    manifest = {
        "world_name": "alpha", "source_sha256": src,
        "smt_spec_sha256": smt, "pricing_sha256": pri,
    }
    if codegen:
        manifest["codegen_sha256"] = cg
    if with_coverage:
        manifest["coverage_farkas_sha256"] = far_sha
    manifest = _sign(manifest, mk, _manifest_canon, algorithm=False)

    trace = {"world_name": "alpha"}
    if codegen:
        trace["codegen_sha256"] = cg
    trace = _sign(trace, tk, _trace_canon)
    trace_sha = hashlib.sha256(_trace_canon(trace)).hexdigest()

    bools = {b: True for b in vsa.OBLIGATION_NAMES}
    if not conformant:
        bools["surface_ok"] = False
    cert = {
        "certificate_schema_version": 4, "nous_version": "5.55.0",
        "world_name": "alpha", "issued_utc": "2026-06-19T11:00:00Z",
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
        "trace_sha256": trace_sha, "conformant": all(bools.values()),
        "errors": [] if conformant else ["surface: extra surface"],
    }
    cert.update(bools)
    if codegen:
        cert["codegen_sha256"] = cg
    cert = _sign(cert, ck, _cert_canon)

    man_sha = hashlib.sha256(_manifest_canon(manifest)).hexdigest()
    cert_sha = hashlib.sha256(_cert_canon(cert)).hexdigest()

    stmt = vsa.build_vsa_statement(
        world_name="alpha", nous_version="5.55.0",
        issued_utc="2026-06-19T11:00:00Z",
        codegen_sha256=(cg if codegen else None), source_sha256=src,
        manifest_canonical_sha256=man_sha, trace_canonical_sha256=trace_sha,
        certificate_canonical_sha256=cert_sha, conformant=all(bools.values()),
        errors=tuple(cert["errors"]), certificate_schema_version=4,
        coverage_farkas_sha256=(far_sha if with_coverage else None),
        coverage_farkas_doc=(_FARKAS if with_coverage else None),
    )
    env = vsa.sign_vsa(stmt, vk)

    dirp.mkdir(parents=True, exist_ok=True)
    (dirp / "manifest.json").write_text(json.dumps(manifest))
    (dirp / "trace.json").write_text(json.dumps(trace))
    (dirp / "conformance.json").write_text(json.dumps(cert))
    (dirp / "vsa.intoto.json").write_text(json.dumps(env))
    if with_coverage:
        (dirp / "coverage.farkas.json").write_bytes(far_bytes)
    return vk, env, stmt


def test_positive_pass(tmp_path):
    vk, _, _ = _bundle(tmp_path)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 0, err
    assert "VERDICT: PASS" in out
    assert "PROVEN offline" in out


def test_lying_verification_result_rejected(tmp_path):
    vk, _, _ = _bundle(tmp_path, conformant=False)
    env = json.loads((tmp_path / "vsa.intoto.json").read_text())
    payload = json.loads(base64.b64decode(env["payload"]).decode())
    payload["predicate"]["verificationResult"] = "PASSED"
    new_payload = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()
    env["payload"] = base64.b64encode(new_payload).decode("ascii")
    (tmp_path / "vsa.intoto.json").write_text(json.dumps(env))
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "DSSE signature does NOT verify" in err


def test_lying_result_resigned_still_rejected(tmp_path):
    vk, _, stmt = _bundle(tmp_path, conformant=False)
    stmt["predicate"]["verificationResult"] = "PASSED"
    (tmp_path / "vsa.intoto.json").write_text(
        json.dumps(vsa.sign_vsa(stmt, vk))
    )
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "LIES" in err


def test_tampered_payload_rejected(tmp_path):
    vk, _, _ = _bundle(tmp_path)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    env = json.loads((tmp_path / "vsa.intoto.json").read_text())
    raw = bytearray(base64.b64decode(env["payload"]))
    raw[5] ^= 0x01
    env["payload"] = base64.b64encode(bytes(raw)).decode("ascii")
    (tmp_path / "vsa.intoto.json").write_text(json.dumps(env))
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "DSSE signature does NOT verify" in err


def test_wrong_pinned_key_rejected(tmp_path):
    _bundle(tmp_path)
    other = Ed25519PrivateKey.generate()
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(other.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "does NOT verify" in err


def test_tampered_farkas_sha_rejected(tmp_path):
    vk, _, _ = _bundle(tmp_path)
    raw = (tmp_path / "coverage.farkas.json").read_bytes()
    (tmp_path / "coverage.farkas.json").write_bytes(
        raw.replace(b'"x":"1"', b'"x":"2"')
    )
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "sha" in err.lower()


def test_forged_farkas_math_rejected(tmp_path):
    mk = Ed25519PrivateKey.generate()
    tk = Ed25519PrivateKey.generate()
    ck = Ed25519PrivateKey.generate()
    vk = Ed25519PrivateKey.generate()
    src, smt, pri, cg = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    bad = dict(_FARKAS)
    bad["multipliers"] = ["1", "0"]
    bad_bytes = json.dumps(bad, sort_keys=True, separators=(",", ":")).encode()
    bad_sha = hashlib.sha256(bad_bytes).hexdigest()

    manifest = _sign(
        {
            "world_name": "alpha", "source_sha256": src,
            "smt_spec_sha256": smt, "pricing_sha256": pri,
            "codegen_sha256": cg, "coverage_farkas_sha256": bad_sha,
        },
        mk, _manifest_canon, algorithm=False,
    )
    trace = _sign(
        {"world_name": "alpha", "codegen_sha256": cg}, tk, _trace_canon
    )
    trace_sha = hashlib.sha256(_trace_canon(trace)).hexdigest()
    bools = {b: True for b in vsa.OBLIGATION_NAMES}
    cert = {
        "certificate_schema_version": 4, "nous_version": "5.55.0",
        "world_name": "alpha", "issued_utc": "2026-06-19T11:00:00Z",
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
        "trace_sha256": trace_sha, "conformant": True, "errors": [],
        "codegen_sha256": cg,
    }
    cert.update(bools)
    cert = _sign(cert, ck, _cert_canon)
    man_sha = hashlib.sha256(_manifest_canon(manifest)).hexdigest()
    cert_sha = hashlib.sha256(_cert_canon(cert)).hexdigest()
    stmt = vsa.build_vsa_statement(
        world_name="alpha", nous_version="5.55.0",
        issued_utc="2026-06-19T11:00:00Z", codegen_sha256=cg,
        source_sha256=src, manifest_canonical_sha256=man_sha,
        trace_canonical_sha256=trace_sha,
        certificate_canonical_sha256=cert_sha, conformant=True,
        errors=(), certificate_schema_version=4,
        coverage_farkas_sha256=bad_sha, coverage_farkas_doc=bad,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "trace.json").write_text(json.dumps(trace))
    (tmp_path / "conformance.json").write_text(json.dumps(cert))
    (tmp_path / "coverage.farkas.json").write_bytes(bad_bytes)
    (tmp_path / "vsa.intoto.json").write_text(
        json.dumps(vsa.sign_vsa(stmt, vk))
    )
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "does NOT prove unsat" in err


def test_subject_confusion_rejected(tmp_path):
    vk, _, _ = _bundle(tmp_path)
    mk = json.loads((tmp_path / "manifest.json").read_text())
    tr = json.loads((tmp_path / "trace.json").read_text())
    ce = json.loads((tmp_path / "conformance.json").read_text())
    man_sha = hashlib.sha256(_manifest_canon(mk)).hexdigest()
    trace_sha = hashlib.sha256(_trace_canon(tr)).hexdigest()
    cert_sha = hashlib.sha256(_cert_canon(ce)).hexdigest()
    stmt = vsa.build_vsa_statement(
        world_name="alpha", nous_version="5.55.0",
        issued_utc="2026-06-19T11:00:00Z", codegen_sha256="9" * 64,
        source_sha256="a" * 64, manifest_canonical_sha256=man_sha,
        trace_canonical_sha256=trace_sha,
        certificate_canonical_sha256=cert_sha, conformant=True,
        errors=(), certificate_schema_version=4,
    )
    (tmp_path / "vsa.intoto.json").write_text(
        json.dumps(vsa.sign_vsa(stmt, vk))
    )
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc != 0
    assert "subject.digest" in err


def test_no_coverage_pass_proves_none(tmp_path):
    vk, _, _ = _bundle(tmp_path, with_coverage=False)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 0, err
    assert "PROVES: none" in out


def test_failed_but_consistent_returns_one(tmp_path):
    vk, _, _ = _bundle(tmp_path, conformant=False, with_coverage=False)
    vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    rc, out, err = _run(tmp_path)
    assert rc == 1
    assert "VERDICT: FAIL" in out


def test_emit_refuses_sentinel_and_empty():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            vsa_verifier.emit_vsa_verifier(d, "")
        with pytest.raises(ValueError):
            vsa_verifier.emit_vsa_verifier(
                d, "__NOUS_VSA_PINNED_PUBKEY_B64__"
            )


def test_emitted_file_has_no_sentinel(tmp_path):
    vk = Ed25519PrivateKey.generate()
    target = vsa_verifier.emit_vsa_verifier(
        str(tmp_path), vsa.public_key_raw_b64(vk.public_key())
    )
    text = Path_read(target)
    assert "__NOUS_VSA_PINNED_PUBKEY_B64__" not in text
    assert vsa.public_key_raw_b64(vk.public_key()) in text


def Path_read(p):
    from pathlib import Path
    return Path(p).read_text(encoding="utf-8")


def test_module_template_carries_sentinel():
    assert "__NOUS_VSA_PINNED_PUBKEY_B64__" in (
        vsa_verifier.VSA_VERIFY_OFFLINE_PY
    )
    assert vsa_verifier.VSA_VERIFY_OFFLINE_PY.isascii()
