"""S139 U2 -- conformance obligation #5 (authorization) teeth.

Obligation #5 was vacuously-true not by design but by IMPOSSIBILITY: the
verifier signed `trace.canonical_body_bytes() + seq`, a preimage that
INCLUDES the attestation's own signature, so no verifying attestation could
ever be constructed (S139 U1 finding). U1 replaced that with a domain-
separated, envelope-bound, identity-bound preimage and added the issuer-side
signer `sign_gated_action`. These teeth prove the now-constructable positive
path and every refuse/negative path, with direct fixtures (no runtime gating
emission exists yet -- that is the separate grammar arc).

SCOPE the teeth pin honestly: obligation #5 proves presence + binding +
identity of an approval for events the trace LABELS gated_action, bound to
the exact decision (seq, action), approver (principal_id key), and proof
envelope (smt_spec_sha256). It does NOT prove COMPLETENESS of the labelling
(which actions ought to be gated) -- gated_actions is read from the advisory
proof_assumptions sibling; completeness needs source-derived signed gating
(documented in RUNTIME_CONFORMANCE.md, future grammar arc). It also proves
only that SOME key bound to the principal_id label signed the decision, not
that it is the RIGHT key (key-trust is a separate layer, as for the manifest
signer).
"""
from __future__ import annotations

import dataclasses
import tomllib
from datetime import date, datetime, timezone

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
    ConformancePreconditionError,
    sign_gated_action,
    verify_conformance,
)
from manifest import manifest_from_verify
from pricing import PricingTable as _PricingTable
from smt_emit import emit_smt
from smt_verify import VerifyResult
from nous_trace import (
    AuthorizationAttestation,
    TraceEnvelope,
    TraceEvent,
    sign_trace,
)

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
    return emit_smt(_program(**kw), pricing, source_text=_SOURCE_TEXT, today=TODAY)


def _manifest(spec, gated_actions=None):
    man = manifest_from_verify(
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
        nous_version="5.12.0",
    )
    if gated_actions is not None:
        man = dataclasses.replace(
            man, proof_assumptions={"gated_actions": list(gated_actions)}
        )
    return man


def _llm_event(seq, tick, soul, it=0, ot=0):
    return TraceEvent(
        seq=seq, tick=tick, soul=soul, kind="llm_call",
        input_tokens=it, output_tokens=ot, tool_cost="0",
        timestamp_utc="2026-05-25T00:00:00Z",
    )


def _gated_event(seq, tick, soul, action, authorization=None):
    return TraceEvent(
        seq=seq, tick=tick, soul=soul, kind="gated_action",
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


def _approval(spec, seq, action, principal_id="alice",
              approver_key=None, smt_spec_sha256=None):
    key = approver_key if approver_key is not None else Ed25519PrivateKey.generate()
    sha = smt_spec_sha256 if smt_spec_sha256 is not None else spec.sha256()
    return sign_gated_action(
        key, sha, seq, action, principal_id, "2026-05-25T00:00:00Z"
    )


def test_gated_action_with_valid_attestation_passes(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=["escalate"])
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_gated_action_without_attestation_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=["escalate"])
    tr = _signed_trace(
        spec, [_gated_event(0, 0, "Analyst", "escalate", authorization=None)]
    )
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_wrong_approved_seq_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=["escalate"])
    # approval minted for seq=1 but attached to the seq=0 event
    auth = _approval(spec, seq=1, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_tampered_signature_fails(
    pricing: _PricingTable,
) -> None:
    import base64

    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=["escalate"])
    auth = _approval(spec, seq=0, action="escalate")
    bad = AuthorizationAttestation(
        principal_id=auth.principal_id,
        approved_seq=auth.approved_seq,
        timestamp_utc=auth.timestamp_utc,
        public_key_b64=auth.public_key_b64,
        signature_b64=base64.b64encode(b"\x00" * 64).decode("ascii"),
    )
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", bad)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_wrong_action_replay_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=["escalate", "delete_all"])
    # approval minted for "escalate" replayed onto a "delete_all" event
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(
        spec, [_gated_event(0, 0, "Analyst", "delete_all", auth)]
    )
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_wrong_envelope_replay_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    other = _spec(pricing, cost_cap="0.40")  # different smt_spec_sha256
    man = _manifest(spec, gated_actions=["escalate"])
    # approval bound to a DIFFERENT envelope's sha, attached to this trace
    auth = _approval(spec, seq=0, action="escalate",
                     smt_spec_sha256=other.sha256())
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_not_declared_refuses(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    man = _manifest(spec, gated_actions=[])  # "escalate" not declared
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    with pytest.raises(ConformancePreconditionError):
        verify_conformance(tr, man, spec, pricing)


def test_no_gated_events_authorization_vacuously_true(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(spec, [_llm_event(0, 0, "Analyst", it=10, ot=10)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True
