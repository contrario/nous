"""
NOUS Session 359 -- the three surfaces that report staleness must agree.

pricing.py, `nous prices verify` and `nous prices age` each answer the
question "is this entry usable under --smt". Today they disagree:

  verify  calls staleness_status without under_smt=True, so it says
          "warn" about an entry --smt will hard-refuse. The default is
          the general one; the pricing table exists for --smt.
  age     blames the verified_date for a per_hour entry. Since S359
          patch 2 the --smt path refuses per_hour for its billing model
          before it ever looks at a date, so "refresh verified_date" is
          both the wrong cause and an instruction the operator cannot
          carry out: verified_by on the shipped entry is "estimated"
          and no vendor publishes an hourly claim to verify against.

Fixtures carry an ancient verified_date so these assertions hold on
every run date rather than flipping on 2026-09-28.

RED before the cli_prices.py fix, green after.

# __s359_verify_age_agreement_v1__
"""
from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import pytest

from cli_prices import cmd_prices_age, cmd_prices_verify

STALE_PER_TOKEN_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."paid-and-ancient"]
    provider = "somebody"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2020-01-01"
""")

PER_HOUR_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."rented-gpu"]
    provider = "self-hosted"
    pricing_model = "per_hour"
    hourly_cost = "2.50"
    verified_date = "2020-01-01"
""")


def _write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "nous_prices.toml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def _freshness_line(out: str) -> str:
    for line in out.splitlines():
        if line.strip().startswith("freshness:"):
            return line
    raise AssertionError("no freshness line in:\n" + out)


class TestVerifyAgreesWithTheSmtPath:

    def test_verify_calls_an_smt_blocking_entry_an_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(
            prices=_write(tmp_path, STALE_PER_TOKEN_TOML),
            model="paid-and-ancient",
        )
        rc = cmd_prices_verify(args)
        cap = capsys.readouterr()
        detail = f"rc={rc}\nstdout:\n{cap.out}\nstderr:\n{cap.err}"
        assert "error" in _freshness_line(cap.out), detail


class TestAgeDoesNotBlameTheDateForPerHour:

    def test_per_hour_row_is_not_reported_as_a_staleness_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(prices=_write(tmp_path, PER_HOUR_TOML))
        rc = cmd_prices_age(args)
        cap = capsys.readouterr()
        detail = f"rc={rc}\nstdout:\n{cap.out}\nstderr:\n{cap.err}"
        assert "ERROR" not in cap.out, detail

    def test_age_does_not_fail_on_a_per_hour_only_table(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(prices=_write(tmp_path, PER_HOUR_TOML))
        rc = cmd_prices_age(args)
        cap = capsys.readouterr()
        assert rc == 0, f"stdout:\n{cap.out}\nstderr:\n{cap.err}"
