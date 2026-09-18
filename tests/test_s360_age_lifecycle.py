"""
NOUS Session 360 -- `nous prices age` must agree with --smt on removed
entries.

get_price_for_smt checks lifecycle first: an entry past removed_after is
refused as removed and the message names its renamed_to successor. The
age report never consulted lifecycle, so it graded a removed entry on
its verified_date and told the operator to refresh a date for a model
the provider no longer serves. From 2026-09-28 that would have been an
ERROR row and exit 1 for the shipped deepseek-chat entry.

Fixtures carry ancient dates so the assertions hold on every run date.

RED before the cli_prices.py fix, green after.

# __s360_age_lifecycle_v1__
"""
from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import pytest

from cli_prices import cmd_prices_age

SHIPPED: Path = Path(__file__).resolve().parent.parent / "pricing" / "defaults.toml"

REMOVED_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."gone-model"]
    provider = "somebody"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2020-01-01"
    removed_after = "2020-06-30"
    renamed_to = "successor-model"

    [models."successor-model"]
    provider = "local"
    pricing_model = "free"
""")

DEPRECATED_ONLY_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."old-but-served"]
    provider = "somebody"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2020-01-01"
    deprecated_after = "2020-06-30"
""")


def _write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "nous_prices.toml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def _row(out: str, model: str) -> str:
    for line in out.splitlines():
        if line.startswith(model + " "):
            return line
    raise AssertionError(f"no row for {model!r} in:\n{out}")


def _run(prices: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    rc = cmd_prices_age(argparse.Namespace(prices=prices))
    cap = capsys.readouterr()
    return rc, cap.out, f"rc={rc}\nstdout:\n{cap.out}\nstderr:\n{cap.err}"


class TestAgeReportsRemovedEntriesAsRemoved:

    def test_removed_row_is_not_graded_on_its_date(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _, out, detail = _run(_write(tmp_path, REMOVED_TOML), capsys)
        row = _row(out, "gone-model")
        assert "ERROR" not in row, detail
        assert "refresh" not in row, detail

    def test_removed_row_names_its_successor(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _, out, detail = _run(_write(tmp_path, REMOVED_TOML), capsys)
        row = _row(out, "gone-model")
        assert "removed on 2020-06-30" in row, detail
        assert "'successor-model'" in row, detail

    def test_a_removed_entry_does_not_fail_the_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, _, detail = _run(_write(tmp_path, REMOVED_TOML), capsys)
        assert rc == 0, detail

    def test_shipped_deepseek_chat_row_names_deepseek_flash(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _, out, detail = _run(str(SHIPPED), capsys)
        row = _row(out, "deepseek-chat")
        assert "removed on 2026-07-24" in row, detail
        assert "'deepseek-flash'" in row, detail


class TestDeprecatedIsStillGradedOnItsDate:

    def test_deprecated_but_served_entry_keeps_its_staleness_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, detail = _run(_write(tmp_path, DEPRECATED_ONLY_TOML), capsys)
        assert "ERROR" in _row(out, "old-but-served"), detail
        assert rc == 1, detail
