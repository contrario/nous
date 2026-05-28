from __future__ import annotations

# __phase2_stage6_tests_v1__
# Phase 2 Stage 6: `nous verify-sequence` CLI surface.
# Verdict -> exit code mapping is the contract under test.

import argparse
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest

from cli_verify_sequence import (
    build_verify_sequence_parser,
    cmd_verify_sequence,
)

z3 = pytest.importorskip("z3")


_CONSISTENT = dedent('''\
    world Demo {  # __phase2_stage6_grammar_fix_v1__ __phase2_stage6_model_fix_v1__
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law before(a, b)
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')

_INCONSISTENT = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
        events { a, b }
        law before(a, b)
        law before(b, a)
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')

_VACUOUS = dedent('''\
    world Demo {
        cost_cap: 0.10 USD
        max_ticks: 2
    }
    soul S {
        mind: claude-sonnet-4-6 @ Tier1
        tokens: input = 100 output = 50
    }
''')


def _args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        file=str(path), prices=None, timeout_ms=30000,
    )


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_consistent_exits_0(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "c.nous", _CONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONSISTENT" in out


def test_inconsistent_exits_1(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "i.nous", _INCONSISTENT)))
    out = capsys.readouterr().out
    assert rc == 1
    assert "INCONSISTENT" in out


def test_vacuous_exits_0(tmp_path: Path, capsys) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "v.nous", _VACUOUS)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "VACUOUS" in out


def test_missing_file_exits_3(tmp_path: Path) -> None:
    rc = cmd_verify_sequence(_args(tmp_path / "nope.nous"))
    assert rc == 3


def test_parse_error_exits_3(tmp_path: Path) -> None:
    rc = cmd_verify_sequence(_args(_write(tmp_path, "bad.nous", "this is not nous")))
    assert rc == 3


def test_parser_registers_subcommand() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command")
    build_verify_sequence_parser(sub)
    ns = ap.parse_args(["verify-sequence", "x.nous"])
    assert ns.command == "verify-sequence"
    assert ns.file == "x.nous"
    assert ns.timeout_ms == 30000
