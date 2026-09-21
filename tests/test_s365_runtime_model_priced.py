"""
NOUS Session 365 -- arc B phase P3: the generated runtime prices its
spend pre-check by the soul's declared model through the governed pricing
table, and refuses a model the table cannot price
(docs/ONE_PRICE_SOURCE_DESIGN.md sections 9, 17.2 and 17.4).

Before P3 codegen passed only `tier=` to SoulRunner (codegen.py:787-797
and 1025-1035), and pre_check priced from the runtime.py:26 TIER_COSTS
tier-label table with a silent Tier1 fallback, so two souls declaring
different models on the same tier pre-checked at the same price and a
model the table cannot price was never refused.

RED before the P3 code stage, green after.

# __s365_p3_runtime_model_test_v1__
"""
from __future__ import annotations

import ast
import asyncio
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pytest

import runtime
from codegen import NousCodeGen
from parser import parse_nous
from pricing import PricingTable, load_pricing

REPO: Path = Path(__file__).resolve().parent.parent
TEMPLATES: list[Path] = sorted((REPO / "templates").glob("*.nous"))
TODAY: str = date.today().isoformat()

EST_IN: int = 500
EST_OUT: int = 200
TIER1_ESTIMATE: float = (EST_IN / 1000) * 0.003 + (EST_OUT / 1000) * 0.015
CHEAP_ESTIMATE: float = (EST_IN * 1.0 + EST_OUT * 4.0) / 1000000
SHIPPED_REMOVED: str = "deepseek-chat"
SHIPPED_PER_HOUR: str = "llama-3-3-70b-local"
ABSENT: str = "s365-no-such-model"


def _table(models: dict[str, Any]) -> PricingTable:
    return PricingTable.model_validate(
        {"_schema_version": "2.0", "_currency": "USD", "models": models}
    )


def _cheap_table() -> PricingTable:
    return _table({
        "s365-cheap": {
            "provider": "s365",
            "pricing_model": "per_token",
            "input_per_1m": "1.00",
            "output_per_1m": "4.00",
            "verified_date": TODAY,
        },
        "s365-free": {
            "provider": "s365",
            "pricing_model": "free",
            "input_per_1m": "0",
            "output_per_1m": "0",
            "verified_date": TODAY,
        },
    })


async def _noop_instinct() -> None:
    return None


async def _noop_heal(exc: Exception) -> bool:
    return False


def _runner(model: Optional[str], tier: str = "Tier1") -> Any:
    return runtime.SoulRunner(
        name="Probe",
        wake_strategy=runtime.SoulWakeStrategy.HEARTBEAT,
        instinct_fn=_noop_instinct,
        heal_fn=_noop_heal,
        tier=tier,
        model=model,
    )


def _generated(path: Path) -> str:
    return NousCodeGen(parse_nous(path.read_text(encoding="utf-8"))).generate()


def _const(node: Any) -> Any:
    return node.value if isinstance(node, ast.Constant) else None


def _soul_runner_kwargs(code: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in ast.walk(ast.parse(code)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "SoulRunner"
        ):
            out.append({kw.arg: kw.value for kw in node.keywords if kw.arg})
    return out


def _declared_models(path: Path) -> dict[str, str]:
    program = parse_nous(path.read_text(encoding="utf-8"))
    return {
        soul.name: (soul.mind.model if soul.mind else "unknown")
        for soul in program.souls
    }


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_codegen_passes_the_declared_model_to_every_soul_runner(
    template: Path,
) -> None:
    calls = _soul_runner_kwargs(_generated(template))
    declared = _declared_models(template)
    assert calls or not declared, f"{template.name} emitted no SoulRunner call"  # __s365_p3_red_nosoul_v1__
    emitted: dict[str, Any] = {}
    for kw in calls:
        name = _const(kw.get("name"))
        emitted[name] = _const(kw.get("model"))
    detail = f"{template.name} emitted {emitted} declared {declared}"
    assert emitted == declared, detail


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_soul_runner_call_keeps_its_tier(template: Path) -> None:
    calls = _soul_runner_kwargs(_generated(template))
    missing = [i for i, kw in enumerate(calls) if "tier" not in kw]
    assert missing == [], f"{template.name} SoulRunner calls without tier: {missing}"


def test_soul_runner_stores_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", _cheap_table(), raising=False)
    r = _runner("s365-cheap")
    got = getattr(r, "_model", "<absent>")
    assert got == "s365-cheap", f"SoulRunner._model is {got!r}"


def test_runtime_exposes_the_pricing_helpers() -> None:
    absent = [
        name
        for name in ("runtime_pricing", "resolve_soul_price", "UnpriceableSoulModel")
        if getattr(runtime, name, None) is None
    ]
    assert absent == [], f"runtime.py is missing {absent}"


def test_pre_check_prices_by_model_not_by_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", _cheap_table(), raising=False)
    ceiling = (CHEAP_ESTIMATE + TIER1_ESTIMATE) / 2
    tracker = runtime.CostTracker(ceiling=ceiling)
    by_model = asyncio.run(
        tracker.pre_check("Probe", EST_IN, EST_OUT, "Tier1", "s365-cheap")
    )
    by_tier = asyncio.run(tracker.pre_check("Probe", EST_IN, EST_OUT, "Tier1"))
    detail = (
        f"ceiling {ceiling} model estimate {CHEAP_ESTIMATE} "
        f"tier estimate {TIER1_ESTIMATE} by_model {by_model} by_tier {by_tier}"
    )
    assert by_model is True, detail
    assert by_tier is False, detail


def test_free_entry_pre_checks_at_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", _cheap_table(), raising=False)
    tracker = runtime.CostTracker(ceiling=0.0)
    got = asyncio.run(
        tracker.pre_check("Probe", EST_IN, EST_OUT, "Tier1", "s365-free")
    )
    assert got is True, f"a free entry must estimate 0.0; pre_check returned {got}"


@pytest.mark.parametrize(
    "model,prefix",
    [
        (ABSENT, "unpriceable"),
        (SHIPPED_REMOVED, "removed"),
        (SHIPPED_PER_HOUR, "per_hour"),
    ],
)
def test_unpriceable_model_refuses_when_the_runner_is_built(
    monkeypatch: pytest.MonkeyPatch, model: str, prefix: str
) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", load_pricing(), raising=False)
    exc_type = getattr(runtime, "UnpriceableSoulModel", None)
    assert exc_type is not None, "runtime.UnpriceableSoulModel is missing"
    with pytest.raises(exc_type) as caught:
        _runner(model)
    message = str(caught.value)
    assert message.startswith(prefix), f"message {message!r} for model {model!r}"
    assert model in message, f"message {message!r} does not name the model"


def test_model_none_neither_prices_nor_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", _table({}), raising=False)
    r = _runner(None)
    assert getattr(r, "_model", "<absent>") is None
    tracker = runtime.CostTracker(ceiling=TIER1_ESTIMATE * 2)
    got = asyncio.run(tracker.pre_check("Probe", EST_IN, EST_OUT, "Tier1"))
    assert got is True, f"tier path must still work with an empty table; got {got}"
