"""S157 U5: end-to-end VSA through the real producers.

cmd_verify (real Z3) mints the signed manifest; TraceRecorder.finalize mints
the signed trace; build_certificate + sign_certificate mint the signed
certificate; `nous vsa emit` (cli_vsa) builds and signs the DSSE-wrapped VSA
and writes the bundle; the emitted verify_vsa_offline.py verifies the whole
bundle offline with cryptography + stdlib only. Mirrors
tests/test_s156_u5_e2e_codegen.py for the producer chain.

EVIDENCES program identity, authenticity, and binding; the verdict is
re-derived from the eight obligations offline (never trusted from the
recorded string). The coverage Farkas (PROVES) leg's tamper/forge defenses
are exercised as real e2e in tests/test_s157_u2_vsa_verifier.py (real
emit_vsa_verifier + real check_serialized rational math); a cmd_verify-
produced coverage leg is deferred to a covering-program fixture (S158).
__s157_u5_e2e_vsa_test_v1__
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import cli_vsa
import vsa
from cli_verify import cmd_verify
from conformance import (
    build_certificate,
    certificate_json,
    sign_certificate,
    verify_conformance,
)
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
        nous_version="5.55.0",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        codegen_sha256=codegen,
    )
    rec.record_llm_call("A", 0, 100, 50)
    return rec.finalize(Ed25519PrivateKey.generate())


def _write_inputs(dirp, manifest_path, trace, cert):
    dirp.mkdir(parents=True, exist_ok=True)
    (dirp / "manifest.json").write_bytes(manifest_path.read_bytes())
    (dirp / "trace.json").write_text(
        json.dumps(trace.persisted_dict(), sort_keys=True), encoding="utf-8"
    )
    (dirp / "conformance.json").write_text(
        certificate_json(cert), encoding="utf-8"
    )


def _emit_args(inputs, out, key):
    return argparse.Namespace(
        command="vsa", vsa_command="emit",
        trace=str(inputs / "trace.json"),
        manifest=str(inputs / "manifest.json"),
        cert=str(inputs / "conformance.json"),
        coverage=None, out=str(out), key_path=str(key),
    )


def _run_offline(bundle):
    return subprocess.run(
        [sys.executable, str(bundle / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(bundle),
    )


def _full_chain(tmp_path, *, trace_codegen=None):
    src, manifest_path = _cmd_verify_manifest(tmp_path)
    source_text = src.read_text(encoding="utf-8")
    manifest, _sig, _pub = parse_manifest_json(
        manifest_path.read_text(encoding="utf-8")
    )
    cg = compute_codegen_sha256(source_text)
    spec, pricing = _spec(source_text, manifest)
    tr = _conforming_trace(spec, codegen=(trace_codegen or cg))
    detail = verify_conformance(
        tr, manifest, spec, pricing, codegen_sha256=cg
    )
    cert = sign_certificate(
        build_certificate(
            detail, tr, manifest, nous_version="5.55.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    return manifest_path, tr, cert, detail


def test_e2e_real_producers_vsa_passes(tmp_path) -> None:
    manifest_path, tr, cert, detail = _full_chain(tmp_path)
    assert detail.ok is True

    inputs = tmp_path / "inputs"
    _write_inputs(inputs, manifest_path, tr, cert)
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    assert cli_vsa.cmd_vsa(_emit_args(inputs, out, key)) == 0

    for name in (
        "vsa.intoto.json", "verify_vsa_offline.py", "manifest.json",
        "trace.json", "conformance.json",
    ):
        assert (out / name).is_file(), name

    r = _run_offline(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERDICT: PASS" in r.stdout
    assert "PROVES: none" in r.stdout


def test_e2e_codegen_mismatch_rejected_offline(tmp_path) -> None:
    manifest_path, tr, cert, detail = _full_chain(
        tmp_path, trace_codegen="a" * 64
    )
    assert detail.codegen_binding_ok is False

    inputs = tmp_path / "inputs"
    _write_inputs(inputs, manifest_path, tr, cert)
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    assert cli_vsa.cmd_vsa(_emit_args(inputs, out, key)) == 0

    r = _run_offline(out)
    assert r.returncode != 0
    assert "codegen_sha256" in r.stderr


def test_e2e_lying_verification_result_rejected(tmp_path) -> None:
    manifest_path, tr, cert, detail = _full_chain(tmp_path)
    assert detail.ok is True

    inputs = tmp_path / "inputs"
    _write_inputs(inputs, manifest_path, tr, cert)
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    assert cli_vsa.cmd_vsa(_emit_args(inputs, out, key)) == 0

    priv, _pub, _ = vsa.load_or_create_vsa_keypair(key)
    env = json.loads((out / "vsa.intoto.json").read_text())
    statement = json.loads(base64.b64decode(env["payload"]).decode("utf-8"))
    statement["predicate"]["verificationResult"] = "FAILED"
    (out / "vsa.intoto.json").write_text(
        json.dumps(vsa.sign_vsa(statement, priv), sort_keys=True, indent=2),
        encoding="utf-8",
    )

    r = _run_offline(out)
    assert r.returncode != 0
    assert "LIES" in r.stderr
