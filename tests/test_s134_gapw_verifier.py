"""S134 2c-2a: end-to-end test of the standalone gap-witness offline verifier.

dossier.build_gap_witness_verifier() emits a self-contained verify_offline.py.
This module builds a synthetic coverage-gap-witness dossier (real Manifest,
real manifest_json/canonical_bytes signature binding, real serialize_gap_witness
and minilang re-derivation), then runs the EMITTED verifier by subprocess and
asserts the exit-code contract: 0 = artifact verified (VERDICT: REFUTATION);
1 = fail-closed (wrong kind / sidecar sha mismatch / missing sidecar / witness
does not hold / broken signature).

BOUNDARY: a verified gap-witness proves a coverage gap EXISTS at the carried
point; it is NOT a compliance pass, NOT evidence the agent misbehaves, NOT a
claim that the gap is unique or maximal. These tests assert verifier behaviour,
not legal sufficiency.
"""
# __s134_gapw_verifier_test_v1__
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import dossier
from coverage_farkas import serialize_gap_witness
from coverage_minilang import ml_parse, ml_scan_blocking_signals
from manifest import Manifest, manifest_json

SOURCE = """world Demo {
  policy guard {
    signal: amount > 1000
    action: block
  }
}
"""
THRESHOLD = "amount > 0"
GOOD_POINT = {"amount": "500"}
BLOCKED_POINT = {"amount": "2000"}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _gw_doc(point: dict) -> dict:
    t = ml_parse(THRESHOLD)
    blk = ml_scan_blocking_signals(SOURCE)
    return serialize_gap_witness(t, blk, dict(point), threshold_expr=THRESHOLD)


def _base(**over: Any) -> Manifest:
    fields = dict(
        schema_version="1",
        nous_version="5.36.0",
        smt_emit_version="1",
        source_sha256=_sha(SOURCE.encode("utf-8")),
        pricing_sha256="1" * 64,
        smt_spec_sha256="2" * 64,
        world_name="Demo",
        cost_cap_usd="10.00",
        max_ticks=100,
        verdict="PASS",
        solver_name="z3",
        solver_version="4.16.0",
        elapsed_ms=5,
        timestamp_utc="2026-06-12T00:00:00+00:00",
    )
    fields.update(over)
    return Manifest(**fields)


def _signed_text(m: Manifest) -> str:
    sk = Ed25519PrivateKey.generate()
    sig = sk.sign(m.canonical_bytes())
    return manifest_json(m, sig, sk.public_key())


def _write(tmp: Path, manifest_text: str, sidecar: bytes | None) -> None:
    (tmp / "manifest.json").write_text(manifest_text, encoding="utf-8")
    (tmp / "source.nous").write_bytes(SOURCE.encode("utf-8"))
    if sidecar is not None:
        (tmp / "coverage.gapwitness.json").write_bytes(sidecar)
    (tmp / "verify_offline.py").write_text(
        dossier.build_gap_witness_verifier(), encoding="utf-8")


def _run(tmp: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "verify_offline.py"],
        cwd=str(tmp), capture_output=True, text=True)


def test_gap_witness_verifies(tmp_path: Path) -> None:
    gwb = _canon(_gw_doc(GOOD_POINT))
    m = _base(source_kind="gap-witness", gap_witness_sha256=_sha(gwb))
    _write(tmp_path, _signed_text(m), gwb)
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "VERDICT: REFUTATION" in out
    assert "result: gap-demonstrated" in out


def test_wrong_kind_refused(tmp_path: Path) -> None:
    gwb = _canon(_gw_doc(GOOD_POINT))
    m = _base()
    _write(tmp_path, _signed_text(m), gwb)
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "not 'gap-witness'" in out


def test_sidecar_sha_mismatch(tmp_path: Path) -> None:
    gwb = _canon(_gw_doc(GOOD_POINT))
    m = _base(source_kind="gap-witness", gap_witness_sha256=_sha(gwb))
    _write(tmp_path, _signed_text(m), gwb + b"x")
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "sha256 mismatch" in out


def test_missing_sidecar(tmp_path: Path) -> None:
    gwb = _canon(_gw_doc(GOOD_POINT))
    m = _base(source_kind="gap-witness", gap_witness_sha256=_sha(gwb))
    _write(tmp_path, _signed_text(m), None)
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "not found" in out


def test_witness_does_not_hold(tmp_path: Path) -> None:
    gw_bad = dict(_gw_doc(GOOD_POINT))
    gw_bad["point"] = dict(BLOCKED_POINT)
    gwb = _canon(gw_bad)
    m = _base(source_kind="gap-witness", gap_witness_sha256=_sha(gwb))
    _write(tmp_path, _signed_text(m), gwb)
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "gap-witness does NOT verify" in out


def test_broken_signature(tmp_path: Path) -> None:
    gwb = _canon(_gw_doc(GOOD_POINT))
    m = _base(source_kind="gap-witness", gap_witness_sha256=_sha(gwb))
    obj = json.loads(_signed_text(m))
    raw = bytearray(base64.b64decode(obj["signature"]["signature_b64"]))
    raw[0] ^= 1
    obj["signature"]["signature_b64"] = base64.b64encode(bytes(raw)).decode()
    _write(tmp_path, json.dumps(obj), gwb)
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "Ed25519 signature does NOT verify" in out
