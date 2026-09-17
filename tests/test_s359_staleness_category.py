"""
NOUS Session 359 -- staleness is a claim about a vendor price.

Two entry kinds have no vendor price standing behind them, and the
staleness rule was written as if every entry did.

  free      a zero cost is not a market price; there is nothing to
            re-verify, so it cannot go stale and must not refuse.
  per_hour  already refused for its billing model. That refusal must
            reach the caller instead of being masked by a staleness
            message telling the operator to refresh a verified_date
            that was never a vendor verification (verified_by is
            "estimated" on the shipped entry).

Both fixtures carry a deliberately ancient verified_date so the tests
are calendar-independent: they assert the same thing on every run
date, in the house style of tests/test_s189_vr003_unpriceable.py.

RED before the pricing.py ordering fix, green after.

# __s359_staleness_category_v1__
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from cli_prices import cmd_prices_age
from pricing import (
    PricingTable,
    get_price_for_smt,
    staleness_status,
)

_TODAY = date(2026, 9, 17)

FREE_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."local-free"]
    provider = "local"
    pricing_model = "free"
    input_per_1m = "0"
    output_per_1m = "0"
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


def _table(body: str) -> PricingTable:
    import tomllib
    return PricingTable.model_validate(tomllib.loads(body))


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "nous_prices.toml"
    p.write_text(body, encoding="utf-8")
    return p


class TestFreeEntryCannotGoStale:

    def test_staleness_status_is_ok_for_a_free_entry(self) -> None:
        _, entry = _table(FREE_TOML).resolve("local-free")
        status, msg = staleness_status(entry, today=_TODAY, under_smt=True)
        assert status == "ok", f"got {status}: {msg}"

    def test_smt_accepts_a_free_entry_with_an_ancient_date(self) -> None:
        canonical, _ = get_price_for_smt(
            _table(FREE_TOML), "local-free", today=_TODAY,
        )
        assert canonical == "local-free"

    def test_age_report_does_not_error_on_a_free_entry(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = argparse.Namespace(prices=str(_write(tmp_path, FREE_TOML)))
        rc = cmd_prices_age(args)
        cap = capsys.readouterr()
        detail = f"rc={rc}\nstdout:\n{cap.out}\nstderr:\n{cap.err}"
        assert "ERROR" not in cap.out, detail
        assert rc == 0, detail


class TestPerHourRefusalSurvivesAnOldDate:

    def test_refusal_names_the_billing_model_not_the_age(self) -> None:
        with pytest.raises(ValueError, match="per_hour"):
            get_price_for_smt(
                _table(PER_HOUR_TOML), "rented-gpu", today=_TODAY,
            )
