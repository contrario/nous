"""S156 U4: the offline verifier independently checks the codegen leg.

A third party running verify_conformance_offline.py (cryptography + stdlib)
re-derives sha-equality of the codegen leg fail-closed; it does not trust the
recorded codegen_binding_ok bool. Construction mirrors
tests/test_s97_certificate.py (signed trace + signed manifest + signed cert)
with the full-program source of tests/test_s156_u3_codegen_obligation.py so the
codegen digest is real. EVIDENCES program identity; does not prove the run ran.
__s156_u4_offline_codegen_test_v1__
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from conformance import (
    build_certificate,
    certificate_json,
    sign_certificate,
    verify_conformance,
)
from conformance_verifier import emit_conformance_verifier
from manifest import (
    load_or_create_keypair,
    manifest_from_verify,
    manifest_json,
    sign_manifest,
)
from nous_trace import TraceEnvelope, TraceEvent, sign_trace
from parser import parse_nous
from pricing import load_pricing
from run_shas import compute_codegen_sha256
from smt_emit import emit_smt
from smt_verify import VerifyResult

_TS = "2026-01-01T00:00:00+00:00"

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


def _spec_pricing():
    pricing = load_pricing(None)
    program = parse_nous(_PROG)
    spec = emit_smt(program, pricing, source_text=_PROG, today=None)
    return spec, pricing


def _manifest(spec, *, codegen):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=1,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.54.0",
        codegen_sha256=codegen,
    )


def _signed_trace(spec, *, codegen):
    env = TraceEnvelope(
        nous_version="5.54.0",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[
            TraceEvent(
                seq=0, tick=0, soul="A", kind="llm_call",
                input_tokens=100, output_tokens=50, tool_cost="0",
                action=None, authorization=None, timestamp_utc=_TS,
            )
        ],
        codegen_sha256=codegen,
    )
    return sign_trace(env, Ed25519PrivateKey.generate())


def _trace_json(tr) -> str:
    return json.dumps(tr.persisted_dict(), sort_keys=True)


def _signed_cert(detail, tr, man):
    return sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.54.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )


def _write_manifest(dp, man):
    priv, pub, _ = load_or_create_keypair(dp / "k.key")
    sig = sign_manifest(man, priv)
    (dp / "manifest.json").write_text(
        manifest_json(man, sig, pub), encoding="utf-8"
    )


def _run(dp):
    return subprocess.run(
        [sys.executable, str(dp / "verify_conformance_offline.py")],
        capture_output=True, text=True,
    )


def test_offline_verifier_passes_with_codegen_leg() -> None:
    spec, pricing = _spec_pricing()
    cg = compute_codegen_sha256(_PROG)
    man = _manifest(spec, codegen=cg)
    tr = _signed_trace(spec, codegen=cg)
    detail = verify_conformance(tr, man, spec, pricing, codegen_sha256=cg)
    assert detail.ok is True
    cert = _signed_cert(detail, tr, man)
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            certificate_json(cert), encoding="utf-8"
        )
        (dp / "trace.json").write_text(_trace_json(tr), encoding="utf-8")
        _write_manifest(dp, man)
        r = _run(dp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "codegen leg" in r.stdout


def test_offline_verifier_rejects_codegen_lie() -> None:
    spec, pricing = _spec_pricing()
    cg = compute_codegen_sha256(_PROG)
    man = _manifest(spec, codegen=cg)
    tr = _signed_trace(spec, codegen=cg)
    detail = verify_conformance(tr, man, spec, pricing, codegen_sha256=cg)
    cert = _signed_cert(detail, tr, man)
    doc = json.loads(certificate_json(cert))
    assert doc["conformant"] is True
    assert doc["codegen_binding_ok"] is True
    doc["codegen_sha256"] = "f" * 64
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    canon = json.dumps(
        body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    doc["signature"] = {
        "algorithm": "ed25519",
        "public_key_b64": base64.b64encode(pub).decode("ascii"),
        "signature_b64": base64.b64encode(key.sign(canon)).decode("ascii"),
    }
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            json.dumps(doc), encoding="utf-8"
        )
        (dp / "trace.json").write_text(_trace_json(tr), encoding="utf-8")
        _write_manifest(dp, man)
        r = _run(dp)
    assert r.returncode == 1
    assert "codegen_sha256" in r.stderr
