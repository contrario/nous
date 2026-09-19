"""
NOUS Session 363 -- arc B phase P1: RUNTIME_TIERS prices come from the
governed pricing table (docs/ONE_PRICE_SOURCE_DESIGN.md sections 9, 14.9
and 15).

Before P1 the cascade carried four ids the shipped table cannot price
(three absent from OpenRouter's catalog, one retired by Anthropic),
priced deepseek-v4-flash at 0.14/0.28 per 1M while the table bills the
same id at the Flash price, and decided "free" by comparing two float
literals.

RED before the P1 code stage, green after.

# __s363_p1_runtime_tiers_test_v1__
"""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import nous_runtime
from pricing import PricingTable, load_pricing

REPO: Path = Path(__file__).resolve().parent.parent
SHIPPED: Path = REPO / "pricing" / "defaults.toml"
OPENROUTER_MODEL_ENDPOINT: str = "https://openrouter.ai/api/v1/model/"
K2_IDS: tuple[str, ...] = (
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openrouter/elephant-alpha",
    "openai/gpt-oss-120b:free",
    "claude-3-haiku-20240307",
)
FREE_PINS: dict[str, str] = {
    "nvidia/nemotron-3-super-120b-a12b:free": "539c4a1d3a575f2c10c271461a4626e6b22793e3601f25a773bc39f9cfb2c6ae",
    "google/gemma-4-31b-it:free": "a357caa3d7b5233abc39de760c4b1b265aee0c2794211c634b962ed5d0b9b159",
}
TEST_KEY_ENV: str = "NOUS_S363_TEST_KEY"
THOUSAND: Decimal = Decimal(1000)


def _shipped() -> PricingTable:
    return load_pricing(SHIPPED)


def _table(models: dict[str, Any]) -> PricingTable:
    return PricingTable.model_validate(
        {"_schema_version": "2.0", "_currency": "USD", "models": models}
    )


def _tier(model: str) -> Any:
    return nous_runtime.RuntimeTier(
        name="S363Probe",
        base_url="https://example.invalid/v1/chat/completions",
        model=model,
        api_key_env=TEST_KEY_ENV,
    )


class _NetworkTouched(Exception):
    pass


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    class _Refuse:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append("AsyncClient")
            raise _NetworkTouched("network client constructed")

    monkeypatch.setattr(nous_runtime.httpx, "AsyncClient", _Refuse)
    monkeypatch.setenv(TEST_KEY_ENV, "s363-not-a-key")
    return calls


@pytest.fixture
def shipped_dispatch(monkeypatch: pytest.MonkeyPatch) -> PricingTable:
    table = _shipped()
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", table, raising=False)
    return table


def _resolve_all(table: PricingTable) -> tuple[dict[str, Any], list[str]]:
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for tier in nous_runtime.RUNTIME_TIERS:
        try:
            resolved[tier.model] = table.resolve(tier.model)
        except (KeyError, ValueError) as e:
            missing.append(f"{tier.name} {tier.model!r}: {type(e).__name__}")
    return resolved, missing


def test_every_runtime_tier_id_resolves_in_shipped_table() -> None:
    ids = [t.model for t in nous_runtime.RUNTIME_TIERS]
    _, missing = _resolve_all(_shipped())
    assert missing == [], f"tiers {ids}; unresolved {missing}"


def test_runtime_tier_ids_are_canonical_table_entries() -> None:
    resolved, missing = _resolve_all(_shipped())
    aliased = {m: c for m, (c, _) in resolved.items() if c != m}
    assert missing == [] and aliased == {}, (
        f"unresolved {missing}; dispatched through an alias {aliased}"
    )


def test_no_runtime_tier_entry_carries_removal_or_hourly_billing() -> None:
    resolved, missing = _resolve_all(_shipped())
    bad = {
        m: (e.pricing_model, e.removed_after, e.deprecated_after)
        for m, (_, e) in resolved.items()
        if e.pricing_model not in ("free", "per_token")
        or e.removed_after is not None
        or e.deprecated_after is not None
    }
    assert missing == [] and bad == {}, f"unresolved {missing}; lifecycle or billing {bad}"


def test_k2_ids_left_the_cascade() -> None:
    ids = [t.model for t in nous_runtime.RUNTIME_TIERS]
    still = sorted(set(ids) & set(K2_IDS))
    assert still == [], f"tiers {ids}; K2 ids still dispatched {still}"


def test_cost_fields_equal_the_table(shipped_dispatch: PricingTable) -> None:
    rows: list[str] = []
    bad: list[str] = []
    for tier in nous_runtime.RUNTIME_TIERS:
        try:
            _, entry = shipped_dispatch.resolve(tier.model)
        except (KeyError, ValueError) as e:
            bad.append(f"{tier.model!r} unresolved: {type(e).__name__}")
            continue
        want_in = float((entry.input_per_1m or Decimal(0)) / THOUSAND)
        want_out = float((entry.output_per_1m or Decimal(0)) / THOUSAND)
        got = (tier.cost_per_1k_in, tier.cost_per_1k_out)
        rows.append(f"{tier.model!r} code {got} table {(want_in, want_out)}")
        if got != (want_in, want_out):
            bad.append(rows[-1])
    assert bad == [], "\n".join(["mismatch:"] + bad + ["all:"] + rows)


