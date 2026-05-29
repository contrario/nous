from __future__ import annotations

# __phase2_stage7a_never_after_tests_v1__
# Phase 2 Stage 7a: the never_after(A, B) ordering law.
# never_after(A, B) = Dwyer Absence-of-B in the After-A scope: once A
# occurs, B is forbidden thereafter. Its static rank is the
# operand-swap of before; its runtime predicate is before's dual.

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


_NEVER_AFTER_CONSISTENT = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law never_after(a, b)
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
        law before(a, b)
        law never_after(a, b)
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')

_UNPRICED_NEVER_AFTER = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law never_after(a, b)
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


def test_never_after_parses_into_sequence_law() -> None:
    prog = parse_nous(_NEVER_AFTER_CONSISTENT)
    laws = prog.world.sequence_laws
    assert len(laws) == 1
    assert laws[0].kind == "never_after"
    assert laws[0].before_label == "a"
    assert laws[0].after_label == "b"


def test_never_after_alone_is_consistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "na.nous", _NEVER_AFTER_CONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONSISTENT" in out


def test_before_and_never_after_same_pair_is_inconsistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "x.nous", _CROSS_OPERATOR_INCONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 1
    assert "INCONSISTENT" in out


def test_never_after_unpriced_model_is_consistent(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "u.nous", _UNPRICED_NEVER_AFTER)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONSISTENT" in out
