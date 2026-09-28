"""
The eight entries re-read on 2026-09-28 (docs/ONE_PRICE_SOURCE_DESIGN.md
section 25, D388-5). __s388_d8_reread_test_v1__

The subject is the age of the shipped prices, so the shipped table is read
directly and every date is fixed: the verdict does not depend on the day
the suite runs.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pricing import PricingTable, get_price_for_smt, load_pricing

SHIPPED: Path = Path(__file__).resolve().parent.parent / "pricing" / "defaults.toml"
LAST_FRESH_DAY: date = date(2026, 12, 27)
FIRST_REFUSAL_DAY: date = date(2026, 12, 28)
READ_DAY: str = "2026-09-28"
REREAD: dict[str, str] = {
    "claude-opus-4-7": "d493a95c63a4cb3ec7d86073e53b40fca8658efcf562872daf751ac871e470a2",
    "claude-sonnet-4-6": "d493a95c63a4cb3ec7d86073e53b40fca8658efcf562872daf751ac871e470a2",
    "claude-haiku-4-5": "d493a95c63a4cb3ec7d86073e53b40fca8658efcf562872daf751ac871e470a2",
    "deepseek-flash": "210f102275ccf1a6542f08a3bc9e4b4c7c83278cb74b35217bffa112df6363b2",
    "gpt-5-2": "0de899a93b1d9a8c7cf7b3a01ed3553337636c7ff374153821f218a203a203c8",
    "gpt-5-mini": "0de899a93b1d9a8c7cf7b3a01ed3553337636c7ff374153821f218a203a203c8",
    "gpt-4o-mini": "0de899a93b1d9a8c7cf7b3a01ed3553337636c7ff374153821f218a203a203c8",
    "gemini-3-1-pro": "97df41eff4012519abb73d7907eb9fbeaa914e13dce2d9c6eef5da3d134db87f",
}


def _table() -> PricingTable:
    return load_pricing(SHIPPED)


@pytest.mark.parametrize("model", sorted(REREAD))
def test_reread_entry_prices_on_its_last_fresh_day(model: str) -> None:
    canonical, _ = get_price_for_smt(_table(), model, today=LAST_FRESH_DAY)
    assert canonical == model


@pytest.mark.parametrize("model", sorted(REREAD))
def test_reread_entry_refuses_the_day_after(model: str) -> None:
    with pytest.raises(ValueError, match=r"pricing too old for --smt: verified 91 days ago;"):
        get_price_for_smt(_table(), model, today=FIRST_REFUSAL_DAY)


@pytest.mark.parametrize("model", sorted(REREAD))
def test_reread_entry_notes_name_the_stored_page(model: str) -> None:
    notes = _table().models[model].notes or ""
    names_sha = REREAD[model] in notes
    names_day = f"fetched on Server A {READ_DAY}" in notes
    assert names_sha, f"{model} notes do not name sha256 {REREAD[model]}"
    assert names_day, f"{model} notes do not name the read of {READ_DAY}"
