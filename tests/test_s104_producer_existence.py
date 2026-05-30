from __future__ import annotations

# __s104_producer_existence_tests_v1__
# S104 Stage B: a sequence law over an event that is never emitted passes
# vacuously. B1 surfaces it on ConformanceDetail.sequence_vacuous; B2 warns
# (SEQ-PROD) statically when no soul speaks a lawed event.

from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from conformance import _sequence_vacuous_laws, verify_conformance
from nous_trace import TraceEnvelope, TraceEvent
from pricing import PricingTable
from smt_emit import emit_smt
from parser import parse_nous
from verifier import NousVerifier

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


def _trace(events) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="x", world_name="W",
        source_sha256=_ZERO, smt_spec_sha256=_ZERO, pricing_sha256=_ZERO,
        events=list(events),
    )


def test_b1_vacuous_law_listed_when_event_absent(pricing: PricingTable) -> None:
    spec = _spec(pricing, [_before("a", "b")], ["a", "b"])
    vac = _sequence_vacuous_laws(_trace([]), spec)
    assert len(vac) == 1
    assert "before(a,b)" in vac[0]
    assert "'b'" in vac[0]


def test_b1_no_vacuous_when_no_laws(pricing: PricingTable) -> None:
    spec = _spec(pricing)
    assert _sequence_vacuous_laws(_trace([]), spec) == []


_LAW_UNSPOKEN = dedent("""\
    world W {
      cost_cap: 0.10 USD
      max_ticks: 4
      events { Ping, Pong }
      law before(Ping, Pong)
    }
    message Ping { v: string }
    message Pong { v: string }
    soul A {
      mind: claude-sonnet-4-6 @ Tier1
      tokens: input = 100 output = 50
      instinct {
        speak Ping(v: "x")
      }
      heal { on error => retry(2, error) }
    }
""")


def test_b2_seq_prod_warns_for_unspoken_lawed_event() -> None:
    program = parse_nous(_LAW_UNSPOKEN)
    result = NousVerifier(program).verify()
    seq_prod = [w for w in result.warnings if w.code == "SEQ-PROD"]
    assert len(seq_prod) == 1
    assert "Pong" in seq_prod[0].message
    assert "Ping" not in seq_prod[0].message
