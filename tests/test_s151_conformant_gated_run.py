"""S151 U3 -- conformant gated WITNESSED-RUN teeth through verify_conformance.

Proves the existing recorder/embedder seam already carries U1's full decision
surface end to end: a gated_action event bearing a sign_gated_decision()
attestation for approved / denied / overridden satisfies conformance
obligation #5 (authorization_ok) under the REAL verify_conformance path, and
the verb is cryptographically bound through that path (an approval relabelled
as a refusal, or a refusal relabelled as an approval, fails). This closes the
verify_conformance end-to-end coverage deferred from U1.

Mirrors the S141/S139 harness (same _spec/_manifest/_signed_trace fixtures);
the only change is sign_gated_decision in place of sign_gated_action so the
decision verb rides through the source-derived, sha-bound spec.

Honest boundary (see docs/AUTHORIZATION_RUNTIME.md): this evidences that a
named principal recorded a decision bound to this exact (seq, action, proof
envelope). A denied/overridden decision is oversight EXERCISED and is conformant
(a valid signed human decision is present), NOT a violation. It does NOT prove
the decision correct, the principal authorized, the oversight meaningful, or
that a refusal was honored at runtime. The auto-routed speak-of-gated-action
path emits authorization=None and is CORRECTLY non-conformant: no human decided.

# __s151_u3_conformant_gated_run_module_v1__
"""
from __future__ import annotations

import base64
import tomllib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ast_nodes import (
    CostCap,
    LawGatedNode,
    MindNode,
    NousProgram,
    SoulNode,
    TokensDecl,
    WorldNode,
)
from conformance import sign_gated_decision, verify_conformance
from manifest import manifest_from_verify
from pricing import PricingTable as _PricingTable
from smt_emit import emit_smt
from smt_verify import VerifyResult
from nous_trace import AuthorizationAttestation, TraceEnvelope, TraceEvent, sign_trace

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


def _program(gated=()) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="Floor",
            cost_cap=CostCap(amount=Decimal("0.50"), currency="USD"),
            max_ticks=5,
            gated_actions=[LawGatedNode(action=a) for a in gated],
            events=list(gated),
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


def _spec(pricing: _PricingTable, gated=()):
    return emit_smt(_program(gated=gated), pricing, source_text=_SOURCE_TEXT, today=TODAY)


def _manifest(spec):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=23,
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
        nous_version="5.12.0",
    )


def _gated_event(seq, soul, action, authorization=None):
    return TraceEvent(
        seq=seq, tick=0, soul=soul, kind="gated_action",
        input_tokens=0, output_tokens=0, tool_cost="0",
        action=action, authorization=authorization,
        timestamp_utc="2026-05-25T00:00:00Z",
    )


def _signed_trace(spec, events):
    env = TraceEnvelope(
        nous_version="5.12.0",
        world_name=spec.world_name,
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=events,
    )
    return sign_trace(env, Ed25519PrivateKey.generate())


def _decision(spec, seq, action, decision, principal_id="alice"):
    return sign_gated_decision(
        Ed25519PrivateKey.generate(), spec.sha256(), seq, action,
        principal_id, "2026-05-25T00:00:00Z", decision,
    )


def _relabel(auth: AuthorizationAttestation, decision: str) -> AuthorizationAttestation:
    return AuthorizationAttestation(
        principal_id=auth.principal_id, approved_seq=auth.approved_seq,
        timestamp_utc=auth.timestamp_utc, public_key_b64=auth.public_key_b64,
        signature_b64=auth.signature_b64, decision=decision,
    )


# --- conformant gated witnessed run: all three oversight verbs ---------------

@pytest.mark.parametrize("verb", ["approved", "denied", "overridden"])
def test_gated_decision_conformant_end_to_end(pricing: _PricingTable, verb: str) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    auth = _decision(spec, 0, "escalate", verb)
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_denied_decision_is_oversight_exercised_not_violation(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    auth = _decision(spec, 0, "escalate", "denied")
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True


def test_approved_relabelled_denied_fails_end_to_end(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    appr = _decision(spec, 0, "escalate", "approved")
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", _relabel(appr, "denied"))])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_denied_relabelled_approved_fails_end_to_end(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    den = _decision(spec, 0, "escalate", "denied")
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", _relabel(den, "approved"))])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_overridden_relabelled_approved_fails_end_to_end(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    ovr = _decision(spec, 0, "escalate", "overridden")
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", _relabel(ovr, "approved"))])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_unattested_gated_event_remains_non_conformant(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    tr = _signed_trace(spec, [_gated_event(0, "Analyst", "escalate", authorization=None)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False
