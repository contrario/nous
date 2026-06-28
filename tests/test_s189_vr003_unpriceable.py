"""
NOUS S189 -- VR003 unpriceable-model failure posture + API pricing wiring.

Part A (leg): an unpriceable model -- unknown (KeyError), removed / stale-
under-SMT / per_hour (ValueError) -- makes a cost PROOF unavailable. The
leg goes DARK (no VR003, no raise), never propagating to a 422. This is
monitor-not-guard: absence of a provable bound is "no VR003", not a
verification failure.

Part B (API): /v1/verify loads default pricing once (cached, load-failure
safe) and passes it to verify_program, lighting the live PROVEN tier for
default-priced programs while staying dark and 200 for unpriceable ones.

# __s189_vr003_unpriceable_pytest_v1__
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from pricing import PricingTable, load_pricing
from verifier import NousVerifier


z3_available = importlib.util.find_spec("z3") is not None
api_available = importlib.util.find_spec("slowapi") is not None
needs_api = pytest.mark.skipif(not api_available, reason="slowapi not installed")
needs_api_z3 = pytest.mark.skipif(
    not (api_available and z3_available), reason="needs slowapi and z3"
)


STALE_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."stale-model"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m = "5.00"
    output_per_1m = "25.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2020-01-01"
""")


GOOD_SRC = dedent("""\
    world TradingFloor {
        cost_cap: 0.50 USD
        max_ticks: 5
    }

    soul Trader {
        mind: claude-opus-4-7 @ Tier1
        tokens: input=500 output=200
        heal {
            on error => alert(operator)
        }
    }

    soul Analyst {
        mind: claude-haiku-4-5 @ Tier3
        tokens: input=300 output=150
        heal {
            on error => alert(operator)
        }
    }
""")

BAD_SRC = GOOD_SRC.replace("claude-opus-4-7", "totally-unknown-model-xyz")


def _program(model: str, cap: str = "5.00") -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="Dark",
            cost_cap=CostCap(amount=Decimal(cap), currency="USD"),
            max_ticks=5,
        ),
        souls=[
            SoulNode(
                name="S",
                mind=MindNode(model=model, tier="Tier1"),
                tokens=TokensDecl(input=500, output=200),
            ),
        ],
    )


def _vr003(result) -> list:
    return [it for it in result.items if it.code == "VR003"]


@pytest.fixture
def real_pricing() -> PricingTable:
    return load_pricing()


@pytest.fixture
def stale_pricing() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(STALE_TOML))


def test_unknown_model_dark_no_raise(real_pricing: PricingTable) -> None:
    v = NousVerifier(_program("totally-unknown-model-xyz"), real_pricing)
    v._verify_smt_cost_bound()
    assert _vr003(v.result) == []


def test_per_hour_model_dark_no_raise(real_pricing: PricingTable) -> None:
    v = NousVerifier(_program("llama-3-3-70b-local"), real_pricing)
    v._verify_smt_cost_bound()
    assert _vr003(v.result) == []


def test_stale_model_dark_no_raise(stale_pricing: PricingTable) -> None:
    v = NousVerifier(_program("stale-model"), stale_pricing)
    v._verify_smt_cost_bound()
    assert _vr003(v.result) == []


@needs_api
def test_default_pricing_helper_caches() -> None:
    import nous_api_server as N
    p1 = N._get_default_pricing()
    p2 = N._get_default_pricing()
    assert p1 is p2
    assert p1 is None or isinstance(p1, PricingTable)


@needs_api_z3
def test_api_verify_lights_vr003_for_default_priced() -> None:
    from fastapi.testclient import TestClient
    import nous_api_server as N
    client = TestClient(N.app)
    r = client.post("/v1/verify", json={"source": GOOD_SRC})
    assert r.status_code == 200
    j = r.json()
    vr003 = [e for e in j.get("proven", []) if e["code"] == "VR003"]
    assert len(vr003) == 1
    assert vr003[0]["tier"] == "PROVEN"


@needs_api
def test_api_verify_dark_for_unpriceable_no_422() -> None:
    from fastapi.testclient import TestClient
    import nous_api_server as N
    client = TestClient(N.app)
    r = client.post("/v1/verify", json={"source": BAD_SRC})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert not any(e["code"] == "VR003" for e in j.get("proven", []))
