"""S110 U3 -- unit tests for the build_run_remedy admissibility gate.

The gate is the only place the Phase 2.0 admissibility logic lives, so it
carries its own CI coverage independent of the U7 end-to-end path. Each
fail-closed branch is exercised in isolation so a red test localizes to the
gate, not to the signing pipeline (which the S97 suite already proves) and not
to emit_smt/pricing/z3.

The authentic-certificate fixture is constructed directly as a
ConformanceCertificate (every field is a primitive; build_certificate is only
a field-copier from a ConformanceDetail/TraceEnvelope/Manifest triple, none of
which the gate needs) and then signed with the real sign_certificate over the
real certificate_canonical_body_bytes. The fixture's faithfulness is asserted
THROUGH the live verify_certificate_from_json: an authentic cert-only call must
yield signature.ok True, verdict_consistency.ok True, verdict INCONCLUSIVE with
both bindings skipped. If that assertion ever fails, the fixture -- not the
gate -- is wrong.

# __s110_u3_build_run_remedy_tests_v1__
"""
from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ast_nodes import (
    HealActionNode,
    HealNode,
    HealRuleNode,
    HealStrategy,
    SoulNode,
    heal_path_digest,
)
from build_run_remedy import admissible_promotions
from conformance import (
    CERTIFICATE_SCHEMA_VERSION,
    ConformanceCertificate,
    certificate_json,
    sign_certificate,
    verify_certificate_from_json,
)
from parser import parse_nous
from remedy_proof import REMEDY_PROOF_SCHEMA_VERSION, RemedyProofError
from run_identity import MemoryConsultationError

_HEX64 = "a" * 64

_SOULED_HEAL_SOURCE = """\
world Floor {
    cost_cap: 0.50 USD
    max_ticks: 5
}

soul Recon {
    mind: claude-haiku-4-5 @ Tier0A
    heal {
        on timeout => retry(2, exponential)
        on error   => sleep 1s
    }
}

soul Analyst {
    mind: claude-haiku-4-5 @ Tier0A
    heal {
        on timeout => retry(1, exponential)
    }
}
"""


def _authentic_cert_dict() -> dict:
    """A real signed certificate, all six obligations True + conformant True,
    schema-version-faithful. Signed over real canonical body bytes."""
    cert = ConformanceCertificate(
        certificate_schema_version=CERTIFICATE_SCHEMA_VERSION,
        nous_version="5.25.0",
        world_name="Floor",
        issued_utc="2026-06-01T00:00:00Z",
        source_sha256=_HEX64,
        smt_spec_sha256=_HEX64,
        pricing_sha256=_HEX64,
        trace_sha256=_HEX64,
        binding_ok=True,
        surface_ok=True,
        assumption_discharge_ok=True,
        bound_transfer_ok=True,
        authorization_ok=True,
        trace_signature_ok=True,
        sequence_ok=True,
        conformant=True,
        realized_total="0.10",
        cost_cap="0.50",
        cost_currency="USD",
    )
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    return json.loads(certificate_json(signed))


def _proof(digest: str, cert: dict) -> dict:
    return {
        "remedy_proof_schema_version": REMEDY_PROOF_SCHEMA_VERSION,
        "promoted_heal_path_sha256": digest,
        "certificate": cert,
    }


def _souls_from_source() -> list[SoulNode]:
    return parse_nous(_SOULED_HEAL_SOURCE).souls


def _digest_for(souls: list[SoulNode], soul_name: str, error_type: str) -> str:
    for s in souls:
        if s.name != soul_name or s.heal is None:
            continue
        for r in s.heal.rules:
            if r.error_type == error_type:
                return heal_path_digest(r)
    raise AssertionError(f"no rule {soul_name}/{error_type} in fixture")


def test_fixture_authentic_cert_is_cert_only_inconclusive() -> None:
    """Safeguard: the authentic fixture must verify cert-only exactly as the
    gate relies on -- signature.ok True, verdict_consistency.ok True, verdict
    INCONCLUSIVE, both bindings skipped. If this fails the fixture is wrong."""
    result = verify_certificate_from_json(json.dumps(_authentic_cert_dict()))
    assert result.signature.ok is True
    assert result.verdict_consistency.ok is True
    assert result.verdict == "INCONCLUSIVE"
    assert result.trace_binding.skipped is True
    assert result.manifest_binding.skipped is True


def test_admit_single_declared_authentic() -> None:
    souls = _souls_from_source()
    d = _digest_for(souls, "Recon", "timeout")
    out = admissible_promotions([_proof(d, _authentic_cert_dict())], souls)
    assert out == [d]


