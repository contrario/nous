"""
The eight entries re-read on 2026-10-26 (docs/ONE_PRICE_SOURCE_DESIGN.md
section 26, D405-6). __s405_d8_reread_test_v1__

The subject is the age and the lifecycle of the shipped prices, so the
shipped table is read directly and every date is fixed: the verdict does
not depend on the day the suite runs.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from pricing import PricingTable, get_price_for_smt, load_pricing

SHIPPED: Path = Path(__file__).resolve().parent.parent / "pricing" / "defaults.toml"
LAST_FRESH_DAY: date = date(2027, 1, 24)
FIRST_REFUSAL_DAY: date = date(2027, 1, 25)
READ_DAY: str = "2026-10-26"
REMOVED_AFTER: dict[str, date] = {"gpt-5-mini": date(2026, 12, 11)}
DEEPSEEK_SOURCE: str = "https://api-docs.deepseek.com/quick_start/pricing/"
REREAD: dict[str, str] = {
    "claude-opus-4-7": "f600adb0254ce08f0dfd821b381b61d20bc8ef325007b039ab24016991ae6faf",
    "claude-sonnet-4-6": "f600adb0254ce08f0dfd821b381b61d20bc8ef325007b039ab24016991ae6faf",
    "claude-haiku-4-5": "f600adb0254ce08f0dfd821b381b61d20bc8ef325007b039ab24016991ae6faf",
    "deepseek-flash": "b856a6e93fa4793ecc8f3fd03a01bb7d8f7572f78a4739da8ce6dbdb09328d66",
    "gpt-5-2": "606acc6693f882253e203e30da2fbfd23f28b02540a98f26fce93c5cdc04e9dd",
    "gpt-5-mini": "606acc6693f882253e203e30da2fbfd23f28b02540a98f26fce93c5cdc04e9dd",
    "gpt-4o-mini": "606acc6693f882253e203e30da2fbfd23f28b02540a98f26fce93c5cdc04e9dd",
    "gemini-3-1-pro": "51f4314aa6d4c39c14bd4ebab3c54c283158784fe46db07ba0195e4e78c329f5",
}
DATED: list[str] = sorted(m for m in REREAD if m not in REMOVED_AFTER)


def _table() -> PricingTable:
    return load_pricing(SHIPPED)


@pytest.mark.parametrize("model", DATED)
def test_reread_entry_prices_on_its_last_fresh_day(model: str) -> None:
    canonical, _ = get_price_for_smt(_table(), model, today=LAST_FRESH_DAY)
    assert canonical == model


@pytest.mark.parametrize("model", DATED)
def test_reread_entry_refuses_the_day_after(model: str) -> None:
    with pytest.raises(ValueError, match=r"pricing too old for --smt: verified 91 days ago;"):
        get_price_for_smt(_table(), model, today=FIRST_REFUSAL_DAY)


def test_gpt_5_mini_refuses_the_day_after_its_removal() -> None:
    day = REMOVED_AFTER["gpt-5-mini"] + timedelta(days=1)
    with pytest.raises(ValueError, match=re.escape("model 'gpt-5-mini' cannot be used: removed on 2026-12-11")):
        get_price_for_smt(_table(), "gpt-5-mini", today=day)


def test_gpt_5_mini_prices_on_its_removal_day_invariant() -> None:
    canonical, _ = get_price_for_smt(_table(), "gpt-5-mini", today=REMOVED_AFTER["gpt-5-mini"])
    assert canonical == "gpt-5-mini"


def test_deepseek_flash_source_url_has_its_trailing_slash() -> None:
    assert _table().models["deepseek-flash"].source_url == DEEPSEEK_SOURCE


@pytest.mark.parametrize("model", sorted(REREAD))
def test_reread_entry_notes_name_the_stored_page(model: str) -> None:
    notes = _table().models[model].notes or ""
    names_sha = REREAD[model] in notes
    names_day = f"fetched on Server A {READ_DAY}" in notes
    assert names_sha, f"{model} notes do not name sha256 {REREAD[model]}"
    assert names_day, f"{model} notes do not name the read of {READ_DAY}"
