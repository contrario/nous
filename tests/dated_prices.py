"""
Test-only price table dated at run time (docs/ONE_PRICE_SOURCE_DESIGN.md
section 23, D2 and D3). __s371_a1_dated_prices_v1__

The copy is test data, not a verified price. It equals the shipped
pricing/defaults.toml on every line except the verified_date lines, which
carry the run date minus OFFSET_DAYS. It is written under a temporary
HOME as .config/nous/prices.toml, the user-global layer, so that calls in
the test process and `nous` subprocesses both resolve it when they load a
table. A test opts in by calling use_dated_shipped_prices; nothing here is
autouse. A cache whose module does not import here is left alone: the test
cannot load that module either.
"""
from __future__ import annotations

import importlib
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "pricing" / "defaults.toml"
OFFSET_DAYS = 5
_KEY = re.compile(r"^verified_date\s*=", re.M)
_DATED = re.compile(r'^(verified_date\s*=\s*")(\d{4}-\d{2}-\d{2})(")', re.M)
_CACHES: tuple[tuple[str, str, object], ...] = (
    ("nous_api_server", "_DEFAULT_PRICING", None),
    ("nous_api_server", "_DEFAULT_PRICING_LOADED", False),
    ("runtime", "_RUNTIME_PRICING", None),
    ("nous_runtime", "_DISPATCH_PRICING", None),
)


class DatedPricesError(RuntimeError):
    pass


def dated_text(text: str, today: date, offset_days: int = OFFSET_DAYS) -> str:
    keys = len(_KEY.findall(text))
    stamp = (today - timedelta(days=offset_days)).isoformat()
    new, replaced = _DATED.subn(lambda m: m.group(1) + stamp + m.group(3), text)
    if keys == 0 or replaced != keys:
        raise DatedPricesError(
            f"verified_date lines {keys}, dated values replaced {replaced}")
    old_lines = text.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    if len(old_lines) != len(new_lines) or any(
            a != b and not _KEY.match(a) for a, b in zip(old_lines, new_lines)):
        raise DatedPricesError(
            "the copy differs from the source outside the verified_date lines")
    return new


def write_dated_copy(home: Path, today: date) -> Path:
    home = Path(home).resolve()
    if home == ROOT or ROOT in home.parents:
        raise DatedPricesError(f"refusing to write inside the repository: {home}")
    dest = home / ".config" / "nous" / "prices.toml"
    text = dated_text(SHIPPED.read_text(encoding="utf-8"), today)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def use_dated_shipped_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = Path(tmp_path) / "dated_prices_home"
    dest = write_dated_copy(home, datetime.now(timezone.utc).date())
    monkeypatch.setenv("HOME", str(home.resolve()))
    for module_name, attr, value in _CACHES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        monkeypatch.setattr(module, attr, value)
    from pricing import load_pricing
    table = load_pricing()
    if table.source_path is None or Path(table.source_path).resolve() != dest.resolve():
        raise DatedPricesError(
            f"load_pricing resolved {table.source_path}, not the dated copy {dest}")
    return dest
