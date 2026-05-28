from __future__ import annotations

# __phase2_stage5_seq_tests_v1__
# Phase 2 Stage 5a: runtime sequence conformance (seventh obligation).

from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from conformance import ConformanceDetail, _check_sequence_obligations
from nous_trace import TraceEnvelope, TraceEvent
from pricing import PricingTable
from smt_emit import emit_smt


_TODAY = date(2026, 4, 28)
_ZERO = "0" * 64

_PRICING_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."m1"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")


@pytest.fixture
def pricing() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(_PRICING_TOML))


def _before(a: str, b: str) -> LawSequenceNode:
    return LawSequenceNode(kind="before", before_label=a, after_label=b)


def _spec(pricing, laws=None, events=None):
    prog = NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=2,
            sequence_laws=list(laws or []),
            events=list(events or []),
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )
    return emit_smt(prog, pricing, source_text="x", today=_TODAY)


def _ev(seq: int, action, kind: str = "llm_call") -> TraceEvent:
    return TraceEvent(
        seq=seq, tick=0, soul="S", kind=kind, action=action, timestamp_utc="t",
    )


def _trace(events) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="x", world_name="W",
        source_sha256=_ZERO, smt_spec_sha256=_ZERO, pricing_sha256=_ZERO,
        events=list(events),
    )


def _detail(**over) -> ConformanceDetail:
    base = dict(
        binding_ok=True, surface_ok=True, assumption_discharge_ok=True,
        bound_transfer_ok=True, authorization_ok=True, trace_signature_ok=True,
        realized_total="0", cost_cap="0.10",
    )
    base.update(over)
    return ConformanceDetail(**base)


def test_emit_populates_sequence_laws(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    assert spec.sequence_laws == (("before", "a", "b"),)


def test_cost_only_spec_has_no_sequence_laws(pricing: PricingTable) -> None:
    assert _spec(pricing).sequence_laws == ()


def test_vacuous_when_no_laws(pricing: PricingTable) -> None:
    ok, errs = _check_sequence_obligations(_trace([]), _spec(pricing))
    assert ok is True and errs == []


def test_holds_a_before_b(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    ok, errs = _check_sequence_obligations(
        _trace([_ev(0, "a"), _ev(1, "b")]), spec,
    )
    assert ok is True and errs == []


def test_violated_b_before_a(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    ok, errs = _check_sequence_obligations(
        _trace([_ev(0, "b"), _ev(1, "a")]), spec,
    )
    assert ok is False
    assert any("before(a,b)" in e for e in errs)


def test_violated_b_with_no_a(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    ok, errs = _check_sequence_obligations(_trace([_ev(0, "b")]), spec)
    assert ok is False


def test_vacuous_when_no_b_events(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    ok, errs = _check_sequence_obligations(_trace([_ev(0, "a")]), spec)
    assert ok is True and errs == []


def test_action_none_events_ignored(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    ok, errs = _check_sequence_obligations(
        _trace([_ev(0, None), _ev(1, "a"), _ev(2, "b")]), spec,
    )
    assert ok is True


def test_chain_two_laws_holds(pricing: PricingTable) -> None:
    spec = _spec(
        pricing, [_before("a", "b"), _before("b", "c")], ["a", "b", "c"],
    )
    ok, errs = _check_sequence_obligations(
        _trace([_ev(0, "a"), _ev(1, "b"), _ev(2, "c")]), spec,
    )
    assert ok is True and errs == []


def test_detail_ok_conjoins_sequence_ok() -> None:
    assert _detail().ok is True
    assert _detail(sequence_ok=True).ok is True
    assert _detail(sequence_ok=False).ok is False
