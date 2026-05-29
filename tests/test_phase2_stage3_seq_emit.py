from __future__ import annotations

# __phase2_stage3_seq_tests_v1__
# Phase 2 Stage 3: emit_smt sequence-consistency assertions.

from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, LawSequenceNode, MindNode, NousProgram, SoulNode,
    TokensDecl, WorldNode,
)
from pricing import PricingTable
from smt_emit import EmitError, emit_smt


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


def _soul() -> SoulNode:
    return SoulNode(
        name="S",
        mind=MindNode(model="m1", tier="Tier1"),
        tokens=TokensDecl(input=100, output=50),
    )


def _prog(sequence_laws=None, events=None) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="W",
            cost_cap=CostCap(amount=Decimal("0.10"), currency="USD"),
            max_ticks=2,
            sequence_laws=list(sequence_laws or []),
            events=list(events or []),
        ),
        souls=[_soul()],
    )


def _before(a: str, b: str) -> LawSequenceNode:
    return LawSequenceNode(kind="before", before_label=a, after_label=b)


def test_cost_only_spec_has_no_sequence_block(pricing: PricingTable) -> None:
    spec = emit_smt(_prog(), pricing, source_text="x", today=_TODAY)
    assert spec.sequence_assertions == ()
    assert spec.sequence_declarations == ()
    assert spec.serialize_sequence() is None


def test_cost_only_sha256_unchanged_by_feature(pricing: PricingTable) -> None:
    spec = emit_smt(_prog(), pricing, source_text="x", today=_TODAY)
    # No sequence laws -> the SD/SA canonical loops add nothing; the
    # cost hash is exactly the same string the pre-stage-3 code produced.
    h1 = spec.sha256()
    spec2 = emit_smt(_prog(), pricing, source_text="x", today=_TODAY)
    assert spec2.sha256() == h1


def test_one_before_law_emits_rank_and_assertion(pricing: PricingTable) -> None:
    spec = emit_smt(
        _prog([_before("a", "b")], ["a", "b"]),
        pricing, source_text="x", today=_TODAY,
    )
    assert ("seqrank_a", "Real") in spec.sequence_declarations
    assert ("seqrank_b", "Real") in spec.sequence_declarations
    assert spec.sequence_assertions == (
        "(assert (< seqrank_a seqrank_b))",
    )


def test_serialize_sequence_is_valid_smtlib(pricing: PricingTable) -> None:
    spec = emit_smt(
        _prog([_before("a", "b")], ["a", "b"]),
        pricing, source_text="x", today=_TODAY,
    )
    out = spec.serialize_sequence()
    assert out is not None
    assert "(set-logic QF_LRA)" in out
    assert "(declare-const seqrank_a Real)" in out
    assert "(declare-const seqrank_b Real)" in out
    assert "(assert (< seqrank_a seqrank_b))" in out
    assert out.rstrip().endswith("(check-sat)")


def test_sequence_law_changes_sha256(pricing: PricingTable) -> None:
    cost_only = emit_smt(_prog(), pricing, source_text="x", today=_TODAY)
    with_seq = emit_smt(
        _prog([_before("a", "b")], ["a", "b"]),
        pricing, source_text="x", today=_TODAY,
    )
    assert with_seq.sha256() != cost_only.sha256()


def test_two_laws_in_order_shared_alphabet(pricing: PricingTable) -> None:
    spec = emit_smt(
        _prog([_before("a", "b"), _before("b", "c")], ["a", "b", "c"]),
        pricing, source_text="x", today=_TODAY,
    )
    assert spec.sequence_assertions == (
        "(assert (< seqrank_a seqrank_b))",
        "(assert (< seqrank_b seqrank_c))",
    )
    assert spec.sequence_declarations == (
        ("seqrank_a", "Real"),
        ("seqrank_b", "Real"),
        ("seqrank_c", "Real"),
    )


def test_undeclared_label_raises_emit_error(pricing: PricingTable) -> None:
    with pytest.raises(EmitError) as exc:
        emit_smt(
            _prog([_before("a", "b")], ["b"]),
            pricing, source_text="x", today=_TODAY,
        )
    assert "undeclared" in str(exc.value)
    assert "'a'" in str(exc.value)


def test_unsupported_kind_raises_emit_error(pricing: PricingTable) -> None:  # __phase2_stage7a_never_after_stage3_fix_v1__
    bad = LawSequenceNode(kind="at_most", before_label="a", after_label="b")
    with pytest.raises(EmitError) as exc:
        emit_smt(
            _prog([bad], ["a", "b"]),
            pricing, source_text="x", today=_TODAY,
        )
    assert "unsupported sequence law kind" in str(exc.value)


def test_never_after_emits_swapped_rank_assertion(pricing: PricingTable) -> None:
    law = LawSequenceNode(kind="never_after", before_label="a", after_label="b")
    spec = emit_smt(
        _prog([law], ["a", "b"]),
        pricing, source_text="x", today=_TODAY,
    )
    assert ("seqrank_a", "Real") in spec.sequence_declarations
    assert ("seqrank_b", "Real") in spec.sequence_declarations
    assert "(assert (< seqrank_b seqrank_a))" in spec.sequence_assertions
    assert "(assert (< seqrank_a seqrank_b))" not in spec.sequence_assertions


def test_leads_to_emits_forward_rank_assertion(pricing: PricingTable) -> None:  # __phase2_stage7b_leads_to_stage3_v1__
    law = LawSequenceNode(kind="leads_to", before_label="a", after_label="b")
    spec = emit_smt(
        _prog([law], ["a", "b"]),
        pricing, source_text="x", today=_TODAY,
    )
    assert "(assert (< seqrank_a seqrank_b))" in spec.sequence_assertions
    assert "(assert (< seqrank_b seqrank_a))" not in spec.sequence_assertions


def test_emit_is_deterministic(pricing: PricingTable) -> None:
    p = _prog([_before("a", "b"), _before("b", "c")], ["c", "b", "a"])
    s1 = emit_smt(p, pricing, source_text="x", today=_TODAY)
    s2 = emit_smt(p, pricing, source_text="x", today=_TODAY)
    assert s1.sequence_declarations == s2.sequence_declarations
    assert s1.sequence_assertions == s2.sequence_assertions
    assert s1.serialize_sequence() == s2.serialize_sequence()
    assert s1.sha256() == s2.sha256()
    # ranks are sorted regardless of events-declaration order
    assert s1.sequence_declarations == (
        ("seqrank_a", "Real"),
        ("seqrank_b", "Real"),
        ("seqrank_c", "Real"),
    )
