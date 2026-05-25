"""S96 runtime conformance -- offline end-to-end tests.

Drives the real pipeline (emit_smt -> manifest_from_verify -> sign trace ->
verify_conformance) with no network and no z3. Covers the six obligation
booleans and the refuse-over-guess preconditions:

  - conforming trace                     -> PASS
  - soul over its token bound            -> assumption_discharge_ok False
  - total over cap                       -> bound_transfer_ok False
  - tampered trace signature             -> trace_signature_ok False
  - out-of-surface soul                  -> ConformancePreconditionError
  - priced tool_call                     -> ConformancePreconditionError
  - binding mismatch (wrong manifest)    -> binding_ok False
  - per-soul call count > max_ticks      -> assumption_discharge_ok False
"""
from __future__ import annotations

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
    verify_conformance,
)
from manifest import manifest_from_verify
from pricing import PricingTable as _PricingTable
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
        nous_version="5.12.0",
    )


def _event(seq, tick, soul, kind="llm_call", it=0, ot=0, tc="0"):
    return TraceEvent(
        seq=seq, tick=tick, soul=soul, kind=kind,
        input_tokens=it, output_tokens=ot, tool_cost=tc,
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


def test_conforming_trace_passes(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(
        spec,
        [
            _event(0, 0, "Analyst", it=900, ot=400),
            _event(1, 1, "Trader", it=300, ot=150),
        ],
    )
    d = verify_conformance(tr, man, spec, pricing)
    assert d.ok
    assert d.binding_ok
    assert d.assumption_discharge_ok
    assert d.bound_transfer_ok
    assert d.trace_signature_ok


def test_soul_over_token_bound_fails_discharge(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(spec, [_event(0, 0, "Analyst", it=2000, ot=400)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.assumption_discharge_ok is False
    assert d.ok is False


def test_total_over_cap_fails_bound_transfer(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, cost_cap="0.0001")
    man = _manifest(spec)
    tr = _signed_trace(spec, [_event(0, 0, "Analyst", it=1000, ot=500)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.bound_transfer_ok is False
    assert d.assumption_discharge_ok is True
    assert d.ok is False


def test_tampered_trace_signature_fails(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    good = _signed_trace(spec, [_event(0, 0, "Analyst", it=900, ot=400)])
    tampered = TraceEnvelope(
        trace_schema_version=good.trace_schema_version,
        nous_version=good.nous_version,
        world_name=good.world_name,
        source_sha256=good.source_sha256,
        smt_spec_sha256=good.smt_spec_sha256,
        pricing_sha256=good.pricing_sha256,
        events=[_event(0, 0, "Analyst", it=901, ot=400)],
        signature=good.signature,
    )
    d = verify_conformance(tampered, man, spec, pricing)
    assert d.trace_signature_ok is False
    assert d.ok is False


def test_out_of_surface_soul_refuses(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(spec, [_event(0, 0, "Ghost", it=10, ot=10)])
    with pytest.raises(ConformancePreconditionError):
        verify_conformance(tr, man, spec, pricing)


def test_priced_tool_call_refuses(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    man = _manifest(spec)
    tr = _signed_trace(
        spec, [_event(0, 0, "Analyst", kind="tool_call", tc="0.01")]
    )
    with pytest.raises(ConformancePreconditionError):
        verify_conformance(tr, man, spec, pricing)


def test_binding_mismatch_fails_binding(pricing: _PricingTable) -> None:
    spec = _spec(pricing)
    other = _spec(pricing, cost_cap="0.40")  # different spec -> different sha
    man = _manifest(other)
    tr = _signed_trace(spec, [_event(0, 0, "Analyst", it=900, ot=400)])
    d = verify_conformance(tr, man, spec, pricing)
    assert d.binding_ok is False
    assert d.ok is False


def test_call_count_over_max_ticks_fails_discharge(
    pricing: _PricingTable,
) -> None:
    spec = _spec(pricing, max_ticks=5)
    man = _manifest(spec)
    events = [_event(i, i % 5, "Analyst", it=10, ot=10) for i in range(6)]
    tr = _signed_trace(spec, events)
    d = verify_conformance(tr, man, spec, pricing)
    assert d.assumption_discharge_ok is False
