"""
tests/test_s358_shipped_template_pricing.py

Binds every model declared by a SHIPPED template to the pricing table.

The wheel carries exactly the .nous files under templates/ (pyproject.toml:
packages = ["templates"], package-data templates = ["*.nous"]), so this is
the surface a stranger receives from PyPI. Before this gate existed, nothing
bound a declared `mind:` name to a pricing key, and the suite was green while
five shipped templates named a model the table could not resolve.

BOTH GRAMMAR SITES ARE COVERED. nous.lark declares a model name at
mind_decl and again at dream_mind; a pattern matching only the first
cannot see templates/trading_floor.nous:75.

TIME-INDEPENDENCE IS DELIBERATE. Resolution is asserted with no `today`.
Lifecycle is asserted against a pinned date. Staleness is NOT asserted here:
pricing/defaults.toml drives a 90-day hard error under --smt, so a staleness
assertion in this gate would take the suite red on a calendar date for a
reason unrelated to the defect this gate exists to catch, aborting the
release pipeline at the pytest floor phase.

# __s358_template_model_pricing_v1__
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from pricing import PricingEntry, PricingTable, lifecycle_status, load_pricing

_MIND_PATTERN: re.Pattern[str] = re.compile(
    r"^[ \t]*(?:dream_)?mind:[ \t]*([A-Za-z0-9._-]+)[ \t]*@",
    re.MULTILINE,
)

LIFECYCLE_PIN: date = date(2026, 9, 17)


def _repo_root() -> Path:
    here: Path = Path(__file__).resolve()
    candidates: list[Path] = [here.parent, *here.parents, Path.cwd().resolve()]
    for base in candidates:
        if (base / "pricing" / "defaults.toml").is_file() and (base / "templates").is_dir():
            return base
    raise RuntimeError(
        "repo root not found: no ancestor of this file and not the working "
        "directory carries both pricing/defaults.toml and templates/"
    )


def _shipped_templates() -> list[Path]:
    templates_dir: Path = _repo_root() / "templates"
    paths: list[Path] = sorted(templates_dir.glob("*.nous"))
    if not paths:
        raise RuntimeError(f"no shipped templates found under {templates_dir}")
    return paths


def _declared_models(path: Path) -> list[str]:
    text: str = path.read_text(encoding="utf-8")
    return sorted(set(_MIND_PATTERN.findall(text)))


@pytest.fixture(scope="module")
def table() -> PricingTable:
    return load_pricing()


@pytest.mark.parametrize("template", _shipped_templates(), ids=lambda p: p.name)
def test_shipped_template_models_resolve(
    template: Path,
    table: PricingTable,
) -> None:
    unresolved: list[str] = []
    for model in _declared_models(template):
        try:
            table.resolve(model)
        except KeyError:
            unresolved.append(model)
    assert not unresolved, (
        f"{template.name} declares model(s) absent from the pricing table: "
        f"{unresolved}. A shipped template must be priceable, or --smt "
        f"refuses over the documented workflow that uses it."
    )


@pytest.mark.parametrize("template", _shipped_templates(), ids=lambda p: p.name)
def test_shipped_template_models_not_removed(
    template: Path,
    table: PricingTable,
) -> None:
    removed: list[str] = []
    for model in _declared_models(template):
        try:
            canonical, entry = table.resolve(model)
        except KeyError:
            continue
        status, message = lifecycle_status(entry, today=LIFECYCLE_PIN)
        if status == "removed":
            removed.append(f"{model} -> {canonical}: {message}")
    assert not removed, (
        f"{template.name} declares model(s) the pricing table marks removed: "
        f"{removed}. get_price_for_smt raises on a removed entry."
    )


def test_every_shipped_template_declares_or_declares_nothing() -> None:
    declarations: dict[str, list[str]] = {
        path.name: _declared_models(path) for path in _shipped_templates()
    }
    assert declarations, "no shipped templates were inspected"
    for name, models in declarations.items():
        for model in models:
            assert model.strip() == model and model, (
                f"{name} yielded a malformed model token {model!r}; the "
                f"mind-declaration pattern no longer matches the grammar"
            )


def test_resolved_entries_expose_a_price_or_a_declared_alias(
    table: PricingTable,
) -> None:
    priceless: list[str] = []
    for template in _shipped_templates():
        for model in _declared_models(template):
            try:
                canonical, entry = table.resolve(model)
            except KeyError:
                continue
            assert isinstance(entry, PricingEntry)
            if entry.pricing_model == "per_token" and entry.output_per_1m is None:
                priceless.append(f"{template.name}: {model} -> {canonical}")
    assert not priceless, (
        f"per_token entries reached by shipped templates carry no "
        f"output_per_1m: {priceless}"
    )
