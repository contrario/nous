"""
Tests for --smt-margin PCT flag (v4.13.3).

Verifies:
  1. Default (margin=0) is byte-identical to v4.13.2 SMT spec.
  2. Invalid margin values raise EmitError.
  3. Margin > 0 changes obligation literal and sha256.
  4. Manifest safety_margin_pct is None when margin=0,
     populated when margin > 0.
  5. SMT-LIB serialize includes margin comment when margin > 0.

# __session64_smt_margin_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from manifest import manifest_from_verify
from parser import parse_nous
from pricing import load_pricing
from smt_emit import EmitError, emit_smt
from smt_verify import VerifyResult


def _load_program():
    template = (
        Path(__file__).parent.parent
        / "templates"
        / "cost_cap_with_souls.nous"
    )
    return parse_nous(template.read_text(encoding="utf-8"))


@pytest.fixture
def program():
    return _load_program()


@pytest.fixture
def pricing():
    return load_pricing()


def test_default_margin_zero(program, pricing) -> None:
    spec = emit_smt(program, pricing, source_text="x")
    assert spec.cost_cap_margin_pct == 0


def test_explicit_margin_zero_byte_identical(program, pricing) -> None:
    spec_default = emit_smt(program, pricing, source_text="x")
    spec_zero = emit_smt(
        program, pricing, source_text="x", margin_pct=0
    )
    assert spec_default.sha256() == spec_zero.sha256()
    assert spec_default.serialize() == spec_zero.serialize()
    assert spec_default.obligation == spec_zero.obligation


def test_margin_invalid_negative(program, pricing) -> None:
    with pytest.raises(EmitError, match="out of range"):
        emit_smt(program, pricing, source_text="x", margin_pct=-1)


def test_margin_invalid_too_large(program, pricing) -> None:
    with pytest.raises(EmitError, match="out of range"):
        emit_smt(program, pricing, source_text="x", margin_pct=100)


def test_margin_changes_obligation(program, pricing) -> None:
    spec_zero = emit_smt(
        program, pricing, source_text="x", margin_pct=0
    )
    spec_with = emit_smt(
        program, pricing, source_text="x", margin_pct=20
    )
    assert spec_zero.obligation != spec_with.obligation


def test_margin_changes_sha256(program, pricing) -> None:
    a = emit_smt(program, pricing, source_text="x", margin_pct=10)
    b = emit_smt(program, pricing, source_text="x", margin_pct=20)
    c = emit_smt(program, pricing, source_text="x", margin_pct=0)
    assert a.sha256() != b.sha256()
    assert a.sha256() != c.sha256()
    assert b.sha256() != c.sha256()


def test_margin_in_manifest(program, pricing) -> None:
    spec_zero = emit_smt(
        program, pricing, source_text="x", margin_pct=0
    )
    spec_with = emit_smt(
        program, pricing, source_text="x", margin_pct=20
    )
    common = dict(
        verdict="proven",
        solver_name="z3",
        solver_version="z3 4.16.0",
        elapsed_ms=10,
        timestamp_utc="2026-04-29T00:00:00+00:00",
    )
    r_zero = VerifyResult(spec=spec_zero, **common)
    r_with = VerifyResult(spec=spec_with, **common)

    m_zero = manifest_from_verify(r_zero, nous_version="4.13.3")
    m_with = manifest_from_verify(r_with, nous_version="4.13.3")

    assert m_zero.safety_margin_pct is None
    assert m_with.safety_margin_pct == 20
    assert "safety_margin_pct" not in m_zero.canonical_dict()
    assert m_with.canonical_dict()["safety_margin_pct"] == 20


def test_margin_serialize_includes_comment(program, pricing) -> None:
    spec_zero = emit_smt(
        program, pricing, source_text="x", margin_pct=0
    )
    spec_with = emit_smt(
        program, pricing, source_text="x", margin_pct=20
    )
    assert "cost_cap_margin_pct" not in spec_zero.serialize()
    assert "cost_cap_margin_pct: 20" in spec_with.serialize()
    assert "effective_cap:" in spec_with.serialize()
