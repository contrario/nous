"""X-G2 -- an auditor-supplied --expect-signer in both offline verifiers.

FG-S415-X, X_INNOVATION_GATE.md XK4 as amended (10-25): the expected
signer is an argument the auditor supplies at run time. It is never a
constant baked into the emitted script, because that script ships inside
the bundle under review and a constant in it would pin nothing.

The bundle is a committed demo vector, unaltered. The "other" key is a
fresh public key that signs nothing.

Honest boundary: a pinned-signer pass EVIDENCES that the certificate was
signed by the holder of the expected key. Who holds that key is
established out of band; it is not a proof of the run.

# __x_g2_offline_pin_tests_v1__
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from conformance_verifier import emit_conformance_verifier

_VEC = Path(__file__).resolve().parents[1] / "examples" / "demos" / "cert-4679350"
_OK_LINE = "OK   certificate signer is the expected key (--expect-signer)"
_SCOPE_LINE = (
    "SIGNER: pinned to the auditor-supplied --expect-signer key; who holds "
    "that key is established out of band."
)
_MISMATCH = "FAIL: certificate signer is not the expected key"
_BADKEY = (
    "ERROR: --expect-signer is not a base64 raw 32-byte Ed25519 public key"
)
_USAGE = "usage: python3 verify_conformance_offline.py [--expect-signer BASE64]"


def _own_key_b64() -> str:
    doc = json.loads((_VEC / "conformance.json").read_text(encoding="utf-8"))
    return doc["signature"]["public_key_b64"]


def _fresh_key_b64() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def _run(tmp_path: Path, anchored: bool, argv: list[str]):
    d = tmp_path / ("anchored" if anchored else "unanchored")
    d.mkdir()
    for name in ("conformance.json", "trace.json", "manifest.json"):
        shutil.copy(_VEC / name, d / name)
    emit_conformance_verifier(str(d), anchored=anchored)
    return subprocess.run(
        [sys.executable, "-I", "verify_conformance_offline.py", *argv],
        cwd=str(d),
        capture_output=True,
        text=True,
    )


def test_o1_unanchored_default(tmp_path: Path) -> None:
    r = _run(tmp_path, False, [])
    assert r.returncode == 0
    assert _OK_LINE not in r.stdout and "SIGNER:" not in r.stdout


def test_o2_unanchored_own_key(tmp_path: Path) -> None:
    r = _run(tmp_path, False, ["--expect-signer", _own_key_b64()])
    assert r.returncode == 0
    assert _OK_LINE in r.stdout and _SCOPE_LINE in r.stdout


def test_o3_unanchored_fresh_key(tmp_path: Path) -> None:
    r = _run(tmp_path, False, ["--expect-signer", _fresh_key_b64()])
    assert r.returncode == 1
    assert _MISMATCH in r.stderr


def test_o4_unanchored_malformed_key(tmp_path: Path) -> None:
    r = _run(tmp_path, False, ["--expect-signer", "not base64 !"])
    assert r.returncode == 2
    assert _BADKEY in r.stderr


def test_o5_unanchored_unknown_argument(tmp_path: Path) -> None:
    r = _run(tmp_path, False, ["--expect-signr", _own_key_b64()])
    assert r.returncode == 2
    assert _USAGE in r.stderr


def test_o6_anchored_default(tmp_path: Path) -> None:
    r = _run(tmp_path, True, [])
    assert r.returncode == 0
    assert _OK_LINE not in r.stdout and "SIGNER:" not in r.stdout


def test_o7_anchored_own_key(tmp_path: Path) -> None:
    r = _run(tmp_path, True, ["--expect-signer", _own_key_b64()])
    assert r.returncode == 0
    assert _OK_LINE in r.stdout and _SCOPE_LINE in r.stdout


def test_o8_anchored_fresh_key(tmp_path: Path) -> None:
    r = _run(tmp_path, True, ["--expect-signer", _fresh_key_b64()])
    assert r.returncode == 1
    assert _MISMATCH in r.stderr


def test_o9_anchored_malformed_key(tmp_path: Path) -> None:
    r = _run(tmp_path, True, ["--expect-signer", "not base64 !"])
    assert r.returncode == 2
    assert _BADKEY in r.stderr


def test_o10_anchored_unknown_argument(tmp_path: Path) -> None:
    r = _run(tmp_path, True, ["--expect-signr", _own_key_b64()])
    assert r.returncode == 2
