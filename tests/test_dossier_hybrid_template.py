"""Tests for VERIFY_OFFLINE_PY_HYBRID template (S82 #1a).

The hybrid verifier accepts both Rekor-anchored and unanchored
dossiers. When transparency_log is present, the full Sigstore Rekor
anchor is verified (identical semantics to VERIFY_OFFLINE_PY_WITH_REKOR).
When absent, --allow-unanchored is required and the verifier falls
back to Ed25519 + source SHA only. By default unanchored dossiers
are refused.

Patch 1a covers unanchored paths only; anchored-path coverage is
delivered in Patch 1b alongside the endpoint changes, since that
patch has the Rekor fixture infrastructure already wired.

# __session82_test_dossier_hybrid_template_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))


def _build_unanchored_dossier(
    tmp_path: Path,
    *,
    tamper_signature: bool = False,
    tamper_source: bool = False,
) -> Path:
    from dossier import VERIFY_OFFLINE_PY_HYBRID

    source_text = "world default { lawful { goal terminate } }\n"
    source_bytes = source_text.encode("utf-8")
    source_sha = hashlib.sha256(source_bytes).hexdigest()

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes_raw()
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")

    body: dict[str, Any] = {
        "schema_version": "1.0",
        "world_name": "default",
        "source_sha256": source_sha,
        "pricing_sha256": "0" * 64,
        "smt_spec_sha256": "0" * 64,
        "cost_cap_usd": "1.00",
        "max_ticks": 10,
        "safety_margin_pct": 5,
        "verdict": "PROVEN",
        "solver_version": "z3-4.16",
        "timestamp_utc": "2026-05-17T12:00:00Z",
        "nous_version": "5.4.0",
        "smt_emit_version": "1.0",
    }
    body_bytes = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sig = priv.sign(body_bytes)
    if tamper_signature:
        sig = bytes([sig[0] ^ 0x01]) + sig[1:]
    sig_b64 = base64.b64encode(sig).decode("ascii")

    manifest_with_sig = dict(body)
    manifest_with_sig["signature"] = {
        "public_key_b64": pub_b64,
        "signature_b64": sig_b64,
    }

    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest_with_sig, indent=2), encoding="utf-8"
    )
    if tamper_source:
        (tmp_path / "source.nous").write_text(
            "world default { lawful { goal evolve } }\n",
            encoding="utf-8",
        )
    else:
        (tmp_path / "source.nous").write_bytes(source_bytes)
    (tmp_path / "verify_offline.py").write_text(
        VERIFY_OFFLINE_PY_HYBRID, encoding="utf-8"
    )
    return tmp_path


def _run_verifier(
    dossier_dir: Path, *, allow_unanchored: bool = False
) -> "subprocess.CompletedProcess[str]":
    args = [sys.executable, str(dossier_dir / "verify_offline.py")]
    if allow_unanchored:
        args.append("--allow-unanchored")
    return subprocess.run(
        args, capture_output=True, text=True, cwd=str(dossier_dir)
    )


def test_hybrid_constant_is_nonempty_ascii() -> None:
    from dossier import VERIFY_OFFLINE_PY_HYBRID
    assert VERIFY_OFFLINE_PY_HYBRID
    assert isinstance(VERIFY_OFFLINE_PY_HYBRID, str)
    VERIFY_OFFLINE_PY_HYBRID.encode("ascii")


def test_hybrid_compiles_as_python(tmp_path: Path) -> None:
    from dossier import VERIFY_OFFLINE_PY_HYBRID
    import py_compile
    target = tmp_path / "vof.py"
    target.write_text(VERIFY_OFFLINE_PY_HYBRID, encoding="utf-8")
    py_compile.compile(str(target), doraise=True)


def test_hybrid_refuses_unanchored_without_flag(tmp_path: Path) -> None:
    _build_unanchored_dossier(tmp_path)
    proc = _run_verifier(tmp_path, allow_unanchored=False)
    assert proc.returncode == 1, (
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "transparency_log block missing" in proc.stderr
    assert "--allow-unanchored" in proc.stderr


def test_hybrid_accepts_unanchored_with_flag(tmp_path: Path) -> None:
    _build_unanchored_dossier(tmp_path)
    proc = _run_verifier(tmp_path, allow_unanchored=True)
    assert proc.returncode == 0, (
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "VERDICT: PASS" in proc.stdout
    assert "unanchored" in proc.stdout.lower()


def test_hybrid_rejects_tampered_signature_even_with_flag(
    tmp_path: Path,
) -> None:
    _build_unanchored_dossier(tmp_path, tamper_signature=True)
    proc = _run_verifier(tmp_path, allow_unanchored=True)
    assert proc.returncode == 1
    assert "signature does NOT verify" in proc.stderr


def test_hybrid_rejects_source_sha_mismatch_even_with_flag(
    tmp_path: Path,
) -> None:
    _build_unanchored_dossier(tmp_path, tamper_source=True)
    proc = _run_verifier(tmp_path, allow_unanchored=True)
    assert proc.returncode == 1
    assert "source.sha256 mismatch" in proc.stderr
