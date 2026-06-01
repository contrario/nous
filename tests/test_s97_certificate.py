"""S97 runtime conformance CERTIFICATE -- offline end-to-end tests.

Extends S96 (verify_conformance) with the standalone signed certificate:
build -> sign -> verify -> JSON round-trip -> offline verifier subprocess.
Drives the real pipeline (emit_smt -> manifest_from_verify -> sign trace ->
verify_conformance -> build_certificate -> sign_certificate), no network,
no z3. The anchored Rekor path needs network and is covered structurally
(the assembled v2 conformance verifier compiles) rather than end-to-end here.

# __nous_s97_certificate_tests_v1__
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ast_nodes import (
    CostCap,
    MindNode,
    NousProgram,
    SoulNode,
    TokensDecl,
    WorldNode,
)
from conformance import (
    ConformanceCertificate,
    build_certificate,
    certificate_json,
    load_certificate,
    sign_certificate,
    verify_certificate_from_json,
    verify_certificate_signature,
    verify_conformance,
)
from conformance_verifier import emit_conformance_verifier
from manifest import manifest_from_verify
from offline_verifier_builder import build_conformance_verifier_v2
from pricing import PricingTable as _PricingTable
from rekor_verify_v2 import KNOWN_REKOR_V2_LOG_KEYS
from smt_emit import emit_smt
from smt_verify import VerifyResult
from nous_trace import TraceEnvelope, TraceEvent, sign_trace

TODAY = date(2026, 4, 28)
_SOURCE_TEXT = "world Floor { cost_cap: 0.50 USD max_ticks: 5 }\n"

PRICING_TOML = """\
_schema_version = "2.0"
_currency = "USD"
[models."m1"]
provider = "test"
pricing_model = "per_token"
input_per_1m = "1.00"
output_per_1m = "5.00"
reasoning_token_multiplier = "1.0"
verified_date = "2026-04-28"
[models."m2"]
provider = "test"
pricing_model = "per_token"
input_per_1m = "0.50"
output_per_1m = "2.00"
reasoning_token_multiplier = "1.0"
verified_date = "2026-04-28"
"""


@pytest.fixture
def pricing() -> _PricingTable:
    return _PricingTable.model_validate(tomllib.loads(PRICING_TOML))


def _program(cost_cap: str = "0.50", max_ticks: int = 5) -> NousProgram:
    from decimal import Decimal
    return NousProgram(
        world=WorldNode(
            name="Floor",
            cost_cap=CostCap(amount=Decimal(cost_cap), currency="USD"),
            max_ticks=max_ticks,
        ),
        souls=[
            SoulNode(
                name="Analyst",
                mind=MindNode(model="m1", tier="Tier1"),
                tokens=TokensDecl(input=1000, output=500),
            ),
            SoulNode(
                name="Trader",
                mind=MindNode(model="m2", tier="Tier1"),
                tokens=TokensDecl(input=400, output=200),
            ),
        ],
    )


def _spec(pricing: _PricingTable, **kw):
    return emit_smt(
        _program(**kw), pricing, source_text=_SOURCE_TEXT, today=TODAY
    )


def _manifest(spec):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=23,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.13.0",
    )


def _event(seq, tick, soul, kind="llm_call", it=0, ot=0, tc="0"):
    return TraceEvent(
        seq=seq, tick=tick, soul=soul, kind=kind,
        input_tokens=it, output_tokens=ot, tool_cost=tc,
        timestamp_utc="2026-05-25T00:00:00Z",
    )


def _signed_trace(spec, events):
    env = TraceEnvelope(
        nous_version="5.13.0",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=events,
    )
    return sign_trace(env, Ed25519PrivateKey.generate())


def _conforming(pricing):
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(
        spec,
        [
            _event(0, 0, "Analyst", it=900, ot=400),
            _event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    detail = verify_conformance(tr, man, spec, pricing)
    return spec, man, tr, detail


def test_build_certificate_records_verdict(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="2026-05-26T00:00:00Z"
    )
    assert cert.conformant is True
    assert cert.signature is None
    assert cert.transparency_log is None
    assert cert.source_sha256 == man.source_sha256
    assert cert.smt_spec_sha256 == man.smt_spec_sha256
    assert cert.pricing_sha256 == man.pricing_sha256


def test_certificate_binds_trace_by_hash(pricing: _PricingTable) -> None:
    import hashlib
    _spec_, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t"
    )
    assert cert.trace_sha256 == hashlib.sha256(
        tr.canonical_body_bytes()
    ).hexdigest()


def test_sign_then_verify_certificate(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t"
    )
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert signed.signature is not None
    assert verify_certificate_signature(signed) is True


def test_certificate_byte_determinism(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    c1 = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t"
    )
    c2 = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t"
    )
    assert (
        c1.certificate_canonical_body_bytes()
        == c2.certificate_canonical_body_bytes()
    )


def test_certificate_json_round_trip(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    signed = sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.13.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "conformance.json"
        p.write_text(certificate_json(signed), encoding="utf-8")
        loaded = load_certificate(str(p))
    assert loaded == signed
    assert verify_certificate_signature(loaded) is True


def test_tampered_certificate_fails_verify(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    signed = sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.13.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    bad = ConformanceCertificate(
        **{**signed.model_dump(), "conformant": False}
    )
    assert verify_certificate_signature(bad) is False


def test_non_conformant_is_certifiable(pricing: _PricingTable) -> None:
    spec = _spec(pricing, cost_cap="0.0001")
    man = _manifest(spec)
    tr = _signed_trace(spec, [_event(0, 0, "Analyst", it=1000, ot=500)])
    detail = verify_conformance(tr, man, spec, pricing)
    assert detail.ok is False
    signed = sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.13.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    assert signed.conformant is False
    assert verify_certificate_signature(signed) is True
    assert signed.errors


def test_offline_verifier_passes_conforming(pricing: _PricingTable) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    from manifest import manifest_json, sign_manifest, load_or_create_keypair
    signed = sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.13.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            certificate_json(signed), encoding="utf-8"
        )
        (dp / "trace.json").write_text(_trace_json(tr), encoding="utf-8")
        priv, pub, _ = load_or_create_keypair(dp / "k.key")
        sig = sign_manifest(man, priv)
        (dp / "manifest.json").write_text(
            manifest_json(man, sig, pub), encoding="utf-8"
        )
        r = subprocess.run(
            [sys.executable, str(dp / "verify_conformance_offline.py")],
            capture_output=True, text=True,
        )
    assert r.returncode == 0, r.stdout + r.stderr


def test_offline_verifier_detects_trace_tamper(
    pricing: _PricingTable,
) -> None:
    _spec_, man, tr, detail = _conforming(pricing)
    from manifest import manifest_json, sign_manifest, load_or_create_keypair
    signed = sign_certificate(
        build_certificate(
            detail, tr, man, nous_version="5.13.0", issued_utc="t"
        ),
        Ed25519PrivateKey.generate(),
    )
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        emit_conformance_verifier(str(dp), anchored=False)
        (dp / "conformance.json").write_text(
            certificate_json(signed), encoding="utf-8"
        )
        doc = json.loads(_trace_json(tr))
        doc["events"][0]["input_tokens"] = 99999
        (dp / "trace.json").write_text(json.dumps(doc), encoding="utf-8")
        priv, pub, _ = load_or_create_keypair(dp / "k.key")
        sig = sign_manifest(man, priv)
        (dp / "manifest.json").write_text(
            manifest_json(man, sig, pub), encoding="utf-8"
        )
        r = subprocess.run(
            [sys.executable, str(dp / "verify_conformance_offline.py")],
            capture_output=True, text=True,
        )
    assert r.returncode == 1


def test_anchored_verifier_assembles_and_compiles() -> None:
    src = build_conformance_verifier_v2(repr(KNOWN_REKOR_V2_LOG_KEYS))
    ast.parse(src)
    assert "verify_rekor_v2_anchor" in src
    assert "def main" in src


def test_emit_anchored_verifier_compiles() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = emit_conformance_verifier(d, anchored=True)
        ast.parse(p.read_text(encoding="utf-8"))


def _trace_json(tr: TraceEnvelope) -> str:
    doc = tr.persisted_dict()  # __s107_u2_testfix_persisted_v1__
    return json.dumps(doc, sort_keys=True)


_SOULED_SOURCE = (  # __nous_s98_certify_cli_test_fix_v1__
    "world Floor {\n"
    "    cost_cap: 0.50 USD\n"
    "    max_ticks: 5\n"
    "}\n"
    "soul Analyst {\n"
    "    mind: m1 @ Tier1\n"
    "    tokens: input=1000 output=500\n"
    "}\n"
    "soul Trader {\n"
    "    mind: m2 @ Tier1\n"
    "    tokens: input=400 output=200\n"
    "}\n"
)


def test_certify_cli_verdict_print(
    pricing: _PricingTable, tmp_path
) -> None:
    """certify CLI must reach exit 0 through its verdict-print line.

    Regression for the 5.13.0 detail.conformant crash (the attribute is .ok).
    Builds spec/manifest/trace from a souls-bearing source STRING so the
    CLI's re-emit from --source is consistent with the manifest. Unanchored
    (no network).
    """
    import argparse

    from parser import parse_nous
    from cli_conformance import cmd_conformance
    from manifest import (
        manifest_json,
        sign_manifest,
        load_or_create_keypair,
    )

    program = parse_nous(_SOULED_SOURCE)
    spec = emit_smt(
        program, pricing, source_text=_SOULED_SOURCE, today=TODAY
    )
    man = manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=11,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.13.1",
    )

    env = TraceEnvelope(
        nous_version="5.13.1",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[
            _event(0, 0, "Analyst", it=900, ot=400),
            _event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    tr = sign_trace(env, Ed25519PrivateKey.generate())

    src_p = tmp_path / "source.nous"
    src_p.write_text(_SOULED_SOURCE, encoding="utf-8")
    prices_p = tmp_path / "pricing.toml"
    prices_p.write_text(PRICING_TOML, encoding="utf-8")
    trace_p = tmp_path / "trace.json"
    trace_p.write_text(_trace_json(tr), encoding="utf-8")

    priv, pub, _ = load_or_create_keypair(tmp_path / "m.key")
    sig = sign_manifest(man, priv)
    man_p = tmp_path / "manifest.json"
    man_p.write_text(manifest_json(man, sig, pub), encoding="utf-8")

    out_p = tmp_path / "conformance.json"
    ns = argparse.Namespace(
        command="conformance",
        conformance_cmd="certify",
        trace=str(trace_p),
        manifest=str(man_p),
        prices=str(prices_p),
        source=str(src_p),
        out=str(out_p),
        key_path=str(tmp_path / "cert.key"),
        issued_utc="2026-05-26T00:00:00Z",
        anchor=None,
    )
    rc = cmd_conformance(ns)
    assert rc == 0
    assert out_p.is_file()

    loaded = load_certificate(str(out_p))
    assert verify_certificate_signature(loaded) is True
    assert loaded.conformant is True
    assert loaded.transparency_log is None


# __nous_s98_stage1_tests_v1__


def _full_bundle_json(pricing: _PricingTable, tmp_path) -> tuple[str, str, str]:
    """Build a souls-bearing, signed (cert, trace, manifest) triple as JSON."""
    import argparse  # noqa: F401
    from parser import parse_nous
    from manifest import (
        manifest_json as _manifest_json,
        sign_manifest,
        load_or_create_keypair,
    )

    src = _SOULED_SOURCE
    program = parse_nous(src)
    spec = emit_smt(program, pricing, source_text=src, today=TODAY)
    man = manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=11,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.13.1",
    )
    env = TraceEnvelope(
        nous_version="5.13.1",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[
            _event(0, 0, "Analyst", it=900, ot=400),
            _event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    tr = sign_trace(env, Ed25519PrivateKey.generate())

    priv, pub, _ = load_or_create_keypair(tmp_path / "mk.key")
    msig = sign_manifest(man, priv)
    man_str = _manifest_json(man, msig, pub)
    tr_str = _trace_json(tr)

    detail = verify_conformance(tr, man, spec, pricing)
    cert = build_certificate(
        detail=detail,
        trace=tr,
        manifest=man,
        nous_version="5.13.1",
        issued_utc="2026-05-26T00:00:00Z",
    )
    cpriv = Ed25519PrivateKey.generate()
    cert_signed = sign_certificate(cert, cpriv)
    return certificate_json(cert_signed), tr_str, man_str


def test_verify_from_json_full_bundle_passes(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, tr_s, man_s = _full_bundle_json(pricing, tmp_path)
    result = verify_certificate_from_json(cert_s, tr_s, man_s)
    assert result.verdict == "PASS"
    assert result.parsed is True
    assert result.signature.ok is True
    assert result.verdict_consistency.ok is True
    assert result.trace_binding.ok is True
    assert result.trace_signature.ok is True
    assert result.manifest_binding.ok is True
    assert result.anchor is None
    assert result.errors == []


def test_verify_from_json_cert_only_is_inconclusive(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, _, _ = _full_bundle_json(pricing, tmp_path)
    result = verify_certificate_from_json(cert_s)
    assert result.verdict == "INCONCLUSIVE"
    assert result.signature.ok is True
    assert result.verdict_consistency.ok is True
    assert result.trace_binding.skipped is True
    assert result.manifest_binding.skipped is True


def test_verify_from_json_malformed_json() -> None:
    result = verify_certificate_from_json("{not valid json}")
    assert result.verdict == "MALFORMED"
    assert result.parsed is False
    assert any("parse error" in e for e in result.errors)


def test_verify_from_json_tampered_signature(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, _, _ = _full_bundle_json(pricing, tmp_path)
    doc = json.loads(cert_s)
    sig = doc["signature"]["signature_b64"]
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    doc["signature"]["signature_b64"] = flipped
    tampered = json.dumps(doc)
    result = verify_certificate_from_json(tampered)
    assert result.verdict == "FAIL"
    assert result.signature.ok is False


def test_verify_from_json_trace_binding_mismatch(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, tr_s, man_s = _full_bundle_json(pricing, tmp_path)
    tr_doc = json.loads(tr_s)
    tr_doc["nous_version"] = "5.99.99"  # changes canonical body -> sha mismatch
    bad_trace = json.dumps(tr_doc)
    result = verify_certificate_from_json(cert_s, bad_trace, man_s)
    assert result.verdict == "FAIL"
    assert result.trace_binding.ok is False
    assert result.signature.ok is True


# __nous_s98_stage2_tests_v1__


def _client():
    from fastapi.testclient import TestClient
    from nous_api_server import app
    return TestClient(app)


def test_verify_conformance_endpoint_full_bundle_passes(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, tr_s, man_s = _full_bundle_json(pricing, tmp_path)
    r = _client().post(
        "/v1/verify-conformance",
        json={
            "certificate_json": cert_s,
            "trace_json": tr_s,
            "manifest_json": man_s,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["spec_version"] == "verify-conformance/v1"
    assert data["verdict"] == "PASS"
    assert data["signature"]["ok"] is True
    assert data["trace_binding"]["ok"] is True
    assert data["manifest_binding"]["ok"] is True
    assert data["errors"] == []


def test_verify_conformance_endpoint_cert_only_inconclusive(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, _, _ = _full_bundle_json(pricing, tmp_path)
    r = _client().post(
        "/v1/verify-conformance",
        json={"certificate_json": cert_s},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == "INCONCLUSIVE"
    assert data["signature"]["ok"] is True
    assert data["trace_binding"]["skipped"] is True
    assert data["manifest_binding"]["skipped"] is True


def test_verify_conformance_endpoint_malformed_json() -> None:
    r = _client().post(
        "/v1/verify-conformance",
        json={"certificate_json": "{not valid"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == "MALFORMED"
    assert data["parsed"] is False


def test_verify_from_json_manifest_binding_mismatch(
    pricing: _PricingTable, tmp_path
) -> None:
    cert_s, tr_s, man_s = _full_bundle_json(pricing, tmp_path)
    man_doc = json.loads(man_s)
    man_doc["source_sha256"] = "0" * 64
    bad_manifest = json.dumps(man_doc)
    result = verify_certificate_from_json(cert_s, tr_s, bad_manifest)
    assert result.verdict == "FAIL"
    assert result.manifest_binding.ok is False
    assert result.trace_binding.ok is True


# __nous_s98_stage1_anchored_regression_v1__


def test_verify_from_json_anchored_signature_ok(
    pricing: _PricingTable, tmp_path
) -> None:
    """Anchored cert: transparency_log MUST be excluded from canonical body.

    Regression for the Stage 1 cert-canon-bytes bug. The signature is
    computed over cert.certificate_canonical_body_bytes() which excludes
    BOTH signature and transparency_log. verify_certificate_from_json must
    use the same exclusion or the signature verify fails on any anchored
    cert. This test sets a fake transparency_log block on a freshly signed
    cert and asserts the signature still verifies.

    No network: the transparency_log fields are constructed locally to
    exercise the body-canonicalization path only. The anchor verification
    itself will fail (no real Rekor key matches), but the SIGNATURE check
    is what the bug broke, and that is what this test asserts.
    """
    from parser import parse_nous
    from manifest import (
        manifest_json as _manifest_json,
        sign_manifest,
        load_or_create_keypair,
    )
    src = _SOULED_SOURCE
    program = parse_nous(src)
    spec = emit_smt(program, pricing, source_text=src, today=TODAY)
    man = manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=11,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.13.1",
    )
    env = TraceEnvelope(
        nous_version="5.13.1",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[
            _event(0, 0, "Analyst", it=900, ot=400),
            _event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    tr = sign_trace(env, Ed25519PrivateKey.generate())

    priv, pub, _ = load_or_create_keypair(tmp_path / "mk.key")
    msig = sign_manifest(man, priv)
    man_str = _manifest_json(man, msig, pub)
    tr_str = _trace_json(tr)

    detail = verify_conformance(tr, man, spec, pricing)
    cert = build_certificate(
        detail=detail,
        trace=tr,
        manifest=man,
        nous_version="5.13.1",
        issued_utc="2026-05-26T00:00:00Z",
    )
    cert = cert.model_copy(update={
        "transparency_log": {
            "api_version": "rekor.sigstore.dev/v2alpha1",
            "log_index": 1,
            "checkpoint_envelope": "log2025-1.rekor.sigstore.dev\n1\n"
                                   "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n",
            "inclusion_proof_hashes": [],
            "leaf_signature_b64":
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        },
    })
    cpriv = Ed25519PrivateKey.generate()
    cert_signed = sign_certificate(cert, cpriv)
    cert_s = certificate_json(cert_signed)

    parsed = json.loads(cert_s)
    assert parsed.get("transparency_log") is not None, (
        "fixture must carry transparency_log to exercise the bug path"
    )

    result = verify_certificate_from_json(cert_s, tr_str, man_str)
    assert result.signature.ok is True, (
        "signature must verify even when transparency_log is present "
        f"(canonicalization bug): detail={result.signature.detail}"
    )
    assert result.verdict_consistency.ok is True
    assert result.trace_binding.ok is True
    assert result.trace_signature.ok is True
    assert result.manifest_binding.ok is True
    assert result.anchor is not None
    assert result.anchor.overall_ok is False