def test_parse_failure_raises_remedy_proof_error() -> None:
    souls = _souls_from_source()
    with pytest.raises(RemedyProofError):
        admissible_promotions(["not-a-dict"], souls)


def test_cert_signature_fail_excluded_not_raised() -> None:
    souls = _souls_from_source()
    d = _digest_for(souls, "Recon", "timeout")
    cert = _authentic_cert_dict()
    sig = cert["signature"]["signature_b64"]
    cert["signature"]["signature_b64"] = ("B" if sig[0] != "B" else "C") + sig[1:]
    out = admissible_promotions([_proof(d, cert)], souls)
    assert out == []


def test_cert_verdict_inconsistency_excluded_not_raised() -> None:
    souls = _souls_from_source()
    d = _digest_for(souls, "Recon", "timeout")
    cert = _authentic_cert_dict()
    cert["conformant"] = False
    out = admissible_promotions([_proof(d, cert)], souls)
    assert out == []


def test_non_declared_digest_excluded_at_c_not_conflict() -> None:
    souls = _souls_from_source()
    bogus = "f" * 64
    out = admissible_promotions([_proof(bogus, _authentic_cert_dict())], souls)
    assert out == []


def test_two_souls_same_error_type_different_digests_no_conflict() -> None:
    """Per-(soul, error_type) scope: Recon.timeout and Analyst.timeout share
    the error_type name but are different souls with different digests
    (retry(2) vs retry(1)) -> separate dispatch chains, both admissible."""
    souls = _souls_from_source()
    d_recon = _digest_for(souls, "Recon", "timeout")
    d_analyst = _digest_for(souls, "Analyst", "timeout")
    assert d_recon != d_analyst
    out = admissible_promotions(
        [_proof(d_recon, _authentic_cert_dict()),
         _proof(d_analyst, _authentic_cert_dict())],
        souls,
    )
    assert sorted(out) == sorted([d_recon, d_analyst])


def test_identical_digest_collapses_no_conflict() -> None:
    souls = _souls_from_source()
    d = _digest_for(souls, "Recon", "timeout")
    out = admissible_promotions(
        [_proof(d, _authentic_cert_dict()), _proof(d, _authentic_cert_dict())],
        souls,
    )
    assert out == [d]


def _first_heal_strategy() -> HealStrategy:
    return next(iter(HealStrategy))


def _souls_with_duplicate_error_type() -> list[SoulNode]:
    """Hand-built: two rules with the SAME error_type in ONE soul, different
    actions -> different whole-rule digests. The grammar permits duplicate
    error_type in a heal block (heal_rule*, no dedupe in parser or validator),
    but no shipped .nous exercises it, so the fixture is constructed directly
    via the same node constructors the parser uses. This is the FQ2 conflict
    shape: same (soul, error_type), two different digests, one trigger -- only
    one can fire first."""
    r1 = HealRuleNode(error_type="timeout", actions=[])
    r2 = HealRuleNode(
        error_type="timeout",
        actions=[HealActionNode(strategy=_first_heal_strategy(), params={})],
    )
    return [SoulNode(name="Recon", heal=HealNode(rules=[r1, r2]))]


def test_fq2_conflict_same_soul_same_error_type_raises() -> None:
    souls = _souls_with_duplicate_error_type()
    r1, r2 = souls[0].heal.rules
    d1, d2 = heal_path_digest(r1), heal_path_digest(r2)
    assert d1 != d2
    with pytest.raises(MemoryConsultationError) as ei:
        admissible_promotions(
            [_proof(d1, _authentic_cert_dict()),
             _proof(d2, _authentic_cert_dict())],
            souls,
        )
    msg = str(ei.value)
    assert "('Recon', 'timeout')" in msg
    assert d1 in msg and d2 in msg


def test_fq2_conflict_aborts_globally() -> None:
    """A conflict in one (soul, error_type) refuses ALL promotions, including
    an unrelated admissible one in another soul."""
    dup = _souls_with_duplicate_error_type()
    extra = parse_nous(_SOULED_HEAL_SOURCE).souls
    analyst = [s for s in extra if s.name == "Analyst"]
    souls = dup + analyst
    r1, r2 = souls[0].heal.rules
    d1, d2 = heal_path_digest(r1), heal_path_digest(r2)
    d_analyst = _digest_for(souls, "Analyst", "timeout")
    with pytest.raises(MemoryConsultationError):
        admissible_promotions(
            [_proof(d1, _authentic_cert_dict()),
             _proof(d2, _authentic_cert_dict()),
             _proof(d_analyst, _authentic_cert_dict())],
            souls,
        )


def test_empty_inputs_return_empty() -> None:
    assert admissible_promotions([], []) == []
    assert admissible_promotions([], _souls_from_source()) == []
