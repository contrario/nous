"""Tests for the standalone Annex IV map verifier builder (S135 U3a).

Generates verify_annex_iv_map.py via build_annex_iv_verifier() and exercises
it as a subprocess against a synthetic dossier + signed map: PASS on a valid
bundle, FAIL on tampered evidence, broken signature, or wrong manifest. Also
pins the injected item table against ANNEX_IV_ITEMS (single source of truth).

# __s135_annex_iv_verifier_tests_v1__
"""
from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from annex_iv_map import (
    ANNEX_IV_ITEMS,
    build_annex_iv_map,
    build_annex_iv_verifier,
    serialize_annex_iv_map,
)


def _write_manifest(dossier_dir: Path) -> None:
    manifest = {
        "schema_version": 3,
        "nous_version": "5.37.0",
        "smt_emit_version": "1.0",
        "source_sha256": "a" * 64,
        "pricing_sha256": "b" * 64,
        "smt_spec_sha256": "c" * 64,
        "world_name": "TestWorld",
        "cost_cap_usd": "0.20",
        "max_ticks": 3,
        "verdict": "proven",
        "solver_name": "z3",
        "solver_version": "4.16.0",
        "elapsed_ms": 12,
        "timestamp_utc": "2026-06-12T00:00:00+00:00",
        "transparency_log": {"provider": "sigstore-rekor", "log_index": 42},
        "signature": {
            "public_key_b64": "ZmFrZQ==",
            "signature_b64": "ZmFrZXNpZw==",
        },
    }
    (dossier_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _make_dossier_with_map(dossier_dir: Path) -> None:
    _write_manifest(dossier_dir)
    (dossier_dir / "source.nous").write_bytes(b"world TestWorld {}\n")
    priv = Ed25519PrivateKey.generate()
    doc = build_annex_iv_map(dossier_dir, priv)
    (dossier_dir / "annex_iv_map.json").write_text(
        serialize_annex_iv_map(doc), encoding="utf-8"
    )
    (dossier_dir / "verify_annex_iv_map.py").write_text(
        build_annex_iv_verifier(), encoding="utf-8"
    )


def _run_verifier(dossier_dir: Path) -> int:
    proc = subprocess.run(
        [sys.executable, "verify_annex_iv_map.py"],
        cwd=str(dossier_dir),
        capture_output=True,
    )
    return proc.returncode


def test_builder_injects_canonical_table() -> None:
    src = build_annex_iv_verifier()
    triples = [(i, t, k) for i, t, _c, k in ANNEX_IV_ITEMS]
    assert repr(triples) in src
    assert "__ANNEX_IV_ITEMS_LITERAL__" not in src


def test_builder_is_deterministic() -> None:
    assert build_annex_iv_verifier() == build_annex_iv_verifier()


def test_generated_verifier_compiles(tmp_path: Path) -> None:
    p = tmp_path / "verify_annex_iv_map.py"
    p.write_text(build_annex_iv_verifier(), encoding="utf-8")
    py_compile.compile(str(p), doraise=True)


def test_generated_verifier_is_ascii() -> None:
    assert build_annex_iv_verifier().encode("ascii")


def test_generated_verifier_passes_on_valid_dossier(tmp_path: Path) -> None:
    _make_dossier_with_map(tmp_path)
    assert _run_verifier(tmp_path) == 0


def test_generated_verifier_fails_on_tampered_evidence(
    tmp_path: Path,
) -> None:
    _make_dossier_with_map(tmp_path)
    (tmp_path / "source.nous").write_bytes(b"world TestWorld { tampered }\n")
    assert _run_verifier(tmp_path) == 1


def test_generated_verifier_fails_on_broken_signature(
    tmp_path: Path,
) -> None:
    _make_dossier_with_map(tmp_path)
    doc = json.loads(
        (tmp_path / "annex_iv_map.json").read_text(encoding="utf-8")
    )
    doc["signature"]["signature_b64"] = "AAAA"
    (tmp_path / "annex_iv_map.json").write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert _run_verifier(tmp_path) == 1


def test_generated_verifier_fails_on_wrong_manifest(tmp_path: Path) -> None:
    _make_dossier_with_map(tmp_path)
    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    manifest["world_name"] = "DifferentWorld"
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert _run_verifier(tmp_path) == 1


def test_generated_verifier_fails_on_missing_map(tmp_path: Path) -> None:
    (tmp_path / "verify_annex_iv_map.py").write_text(
        build_annex_iv_verifier(), encoding="utf-8"
    )
    assert _run_verifier(tmp_path) == 1
