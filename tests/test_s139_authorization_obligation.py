"""S141 U5 -- conformance obligation #5 (authorization) teeth, now
source-derived. S139 gave obligation #5 its constructable preimage and
proved presence + binding + identity of an approval for trace-LABELLED
gated_action events. The labelling itself was read from the advisory,
unsigned proof_assumptions sibling -- a documented trust hole.

S141 closes that hole: the gated set is declared in source
('law gated(<action>)'), folded into the SMTSpec, hashed into
smt_spec_sha256 (GA: lines), and read by the verifier from the
re-derived, sha-bound spec -- NOT from the sibling. These teeth migrate
the S139 presence proofs onto the signed source and add completeness
teeth proving a tampered sibling cannot change the verdict in either
direction (cannot remove gating, cannot add it).

Still NOT proven here: key-trust (that the approver key is the RIGHT
key) -- a separate layer, as for the manifest signer.
"""
from __future__ import annotations

import dataclasses
import tomllib
from datetime import date, datetime, timezone

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


def _program(cost_cap: str = "0.50", max_ticks: int = 5, gated=()) -> NousProgram:
    from decimal import Decimal

    return NousProgram(
        world=WorldNode(
            name="Floor",
            cost_cap=CostCap(amount=Decimal(cost_cap), currency="USD"),
            max_ticks=max_ticks,
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


def _spec(pricing: _PricingTable, gated=(), **kw):
    return emit_smt(
        _program(gated=gated, **kw), pricing,
        source_text=_SOURCE_TEXT, today=TODAY,
    )


def _manifest(spec, sibling_gated=None):
    """Build a manifest. sibling_gated injects the ADVISORY proof_assumptions
    sibling -- which the S141 verifier IGNORES (used only by tamper teeth)."""
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
    if sibling_gated is not None:
        man = dataclasses.replace(
            man, proof_assumptions={"gated_actions": list(sibling_gated)}
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


# --- migrated S139 presence teeth (gating now in the signed spec) -----------

def test_gated_action_with_valid_attestation_passes(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_gated_action_without_attestation_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    tr = _signed_trace(
        spec, [_gated_event(0, 0, "Analyst", "escalate", authorization=None)]
    )
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_wrong_approved_seq_fails(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
    auth = _approval(spec, seq=1, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_tampered_signature_fails(
    pricing: _PricingTable,
) -> None:
    import base64

    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)
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
    spec = _spec(pricing, gated=["escalate", "delete_all"])
    man = _manifest(spec)
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
    spec = _spec(pricing, gated=["escalate"])
    other = _spec(pricing, gated=["escalate"], cost_cap="0.40")
    man = _manifest(spec)
    auth = _approval(spec, seq=0, action="escalate",
                     smt_spec_sha256=other.sha256())
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_gated_action_not_declared_refuses(pricing: _PricingTable) -> None:
    spec = _spec(pricing, gated=[])  # "escalate" not declared in signed spec
    man = _manifest(spec)
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


# --- S141 completeness teeth (gating sourced from signed spec) --------------

def test_gating_sourced_from_signed_spec_not_sibling(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec)  # NO advisory sibling at all
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_tampered_sibling_cannot_remove_gating(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=["escalate"])
    man = _manifest(spec, sibling_gated=[])  # sibling lies: nothing gated
    tr = _signed_trace(
        spec, [_gated_event(0, 0, "Analyst", "escalate", authorization=None)]
    )
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert d.ok is False


def test_tampered_sibling_cannot_add_gating(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, gated=[])  # signed spec gates nothing
    man = _manifest(spec, sibling_gated=["escalate"])  # sibling lies: gated
    auth = _approval(spec, seq=0, action="escalate")
    tr = _signed_trace(spec, [_gated_event(0, 0, "Analyst", "escalate", auth)])
    with pytest.raises(ConformancePreconditionError):
        verify_conformance(tr, man, spec, pricing)
