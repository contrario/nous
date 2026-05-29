from __future__ import annotations

# __phase2_stage7b_leads_to_tests_v1__
# Phase 2 Stage 7b: the leads_to(A, B) ordering law.
# leads_to(A, B) = Dwyer Response (TLA+ ~>): every A is eventually
# followed by some later B. The liveness twin of before; same static
# rank (rank_A < rank_B), dual runtime predicate.

import argparse
from pathlib import Path
from textwrap import dedent

import pytest

from parser import parse_nous

z3 = pytest.importorskip("z3")

from cli_verify_sequence import (
    build_verify_sequence_parser,
    cmd_verify_sequence,
)


_LEADS_TO_CONSISTENT = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law leads_to(a, b)
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')

_CROSS_OPERATOR_INCONSISTENT = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law leads_to(a, b)
        law never_after(a, b)
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')

_UNPRICED_LEADS_TO = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law leads_to(a, b)
    }
    soul S {
        mind: gpt-4o @ Tier1
        tokens: input = 100 output = 50
    }
''')


def _args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(file=str(path), prices=None, timeout_ms=30000)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_leads_to_parses_into_sequence_law() -> None:
    prog = parse_nous(_LEADS_TO_CONSISTENT)
    laws = prog.world.sequence_laws
    assert len(laws) == 1
    assert laws[0].kind == "leads_to"
    assert laws[0].before_label == "a"
    assert laws[0].after_label == "b"


def test_leads_to_alone_is_consistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "lt.nous", _LEADS_TO_CONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONSISTENT" in out


def test_leads_to_and_never_after_same_pair_is_inconsistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "x.nous", _CROSS_OPERATOR_INCONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 1
    assert "INCONSISTENT" in out


def test_leads_to_unpriced_model_is_consistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "u.nous", _UNPRICED_LEADS_TO)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONSISTENT" in out
