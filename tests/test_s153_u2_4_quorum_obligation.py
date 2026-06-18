"""S153 U2.4 -- gated quorum enforced through verify_conformance.

K > 1 requires K distinct valid APPROVING keys among {authorization} U
co_authorizations. Mirrors the S151 conformant-gated harness; adds quorum cases.
# __s153_u2_4_quorum_obligation_tests_v1__
"""
from __future__ import annotations

import base64
import tomllib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ast_nodes import (
    CostCap, LawGatedNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from conformance import sign_gated_decision, verify_conformance
from manifest import manifest_from_verify
from pricing import PricingTable as _PricingTable
from smt_emit import emit_smt
from smt_verify import VerifyResult
from nous_trace import (
    AuthorizationAttestation, TraceEnvelope, TraceEvent, sign_trace,
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


def _program(gated_pairs=()) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="Floor",
            cost_cap=CostCap(amount=Decimal("0.50"), currency="USD"),
            max_ticks=5,
            gated_actions=[
                LawGatedNode(action=a, quorum=k) for (a, k) in gated_pairs
            ],
            events=[a for (a, k) in gated_pairs],
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


def _spec(pricing, gated_pairs=()):
    return emit_smt(
        _program(gated_pairs=gated_pairs), pricing,
        source_text=_SOURCE_TEXT, today=TODAY,
    )


def _manifest(spec):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven", spec=spec, solver_name="z3",
            solver_version="z3 4.16.0", elapsed_ms=23,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
        ),
        nous_version="5.12.0",
    )


def _event(seq, action, auth=None, co=None):
    return TraceEvent(
        seq=seq, tick=0, soul="Analyst", kind="gated_action",
        input_tokens=0, output_tokens=0, tool_cost="0",
        action=action, authorization=auth, co_authorizations=co,
        timestamp_utc="2026-05-25T00:00:00Z",
    )


def _signed_trace(spec, events):
    env = TraceEnvelope(
        nous_version="5.12.0", world_name=spec.world_name,
        source_sha256=spec.source_sha256, smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256, events=events,
    )
    return sign_trace(env, Ed25519PrivateKey.generate())


def _decision(spec, seq, action, decision, principal_id, key=None):
    key = key or Ed25519PrivateKey.generate()
    return sign_gated_decision(
        key, spec.sha256(), seq, action, principal_id,
        "2026-05-25T00:00:00Z", decision,
    )


def _corrupt_sig(att):
    raw = bytearray(base64.b64decode(att.signature_b64))
    raw[0] ^= 0xFF
    return AuthorizationAttestation(
        principal_id=att.principal_id, approved_seq=att.approved_seq,
        timestamp_utc=att.timestamp_utc, public_key_b64=att.public_key_b64,
        signature_b64=base64.b64encode(bytes(raw)).decode("ascii"),
        decision=att.decision,
    )


def test_quorum_two_met_two_distinct_keys(pricing) -> None:
    spec = _spec(pricing, [("escalate", 2)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    c = _decision(spec, 0, "escalate", "approved", "bob")
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_quorum_two_only_primary_fails(pricing) -> None:
    spec = _spec(pricing, [("escalate", 2)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    tr = _signed_trace(spec, [_event(0, "escalate", p, None)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
    assert any("quorum not met" in e for e in d.errors)


def test_quorum_two_same_key_fails(pricing) -> None:
    spec = _spec(pricing, [("escalate", 2)])
    man = _manifest(spec)
    k = Ed25519PrivateKey.generate()
    p = _decision(spec, 0, "escalate", "approved", "alice", key=k)
    c = _decision(spec, 0, "escalate", "approved", "alice2", key=k)
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False


def test_quorum_two_primary_approved_co_denied_fails(pricing) -> None:
    spec = _spec(pricing, [("escalate", 2)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    c = _decision(spec, 0, "escalate", "denied", "bob")
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False


def test_quorum_two_co_sig_tampered_fails(pricing) -> None:
    spec = _spec(pricing, [("escalate", 2)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    c = _corrupt_sig(_decision(spec, 0, "escalate", "approved", "bob"))
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False


def test_quorum_one_plain_gated_unchanged(pricing) -> None:
    spec = _spec(pricing, [("escalate", 1)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    tr = _signed_trace(spec, [_event(0, "escalate", p, None)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True
    assert d.ok is True


def test_quorum_three_met(pricing) -> None:
    spec = _spec(pricing, [("escalate", 3)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    c1 = _decision(spec, 0, "escalate", "approved", "bob")
    c2 = _decision(spec, 0, "escalate", "approved", "carol")
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c1, c2])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is True


def test_quorum_three_two_distinct_fails(pricing) -> None:
    spec = _spec(pricing, [("escalate", 3)])
    man = _manifest(spec)
    p = _decision(spec, 0, "escalate", "approved", "alice")
    c1 = _decision(spec, 0, "escalate", "approved", "bob")
    tr = _signed_trace(spec, [_event(0, "escalate", p, [c1])])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.authorization_ok is False
