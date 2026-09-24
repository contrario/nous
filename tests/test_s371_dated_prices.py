"""
NOUS Session 371 -- the dated copy of the shipped price table that tests
use instead of the calendar (docs/ONE_PRICE_SOURCE_DESIGN.md section 23,
D2 and D3).

The copy is test data. It must equal pricing/defaults.toml on every line
except the verified_date lines, stay out of the repository, leave the
shipped file untouched, and be what load_pricing resolves, in process and
in a subprocess, while a test uses it.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import dated_prices
from pricing import PricingTable, lifecycle_status, load_pricing, staleness_status

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "pricing" / "defaults.toml"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dated_table(tmp_path: Path, today: date) -> PricingTable:
    path = dated_prices.write_dated_copy(tmp_path / "home", today)
    return load_pricing(path)


def test_copy_differs_only_on_verified_date_lines() -> None:
    text = SHIPPED.read_text(encoding="utf-8")
    today = date(2031, 1, 1)
    stamp = (today - timedelta(days=dated_prices.OFFSET_DAYS)).isoformat()
    new = dated_prices.dated_text(text, today)
    old_lines = text.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    assert len(old_lines) == len(new_lines)
    keys = [i for i, line in enumerate(old_lines) if line.startswith("verified_date")]
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    assert keys and changed == keys
    assert all(f'"{stamp}"' in new_lines[i] for i in keys)


@pytest.mark.parametrize("days_ahead", [0, 400])
def test_every_entry_keeps_its_price_and_lifecycle_and_is_fresh(tmp_path: Path, days_ahead: int) -> None:
    today = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    shipped = load_pricing(SHIPPED)
    copy = _dated_table(tmp_path, today)
    assert set(copy.models) == set(shipped.models)
    for name, entry in shipped.models.items():
        dated = copy.models[name]
        assert dated.model_dump(exclude={"verified_date"}) == entry.model_dump(exclude={"verified_date"}), name
        assert lifecycle_status(dated, today=today) == lifecycle_status(entry, today=today), name
        assert staleness_status(dated, today=today, under_smt=True)[0] != "error", name


def test_refuses_a_verified_date_it_cannot_date() -> None:
    text = SHIPPED.read_text(encoding="utf-8") + '\n[models."s371-bad"]\nverified_date = "2026-9-8"\n'
    with pytest.raises(dated_prices.DatedPricesError):
        dated_prices.dated_text(text, date(2031, 1, 1))


def test_refuses_to_write_inside_the_repository() -> None:
    target = ROOT / "s371_dated_home_must_not_exist"
    with pytest.raises(dated_prices.DatedPricesError):
        dated_prices.write_dated_copy(target, date(2031, 1, 1))
    assert not target.exists()


def test_use_resolves_the_copy_and_leaves_the_shipped_file_unchanged(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _sha(SHIPPED)
    dest = dated_prices.use_dated_shipped_prices(tmp_path, monkeypatch)
    table = load_pricing()
    assert table.source_path is not None and Path(table.source_path).resolve() == dest.resolve()
    assert table.layer_index == 3
    assert ROOT not in dest.resolve().parents
    assert _sha(SHIPPED) == before


def test_use_resets_the_runtime_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import runtime
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", object())
    dated_prices.use_dated_shipped_prices(tmp_path, monkeypatch)
    assert runtime._RUNTIME_PRICING is None


def test_use_reaches_a_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = dated_prices.use_dated_shipped_prices(tmp_path, monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    out = subprocess.run(
        [sys.executable, "-c",
         "from pricing import load_pricing; t = load_pricing(); print(t.source_path); print(t.layer_index)"],
        cwd=str(work), env=env, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert Path(out[0]).resolve() == dest.resolve()
    assert out[1] == "3"
