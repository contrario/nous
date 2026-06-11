"""S127 U4 tests: --chain-coverage full admission rule.

The verify pipeline refuses --chain-coverage full without --supersedes
(full mode carries per-link sources and net-containment proofs across
hops; there is no chain without a predecessor). The rule is exercised
in isolation via cmd_verify_impl_guard_for_test.

__s127_chain_coverage_flag_tests_v1__
"""
from __future__ import annotations

from cli_verify import cmd_verify_impl_guard_for_test


def test_full_without_supersedes_refused() -> None:
    rc = cmd_verify_impl_guard_for_test(
        chain_coverage="full", supersedes=None
    )
    assert rc == 1


def test_full_with_supersedes_passes_guard() -> None:
    rc = cmd_verify_impl_guard_for_test(
        chain_coverage="full", supersedes="p.json"
    )
    assert rc == 0


def test_none_mode_passes_regardless_of_supersedes() -> None:
    assert cmd_verify_impl_guard_for_test(
        chain_coverage=None, supersedes=None
    ) == 0
    assert cmd_verify_impl_guard_for_test(
        chain_coverage=None, supersedes="p.json"
    ) == 0
