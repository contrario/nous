from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from pricing import (
    STALENESS_ERROR_DAYS_UNDER_SMT,
    PricingTable,
    get_price_for_smt,
    load_pricing,
)

SHIPPED: Path = Path(__file__).resolve().parent.parent / "pricing" / "defaults.toml"
LEGACY: str = "deepseek-v4-flash"
TARGET: str = "deepseek-flash"
OLD_CLIFF: date = date(2026, 10, 6)
PRICING_PAGE: str = "https://api-docs.deepseek.com/quick_start/pricing"
PIN_PRICING: str = "31902010ee5d690de6b0c79c9e05c507fedf11007a23a965551b5ecebdc4adc8"
PIN_DOCS: str = "5cbf7f811500872c40b2c32ea1ef023056d52f28a9a3cbf668d4a37da7c83587"
OWN_FIELDS: tuple[str, ...] = (
    "input_per_1m",
    "output_per_1m",
    "input_cached_per_1m",
    "input_cache_write_per_1m",
    "hourly_cost",
    "verified_date",
    "removed_after",
    "deprecated_after",
    "renamed_to",
)


def _table() -> PricingTable:
    return load_pricing(SHIPPED)


def test_legacy_flash_name_aliases_deepseek_flash() -> None:
    assert _table().models[LEGACY].alias_of == TARGET


def test_legacy_flash_alias_carries_no_price_date_or_lifecycle() -> None:
    entry = _table().models[LEGACY]
    for field in OWN_FIELDS:
        assert getattr(entry, field) is None, f"{LEGACY!r} carries {field!r}"


def test_smt_prices_legacy_name_as_deepseek_flash_past_the_old_cliff() -> None:
    table = _table()
    canonical, entry = get_price_for_smt(table, LEGACY, today=OLD_CLIFF)
    assert canonical == TARGET
    assert entry == table.models[TARGET]


def test_legacy_name_refuses_on_the_target_clock() -> None:
    table = _table()
    verified = table.models[TARGET].verified_date
    assert verified is not None
    past = verified + timedelta(days=STALENESS_ERROR_DAYS_UNDER_SMT + 1)
    with pytest.raises(
        ValueError, match=r"model 'deepseek-flash' pricing too old for --smt"
    ):
        get_price_for_smt(table, LEGACY, today=past)


def test_alias_evidence_travels_in_the_canonical_digest() -> None:
    row = json.loads(_table().canonical_bytes())["models"][LEGACY]
    assert row["alias_of"] == TARGET
    assert row["source_url"] == PRICING_PAGE
    assert PIN_PRICING in row["notes"]
    assert PIN_DOCS in row["notes"]
