from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
DOCS_PAGE: Path = ROOT / "website" / "docs" / "index.html"
OVERCLAIMS: tuple[str, ...] = (
    "circuit breaker trips automatically",
    "Trips circuit breaker if cost exceeds ceiling",
    "Budget remaining before circuit breaker trips",
)
DISCLOSURE: str = "does not meter observed spend"
CHARGE_CALL: re.Pattern[str] = re.compile(r"\.charge\(")


def _shipped_modules() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["tool"]["setuptools"]["py-modules"])


def test_docs_page_states_the_runtime_does_not_meter_spend() -> None:
    text = DOCS_PAGE.read_text(encoding="utf-8")
    found = [phrase for phrase in OVERCLAIMS if phrase in text]
    assert found == [], f"docs page claims a spend breaker: {found}"
    assert DISCLOSURE in text


def test_no_shipped_module_calls_cost_tracker_charge() -> None:
    callers: list[str] = []
    for name in _shipped_modules():
        path = ROOT / f"{name}.py"
        if path.is_file() and CHARGE_CALL.search(path.read_text(encoding="utf-8")):
            callers.append(name)
    assert callers == [], (
        f"{callers} now call .charge(); the docs page says the runtime "
        f"does not meter observed spend, so review that copy"
    )
