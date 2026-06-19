"""S156 U5: end-to-end codegen leg through the real producers.

cmd_verify mints the manifest (stamping codegen), TraceRecorder.finalize
produces the signed trace (stamping codegen), build_certificate carries the leg
from the manifest, and the emitted offline verifier checks sha-equality with
cryptography + stdlib. Mirrors tests/test_dossier.py (cmd_verify Args) and
tests/test_s156_u4_offline_codegen.py (offline run) with the full-program source
of tests/test_s156_u3_codegen_obligation.py. EVIDENCES program identity; does
not prove the run executed.
__s156_u5_e2e_codegen_test_v1__
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cli_verify import cmd_verify
from conformance import (
    build_certificate,
    certificate_json,
    sign_certificate,
    verify_conformance,
)
from conformance_verifier import emit_conformance_verifier
from manifest import parse_manifest_json
from parser import parse_nous
from pricing import load_pricing
from run_shas import compute_codegen_sha256
from smt_emit import emit_smt
from trace_recorder import TraceRecorder

_PROG = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Ping }\n"
    "}\n"
    "message Ping { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)


class _VerifyArgs:
    smt = True
    prices = None
    timeout_ms = 30000
    no_manifest = False
    manifest_out = None
    key_path = None
    smt_margin = 0
    no_lint = True
    lint_strict = False
    lint_error_on = None

    def __init__(self, file: str) -> None:
        self.file = file


def _cmd_verify_manifest(tmp_path):
    src = tmp_path / "source.nous"
    src.write_text(_PROG, encoding="utf-8")
    assert cmd_verify(_VerifyArgs(str(src))) == 0
    manifest_path = src.with_suffix(".manifest.json")
    assert manifest_path.is_file()
    return src, manifest_path


def _spec(source_text, manifest):
    pricing = load_pricing(None)
    program = parse_nous(source_text)
    margin = manifest.safety_margin_pct or 0
    spec = emit_smt(
        program, pricing, source_text=source_text, margin_pct=margin
    )
    return spec, pricing


def _conforming_trace(spec, *, codegen):
    rec = TraceRecorder(
        nous_version="5.54.0",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        codegen_sha256=codegen,
    )
    rec.record_llm_call("A", 0, 100, 50)
    return rec.finalize(Ed25519PrivateKey.generate())


def _run(dp):
    return subprocess.run(
        [sys.executable, str(dp / "verify_conformance_offline.py")],
        capture_output=True, text=True,
    )


def test_e2e_real_producers_codegen_leg_agrees_and_passes(tmp_path) -> None:
    src, manifest_path = _cmd_verify_manifest(tmp_path)
    source_text = src.read_text(encoding="utf-8")
    manifest, _sig, _pub = parse_manifest_json(
        manifest_path.read_text(encoding="utf-8")
    )
    cg = compute_codegen_sha256(source_text)
    assert manifest.codegen_sha256 == cg
    assert manifest.codegen_sha256 is not None

    spec, pricing = _spec(source_text, manifest)
    tr = _conforming_trace(spec, codegen=cg)
    assert tr.codegen_sha256 == cg

    detail = verify_conformance(tr, manifest, spec, pricing, codegen_sha256=cg)
    assert detail.codegen_binding_ok is True
    assert detail.ok is True

    cert = sign_certificate(
        build_certificate(
            detail, tr, manifest, nous_version="5.54.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    assert cert.codegen_sha256 == cg
    assert manifest.codegen_sha256 == tr.codegen_sha256 == cert.codegen_sha256

    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            certificate_json(cert), encoding="utf-8"
        )
        (dp / "trace.json").write_text(
            json.dumps(tr.persisted_dict(), sort_keys=True), encoding="utf-8"
        )
        shutil.copy2(manifest_path, dp / "manifest.json")
        r = _run(dp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "codegen leg" in r.stdout


def test_e2e_producer_codegen_mismatch_rejected_offline(tmp_path) -> None:
    src, manifest_path = _cmd_verify_manifest(tmp_path)
    source_text = src.read_text(encoding="utf-8")
    manifest, _sig, _pub = parse_manifest_json(
        manifest_path.read_text(encoding="utf-8")
    )
    cg = compute_codegen_sha256(source_text)
    spec, pricing = _spec(source_text, manifest)

    wrong = "a" * 64
    tr = _conforming_trace(spec, codegen=wrong)
    assert tr.codegen_sha256 == wrong

    detail = verify_conformance(tr, manifest, spec, pricing, codegen_sha256=cg)
    assert detail.codegen_binding_ok is False

    cert = sign_certificate(
        build_certificate(
            detail, tr, manifest, nous_version="5.54.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    assert cert.codegen_sha256 == cg

    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            certificate_json(cert), encoding="utf-8"
        )
        (dp / "trace.json").write_text(
            json.dumps(tr.persisted_dict(), sort_keys=True), encoding="utf-8"
        )
        shutil.copy2(manifest_path, dp / "manifest.json")
        r = _run(dp)
    assert r.returncode == 1
    assert "codegen_sha256" in r.stderr
