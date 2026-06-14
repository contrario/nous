from __future__ import annotations
# __s141_u4_gated_emit_tests_v1__
# S141 U4: SMTSpec.gated_actions field + sha binding. Empty -> byte-identical;
# populated -> sorted+deduped GA: lines change the smt_spec sha.
from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, LawGatedNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from parser import parse_nous
from pricing import PricingTable
from smt_emit import emit_smt

_TODAY = date(2026, 4, 28)
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


def _spec(pricing, gated=None, events=None):
    prog = NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=4,
            gated_actions=[LawGatedNode(action=a) for a in (gated or [])],
            events=list(events or []),
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )
    return emit_smt(prog, pricing, source_text="x", today=_TODAY)


def test_field_default_empty(pricing: PricingTable) -> None:
    assert _spec(pricing).gated_actions == ()


def test_gated_populates_sorted_deduped(pricing: PricingTable) -> None:
    s = _spec(
        pricing,
        gated=["resolve", "escalate", "escalate"],
        events=["escalate", "resolve"],
    )
    assert s.gated_actions == ("escalate", "resolve")


def test_empty_gated_sha_byte_identical(pricing: PricingTable) -> None:
    s_explicit_empty = _spec(pricing, gated=[], events=["escalate"])
    s_default = _spec(pricing, gated=None, events=["escalate"])
    assert s_explicit_empty.sha256() == s_default.sha256()


def test_gated_changes_sha(pricing: PricingTable) -> None:
    s_no = _spec(pricing, gated=[], events=["escalate"])
    s_yes = _spec(pricing, gated=["escalate"], events=["escalate"])
    assert s_no.sha256() != s_yes.sha256()


def test_gated_sha_order_independent(pricing: PricingTable) -> None:
    s1 = _spec(
        pricing, gated=["escalate", "resolve"],
        events=["escalate", "resolve"],
    )
    s2 = _spec(
        pricing, gated=["resolve", "escalate"],
        events=["escalate", "resolve"],
    )
    assert s1.sha256() == s2.sha256()


def test_gated_flows_from_source(pricing: PricingTable) -> None:
    src = dedent("""\
        world W {
          cost_cap: 0.10 USD
          max_ticks: 4
          events { escalate }
          law gated(escalate)
        }
        soul S {
          mind: m1 @ Tier1
          tokens: input = 100 output = 50
        }
    """)
    prog = parse_nous(src)
    spec = emit_smt(prog, pricing, source_text=src, today=_TODAY)
    assert spec.gated_actions == ("escalate",)
