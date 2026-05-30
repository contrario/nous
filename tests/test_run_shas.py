"""Tests for run_shas.compute_run_shas (N.1).

The byte-identity test is the load-bearing one: compute_run_shas must
return exactly the three SHA-256 digests the dossier / verify path
derives for the same source and cost model, so a runtime trace's subject
binding matches its compliance dossier's. It runs against the real
parser / pricing / smt_emit modules.

# __nous_run_shas_tests_v1__
"""
from __future__ import annotations

import pytest

from run_shas import RunShasError, compute_run_shas

_SOURCE = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "}\n"
    "soul S {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "}\n"
)


def _emit_path_shas(source_text: str) -> tuple[str, str, str]:
    from parser import parse_nous
    from pricing import load_pricing
    from smt_emit import emit_smt

    program = parse_nous(source_text)
    pricing = load_pricing(None)
    spec = emit_smt(program, pricing, source_text=source_text)
    return spec.source_sha256, spec.sha256(), spec.pricing_sha256


def test_matches_dossier_emit_path() -> None:
    assert compute_run_shas(_SOURCE) == _emit_path_shas(_SOURCE)


def test_deterministic() -> None:
    assert compute_run_shas(_SOURCE) == compute_run_shas(_SOURCE)


def test_all_three_are_64_hex() -> None:
    for value in compute_run_shas(_SOURCE):
        assert len(value) == 64
        assert all(c in "0123456789abcdef" for c in value)


def test_refuse_empty_source() -> None:
    with pytest.raises(RunShasError) as ei:
        compute_run_shas("")
    assert "non-empty" in str(ei.value)


def test_refuse_non_string_source() -> None:
    with pytest.raises(RunShasError):
        compute_run_shas(None)  # type: ignore[arg-type]


def test_parse_failure_wrapped() -> None:
    with pytest.raises(RunShasError) as ei:
        compute_run_shas("this is not valid nous source {{{")
    assert "parse failed" in str(ei.value)
