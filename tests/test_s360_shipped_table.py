from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pricing import PricingTable, get_price_for_smt, load_pricing

SHIPPED: Path = Path(__file__).resolve().parent.parent / "pricing" / "defaults.toml"
AFTER_REMOVAL: date = date(2026, 9, 18)
CLIFF: date = date(2026, 9, 28)


def _table() -> PricingTable:
    return load_pricing(SHIPPED)


def test_every_renamed_to_resolves_in_shipped_table() -> None:
    table = _table()
    for name, entry in table.models.items():
        if entry.renamed_to is None:
            continue
        assert entry.renamed_to != name, f"{name!r} renames to itself"
        assert entry.renamed_to in table.models, (
            f"{name!r} renamed_to {entry.renamed_to!r}, "
            f"which the shipped table cannot price"
        )
        table.resolve(entry.renamed_to)


def test_deepseek_chat_refuses_as_removed_naming_a_usable_successor() -> None:
    table = _table()
    with pytest.raises(ValueError, match=r"removed on 2026-07-24; use 'deepseek-flash' instead"):
        get_price_for_smt(table, "deepseek-chat", today=AFTER_REMOVAL)
    canonical, _ = get_price_for_smt(table, "deepseek-flash", today=AFTER_REMOVAL)
    assert canonical == "deepseek-flash"


@pytest.mark.parametrize("model", ["gpt-5-2", "gpt-5-mini", "gemini-3-1-pro"])
def test_reverified_entries_clear_the_2026_09_28_cliff(model: str) -> None:
    canonical, _ = get_price_for_smt(_table(), model, today=CLIFF)
    assert canonical == model


def test_gpt_4o_mini_carries_a_verified_date() -> None:
    entry = _table().models["gpt-4o-mini"]
    assert entry.verified_date is not None
    assert entry.source_url is not None


@pytest.mark.parametrize(
    ("model", "cached"),
    [("gpt-5-2", "0.175"), ("gpt-5-mini", "0.025"), ("gemini-3-1-pro", "0.20")],
)
def test_cache_fields_record_only_published_rates(model: str, cached: str) -> None:
    entry = _table().models[model]
    assert entry.input_cached_per_1m == Decimal(cached)
    assert entry.input_cache_write_per_1m is None