def test_is_free_is_the_table_pricing_model(shipped_dispatch: PricingTable) -> None:
    rows: list[str] = []
    bad: list[str] = []
    for tier in nous_runtime.RUNTIME_TIERS:
        try:
            _, entry = shipped_dispatch.resolve(tier.model)
            want = entry.pricing_model == "free"
        except (KeyError, ValueError):
            want = False
        rows.append(f"{tier.model!r} is_free {tier.is_free} table_free {want}")
        if tier.is_free != want:
            bad.append(rows[-1])
    assert bad == [], "\n".join(bad + ["all:"] + rows)


@pytest.mark.parametrize("model_id", sorted(FREE_PINS))
def test_free_entry_carries_its_stored_pin(model_id: str) -> None:
    table = _shipped()
    assert model_id in table.models, f"{model_id!r} not in {sorted(table.models)}"
    entry = table.models[model_id]
    detail = (
        f"pricing_model {entry.pricing_model} provider {entry.provider} "
        f"prices {entry.input_per_1m}/{entry.output_per_1m} "
        f"verified {entry.verified_date} source {entry.source_url} "
        f"pin {FREE_PINS[model_id]}"
    )
    assert entry.alias_of is None, detail
    assert entry.pricing_model == "free", detail
    assert entry.provider == "openrouter", detail
    assert entry.input_per_1m == Decimal(0) and entry.output_per_1m == Decimal(0), detail
    assert entry.verified_date is not None, detail
    assert entry.source_url == OPENROUTER_MODEL_ENDPOINT + model_id, detail
    assert entry.notes is not None and FREE_PINS[model_id] in entry.notes, detail


def test_unpriceable_tier_refuses_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", _table({}), raising=False)
    result = asyncio.run(_tier("s363-unpriced-model").call("sys", "user"))
    detail = f"result {result} network {no_network}"
    assert result.get("success") is False, detail
    assert str(result.get("error", "")).startswith("unpriceable"), detail
    assert no_network == [], detail


def test_unpriceable_tier_stream_refuses_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", _table({}), raising=False)

    async def _first() -> tuple[str, Any]:
        gen = _tier("s363-unpriced-model").stream_call("sys", "user")
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    event = asyncio.run(_first())
    detail = f"event {event} network {no_network}"
    assert event[0] == "error", detail
    assert str(event[1].get("error", "")).startswith("unpriceable"), detail
    assert no_network == [], detail


def test_unpriceable_tier_is_not_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", _table({}), raising=False)
    tier = _tier("s363-unpriced-model")
    assert tier.is_free is False, f"is_free {tier.is_free} for an id the table cannot price"


def test_removed_entry_refuses_at_dispatch(
    monkeypatch: pytest.MonkeyPatch, no_network: list[str]
) -> None:
    table = _table({
        "s363-gone": {
            "provider": "somebody",
            "pricing_model": "per_token",
            "input_per_1m": "1.00",
            "output_per_1m": "5.00",
            "verified_date": "2020-01-01",
            "removed_after": "2020-06-30",
        },
    })
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", table, raising=False)
    result = asyncio.run(_tier("s363-gone").call("sys", "user"))
    detail = f"result {result} network {no_network}"
    assert result.get("success") is False, detail
    assert str(result.get("error", "")).startswith("removed"), detail
    assert no_network == [], detail


def test_stale_entry_warns_and_still_prices() -> None:
    resolve = getattr(nous_runtime, "resolve_tier_price", None)
    assert resolve is not None, "nous_runtime.resolve_tier_price is missing"
    table = _table({
        "s363-old": {
            "provider": "somebody",
            "pricing_model": "per_token",
            "input_per_1m": "2.00",
            "output_per_1m": "8.00",
            "verified_date": "2020-01-01",
        },
    })
    price = resolve("s363-old", table)
    detail = f"price {price}"
    assert price.staleness == "warn", detail
    assert (price.cost_per_1k_in, price.cost_per_1k_out) == (0.002, 0.008), detail


def test_dispatch_pricing_is_the_layered_loader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    loader = getattr(nous_runtime, "dispatch_pricing", None)
    assert loader is not None, "nous_runtime.dispatch_pricing is missing"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nous_runtime, "_DISPATCH_PRICING", None, raising=False)
    got = loader().sha256()
    want = _shipped().sha256()
    assert got == want, f"dispatch table {got} shipped table {want}"


def test_nous_runtime_defines_no_per_token_price_literal() -> None:
    src = (REPO / "nous_runtime.py").read_text(encoding="utf-8")
    hits = re.findall(r"cost_per_1k_(?:in|out)\s*=\s*[0-9]", src)
    assert hits == [], f"price literals in nous_runtime.py: {hits}"
