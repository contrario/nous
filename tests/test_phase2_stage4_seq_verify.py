from __future__ import annotations

# __phase2_stage4_seq_tests_v1__
# Phase 2 Stage 4: Z3 verification of sequence consistency.

from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

pytest.importorskip("z3")

from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from pricing import PricingTable
from smt_emit import emit_smt
from smt_verify import (
    SequenceVerifyResult, format_sequence_verdict, verify_sequence,
)


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


def _prog(sequence_laws=None, events=None) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=2,
            sequence_laws=list(sequence_laws or []),
            events=list(events or []),
        ),
        souls=[SoulNode(
            name="S",
            mind=MindNode(model="m1", tier="Tier1"),
            tokens=TokensDecl(input=100, output=50),
        )],
    )


def _before(a: str, b: str) -> LawSequenceNode:
    return LawSequenceNode(kind="before", before_label=a, after_label=b)


def _spec(pricing, laws=None, events=None):
    return emit_smt(_prog(laws, events), pricing, source_text="x", today=_TODAY)


def test_vacuous_when_no_sequence_laws(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(pricing))
    assert r.verdict == "vacuous"
    assert r.solver_version == "n/a"


def test_consistent_single_law(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(pricing, [_before("a", "b")], ["a", "b"]))
    assert r.verdict == "consistent"


def test_consistent_chain(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(
        pricing, [_before("a", "b"), _before("b", "c")], ["a", "b", "c"],
    ))
    assert r.verdict == "consistent"


def test_inconsistent_two_cycle(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(
        pricing, [_before("a", "b"), _before("b", "a")], ["a", "b"],
    ))
    assert r.verdict == "inconsistent"
    assert "contradict" in (r.error or "")


def test_inconsistent_three_cycle(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(
        pricing,
        [_before("a", "b"), _before("b", "c"), _before("c", "a")],
        ["a", "b", "c"],
    ))
    assert r.verdict == "inconsistent"


def test_result_carries_solver_metadata(pricing: PricingTable) -> None:
    r = verify_sequence(_spec(pricing, [_before("a", "b")], ["a", "b"]))
    assert isinstance(r, SequenceVerifyResult)
    assert "z3" in r.solver_version
    assert r.elapsed_ms >= 0
    assert r.spec.world_name == "W"


def test_format_renders_each_verdict(pricing: PricingTable) -> None:
    cons = format_sequence_verdict(
        verify_sequence(_spec(pricing, [_before("a", "b")], ["a", "b"]))
    )
    assert "CONSISTENT" in cons
    inco = format_sequence_verdict(
        verify_sequence(_spec(
            pricing, [_before("a", "b"), _before("b", "a")], ["a", "b"],
        ))
    )
    assert "INCONSISTENT" in inco
    vac = format_sequence_verdict(verify_sequence(_spec(pricing)))
    assert "VACUOUS" in vac


def test_verdict_is_deterministic(pricing: PricingTable) -> None:
    s = _spec(pricing, [_before("a", "b"), _before("b", "c")], ["a", "b", "c"])
    assert verify_sequence(s).verdict == verify_sequence(s).verdict == "consistent"
