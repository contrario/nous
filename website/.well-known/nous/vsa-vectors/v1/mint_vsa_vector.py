#!/usr/bin/env python3
"""Deterministic mint harness for the NOUS VSA conformance vector.

Architecture: CLI-then-repin. cmd_verify mints the CANONICAL manifest and the
canonical coverage.farkas.json / cost.farkas.json (exactly the bytes `nous
verify` writes -- indent=2 coverage, cost_farkas_json_bytes cost, every
manifest field the CLI sets). The harness then pins ONLY the two wall-clock
fields that cmd_verify bakes in non-injectably (manifest.timestamp_utc via
datetime.now() in smt_verify.py, and manifest.elapsed_ms, the real solve time),
by re-signing the manifest with the same fixed key. Reconstructing the manifest
by hand was rejected: it silently drops CLI-set fields
(policy_coverage_sha256, coverage_smt2_sha256) and produces non-canonical
bytes. Trace and cert are minted producer-direct (cmd_verify does not emit
them) with a pinned clock and pinned issued_utc, mirroring the S157 e2e chain.

Three pins (the determinism contract):
  1. keys      -- four fixed Ed25519 seeds (manifest, trace, cert, VSA),
                  loaded via from_private_bytes. PUBLISHED vector keys, not
                  secrets: reproducibility is the goal.
  2. timestamps-- manifest.timestamp_utc + manifest.elapsed_ms repinned by
                  re-signing; cert.issued_utc is a direct arg; trace uses an
                  injected fixed clock; the VSA carries no independent stamp
                  (timeVerified rides from the pinned cert).
  3. program   -- the frozen vsa_conformance_vector_v1.nous.

Determinism gate: the whole mint runs TWICE; bundle files, verifier stdout, and
exit code MUST be byte-identical across runs, or the harness aborts. "Ran
without crashing" is not the gate.

Usage:  python3 mint_vsa_vector.py <source.nous> <out_dir>
Exit 0 = deterministic both-legs bundle, verifier PASS reproduced twice.
Exit 1 = non-determinism detected or verifier did not PASS.
Exit 2 = environment / producer-signature error.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives import serialization

import cli_vsa
import cli_verify
from conformance import (
    build_certificate,
    certificate_json,
    sign_certificate,
    verify_conformance,
)
from manifest import (
    manifest_json,
    parse_manifest_json,
    sign_manifest,
)
from parser import parse_nous
from pricing import load_pricing
from run_shas import compute_codegen_sha256
from smt_emit import emit_smt
from trace_recorder import TraceRecorder

_PINNED_TS = "2000-01-01T00:00:00Z"
_PINNED_ISSUED = "2000-01-01T00:00:00Z"
_PINNED_ELAPSED_MS = 0
_COVERAGE_THRESHOLD = "amount > 10000"
_SOUL = "Probe"
_IN_TOK = 100
_OUT_TOK = 50

_SEED_MANIFEST = bytes(range(0, 32))
_SEED_TRACE = bytes(range(32, 64))
_SEED_CERT = bytes(range(64, 96))
_SEED_VSA = bytes(range(96, 128))


def _fixed_key(seed: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(seed)


def _write_pkcs8_pem(seed: bytes, path: Path) -> None:
    pem = _fixed_key(seed).private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)


def _fixed_clock() -> str:
    return _PINNED_TS


def _verify_args(source_path: Path, work: Path, mkey: Path) -> argparse.Namespace:
    return argparse.Namespace(
        file=str(source_path),
        smt=True,
        prices=None,
        timeout_ms=30000,
        no_manifest=False,
        manifest_out=str(work / "manifest.json"),
        key_path=str(mkey),
        coverage_threshold=_COVERAGE_THRESHOLD,
        gap_witness=False,
        smt_margin=0,
        no_lint=True,
        lint_strict=False,
        lint_error_on=None,
    )


def _repin_manifest(manifest_path: Path) -> None:
    manifest, _body, _pub = parse_manifest_json(
        manifest_path.read_text(encoding="utf-8")
    )
    repinned = dataclasses.replace(
        manifest,
        nous_version="vector",
        timestamp_utc=_PINNED_TS,
        elapsed_ms=_PINNED_ELAPSED_MS,
    )
    priv = _fixed_key(_SEED_MANIFEST)
    sig = sign_manifest(repinned, priv)
    manifest_path.write_text(
        manifest_json(repinned, sig, priv.public_key()), encoding="utf-8"
    )


def _mint_once(source_path: Path, run_root: Path) -> Tuple[str, int, Path]:
    work = run_root / "work"
    work.mkdir(parents=True, exist_ok=True)
    source_text = source_path.read_text(encoding="utf-8")

    mkey = work / "_manifest.key"
    _write_pkcs8_pem(_SEED_MANIFEST, mkey)

    rc = cli_verify.cmd_verify(_verify_args(source_path, work, mkey))
    if rc != 0:
        raise SystemExit("mint: cmd_verify returned " + str(rc))

    manifest_path = work / "manifest.json"
    coverage_far = work / "coverage.farkas.json"
    cost_far = work / "cost.farkas.json"
    for p in (manifest_path, coverage_far, cost_far):
        if not p.is_file():
            raise SystemExit("mint: cmd_verify did not write " + p.name)

    _repin_manifest(manifest_path)

    program = parse_nous(source_text)
    pricing = load_pricing(None)
    spec = emit_smt(program, pricing, source_text=source_text)
    codegen = compute_codegen_sha256(source_text)

    rec = TraceRecorder(
        nous_version="vector",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        codegen_sha256=codegen,
        clock=_fixed_clock,
    )
    rec.record_llm_call(_SOUL, 0, _IN_TOK, _OUT_TOK)
    trace = rec.finalize(_fixed_key(_SEED_TRACE))

    manifest, _b, _p = parse_manifest_json(
        manifest_path.read_text(encoding="utf-8")
    )
    detail = verify_conformance(
        trace, manifest, spec, pricing, codegen_sha256=codegen
    )
    cert = sign_certificate(
        build_certificate(
            detail, trace, manifest,
            nous_version="vector", issued_utc=_PINNED_ISSUED,
        ),
        _fixed_key(_SEED_CERT),
    )

    (work / "trace.json").write_text(
        json.dumps(trace.persisted_dict(), sort_keys=True), encoding="utf-8"
    )
    (work / "conformance.json").write_text(
        certificate_json(cert), encoding="utf-8"
    )

    vkey = work / "_vsa.key"
    vkey.write_bytes(_SEED_VSA)
    bundle = run_root / "bundle"
    emit_args = argparse.Namespace(
        command="vsa", vsa_command="emit",
        trace=str(work / "trace.json"),
        manifest=str(manifest_path),
        cert=str(work / "conformance.json"),
        coverage=str(coverage_far),
        cost=str(cost_far),
        out=str(bundle),
        key_path=str(vkey),
        no_inline_pin=False,
    )
    rc_emit = cli_vsa.cmd_vsa(emit_args)
    if rc_emit != 0:
        raise SystemExit("mint: vsa emit returned " + str(rc_emit))

    proc = subprocess.run(
        [sys.executable, str(bundle / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(bundle),
    )
    return proc.stdout, proc.returncode, bundle


def _bundle_digest(bundle: Path) -> dict:
    out = {}
    for p in sorted(bundle.iterdir()):
        if p.is_file():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out")
    args = ap.parse_args()

    source_path = Path(args.source)
    out_root = Path(args.out)

    with tempfile.TemporaryDirectory() as t1, \
            tempfile.TemporaryDirectory() as t2:
        stdout1, rc1, bundle1 = _mint_once(source_path, Path(t1))
        stdout2, rc2, bundle2 = _mint_once(source_path, Path(t2))

        dig1 = _bundle_digest(bundle1)
        dig2 = _bundle_digest(bundle2)

        problems = []
        if dig1 != dig2:
            problems.append("bundle bytes differ across runs")
            for name in sorted(set(dig1) | set(dig2)):
                a = dig1.get(name, "MISSING")
                b = dig2.get(name, "MISSING")
                if a != b:
                    problems.append("  " + name + ": " + a[:16]
                                    + " != " + b[:16])
        if stdout1 != stdout2:
            problems.append("verifier stdout differs across runs")
        if rc1 != rc2:
            problems.append("verifier exit differs: "
                            + str(rc1) + " != " + str(rc2))
        if rc1 != 0:
            problems.append("verifier did not PASS (exit " + str(rc1) + ")")
        if "VERDICT: PASS" not in stdout1:
            problems.append("verifier stdout missing VERDICT: PASS")

        if problems:
            print("DETERMINISM/PASS GATE FAILED:", file=sys.stderr)
            for p in problems:
                print("  " + p, file=sys.stderr)
            print("\n--- stdout run 1 ---\n" + stdout1, file=sys.stderr)
            return 1

        out_root.mkdir(parents=True, exist_ok=True)
        for p in sorted(bundle1.iterdir()):
            if p.is_file():
                (out_root / p.name).write_bytes(p.read_bytes())
        (out_root / "expected_stdout.txt").write_text(
            stdout1, encoding="utf-8"
        )
        (out_root / "expected_exit.txt").write_text(
            str(rc1) + "\n", encoding="utf-8"
        )

        print("DETERMINISM GATE PASSED (byte-identical across two mints)")
        print("verifier exit: " + str(rc1))
        print("\nfrozen bundle digests:")
        for name, sha in sorted(dig1.items()):
            print("  " + sha[:16] + "...  " + name)
        print("\nbundle + expected_stdout.txt + expected_exit.txt -> "
              + str(out_root))
        print("\n--- verifier stdout (the frozen expected output) ---")
        print(stdout1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
