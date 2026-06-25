from __future__ import annotations

# __s104_cli_command_count_tests_v1__
# Locks the health cli_commands literal to the derived root subcommand
# count, so the two can never silently diverge again.

import re
from pathlib import Path

from cli import build_parser, cli_command_count

_EXPECTED = 59  # __s177_p1_cli_count_59_v1__  # __s170_leg6b_verify_cost_v1__  # __s167_p2b_cli_count_57_v1__  # __s157_u3b_cli_count_56_v1__  # __s147_cli_count_55_v1__
_API = Path(__file__).resolve().parent.parent / "nous_api_server.py"


def test_cli_command_count_matches_parser() -> None:
    assert cli_command_count() == _EXPECTED


def test_build_parser_has_expected_root_commands() -> None:
    import argparse
    ap = build_parser()
    actions = [a for a in ap._actions if isinstance(a, argparse._SubParsersAction)]
    assert actions, "no subparsers action on root parser"
    assert len(actions[0].choices) == _EXPECTED


def test_health_literal_locked_to_derived_count() -> None:
    src = _API.read_text(encoding="utf-8")
    m = re.search(r'"cli_commands":\s*(\d+),', src)
    assert m, "cli_commands literal not found"
    assert int(m.group(1)) == cli_command_count()
