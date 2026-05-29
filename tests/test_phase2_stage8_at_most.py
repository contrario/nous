from __future__ import annotations
# __phase2_stage8_at_most_tests_v1__
# Phase 2 Stage 8: at_most(N, label) cardinality operator -- four surfaces.
from datetime import date
from decimal import Decimal
from textwrap import dedent
import pytest
import tomllib
from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from conformance import _check_sequence_obligations
from nous_trace import TraceEnvelope, TraceEvent
from parser import parse_nous
from pricing import PricingTable
from smt_emit import SequenceLaw, emit_smt
from validator import validate_program

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


def _at_most(n: int, label: str) -> LawSequenceNode:
    return LawSequenceNode(
        kind="at_most", before_label=label, after_label=None, count=n,
    )


def _spec(pricing, laws=None, events=None):
    prog = NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=4,
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


def _ev(seq: int, action) -> TraceEvent:
    return TraceEvent(
        seq=seq, tick=0, soul="S", kind="llm_call",
        action=action, timestamp_utc="t",
    )


def _trace(events) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="x", world_name="W",
        source_sha256=_ZERO, smt_spec_sha256=_ZERO, pricing_sha256=_ZERO,
        events=list(events),
    )


_SRC = dedent("""\
    world W {
      cost_cap: 0.10 USD
      max_ticks: 4
      events { escalate, resolve }
      law at_most(2, escalate)
    }
    soul S {
      mind: gpt-5-2 @ Tier1
      tokens: input = 100 output = 50
    }
""")


def test_parse_at_most_builds_node() -> None:
    prog = parse_nous(_SRC)
    laws = prog.world.sequence_laws
    assert len(laws) == 1
    law = laws[0]
    assert law.kind == "at_most"
    assert law.before_label == "escalate"
    assert law.after_label is None
    assert law.count == 2


def test_validate_at_most_undeclared_label() -> None:
    prog = NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=4,
            sequence_laws=[_at_most(2, "ghost")],
            events=["escalate"],
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )
    result = validate_program(prog)
    assert not result.ok
    assert any(e.code == "SE002" for e in result.errors)


def test_emit_at_most_no_seq_assertions(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_at_most(2, "escalate")], ["escalate", "resolve"])
    assert spec.sequence_assertions == ()
    assert spec.sequence_laws == (
        SequenceLaw("at_most", "escalate", None, 2),
    )


def test_emit_at_most_byte_identity_with_pairwise(
    pricing: PricingTable,
) -> None:
    before = LawSequenceNode(
        kind="before", before_label="escalate", after_label="resolve",
    )
    spec_pair = _spec(pricing, [before], ["escalate", "resolve"])
    spec_both = _spec(
        pricing, [before, _at_most(2, "escalate")], ["escalate", "resolve"],
    )
    assert spec_both.sequence_assertions == spec_pair.sequence_assertions
    assert spec_both.sequence_declarations == spec_pair.sequence_declarations


def test_conformance_at_most_pass(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_at_most(2, "escalate")], ["escalate", "resolve"])
    trace = _trace([_ev(0, "escalate"), _ev(1, "escalate")])
    ok, errors = _check_sequence_obligations(trace, spec)
    assert ok
    assert errors == []


def test_conformance_at_most_fail(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_at_most(2, "escalate")], ["escalate", "resolve"])
    trace = _trace([
        _ev(0, "escalate"), _ev(1, "escalate"), _ev(2, "escalate"),
    ])
    ok, errors = _check_sequence_obligations(trace, spec)
    assert not ok
    assert any("at_most" in e for e in errors)


def test_conformance_at_most_vacuous_when_absent(
    pricing: PricingTable,
) -> None:
    spec = _spec(pricing, [_at_most(2, "escalate")], ["escalate", "resolve"])
    trace = _trace([_ev(0, "resolve")])
    ok, errors = _check_sequence_obligations(trace, spec)
    assert ok
    assert errors == []
