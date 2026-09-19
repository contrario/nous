"""
NOUS Session 364 -- F1: a verifier finding that is not affirmative never
carries tier PROVEN (docs/ONE_PRICE_SOURCE_DESIGN.md sections 16.2, 16.6).

Before S364, VerificationResult.add defaulted the tier to "PROVEN" and
error(), warning() and info() passed none. Every ERROR, WARNING and INFO
item therefore left the verifier, and /v1/verify, labelled PROVEN,
including the VR001 estimate and INFO notes about checks that did not
run. Only the Z3/Farkas leg carries PROVEN, and only when its bound
holds.

Rule: an ERROR or WARNING item carries the tier its code carries when
affirmative, where that is a single tier other than PROVEN. Every other
non-affirmative item, every INFO item included, carries no tier.
"""
from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest
import tomllib

import verifier
from parser import parse_nous
from pricing import PricingTable, load_pricing
from verifier import VerificationTier, verify_program

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "templates").glob("*.nous"))
NON_AFFIRMATIVE = ("ERROR", "WARNING", "INFO")
AFFIRMATIVE_TIER = {
    "prove": VerificationTier.PROVEN,
    "verify": VerificationTier.VERIFIED,
    "estimate": VerificationTier.ESTIMATED,
    "report": VerificationTier.REPORTED,
}

needs_z3 = pytest.mark.skipif(
    importlib.util.find_spec("z3") is None, reason="needs z3"
)
needs_api = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None,
    reason="needs the server extra",
)

FIXTURE_SRC = dedent("""\
    world F1Fixture {
        law cost_ceiling = $0.000001 per cycle
        cost_cap: 0.000001 USD
        max_ticks: 3
    }

    soul Alpha {
        mind: f1-fixture-model @ Tier3
        tokens: input=200 output=80
        heal {
            on error => alert(operator)
        }
    }
""")


def _fixture_pricing() -> PricingTable:
    today = datetime.now(timezone.utc).date().isoformat()
    toml = dedent(f"""\
        _schema_version = "2.0"
        _currency = "USD"

        [models."f1-fixture-model"]
        provider = "anthropic"
        pricing_model = "per_token"
        input_per_1m = "5.00"
        output_per_1m = "25.00"
        reasoning_token_multiplier = "1.0"
        verified_date = "{today}"
    """)
    return PricingTable.model_validate(tomllib.loads(toml))


def _derived_map() -> dict[str, str]:
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    affirmative: dict[str, set[str]] = {}
    flagged: set[str] = set()
    non_constant: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Attribute) and owner.attr == "result"):
            continue
        method = node.func.attr
        if method not in AFFIRMATIVE_TIER and method not in ("error", "warning", "info"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            non_constant.append(node.lineno)
            continue
        code = node.args[0].value
        if method in AFFIRMATIVE_TIER:
            affirmative.setdefault(code, set()).add(AFFIRMATIVE_TIER[method])
        elif method in ("error", "warning"):
            flagged.add(code)
    assert non_constant == [], (
        "verifier result calls with a non-literal code at lines "
        + str(non_constant) + "; the tier map cannot be derived for them"
    )
    derived: dict[str, str] = {}
    for code in flagged:
        tiers = affirmative.get(code, set())
        if len(tiers) == 1 and VerificationTier.PROVEN not in tiers:
            derived[code] = next(iter(tiers))
    return derived


def test_tier_map_matches_the_affirmative_calls() -> None:
    shipped = getattr(verifier, "NON_AFFIRMATIVE_TIER", None)
    derived = _derived_map()
    assert shipped == derived, (
        "verifier.NON_AFFIRMATIVE_TIER must equal the tiers derived from "
        "the affirmative calls; shipped=" + repr(shipped)
        + " derived=" + repr(derived)
    )
    assert VerificationTier.PROVEN not in derived.values()


@needs_z3
@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_template_findings_carry_no_proven_tier(path: Path) -> None:
    result = verify_program(parse_nous(path.read_text(encoding="utf-8")), load_pricing())
    flagged = [i for i in result.items if i.severity in NON_AFFIRMATIVE]
    assert flagged, path.name + " emits no non-affirmative item; the check is vacuous"
    proven = [(i.code, i.severity, i.tier) for i in flagged
              if i.tier == VerificationTier.PROVEN]
    assert proven == [], path.name + " non-affirmative items tier PROVEN: " + repr(proven)
    info = [(i.code, i.tier) for i in flagged
            if i.severity == "INFO" and i.tier is not None]
    assert info == [], path.name + " INFO items carry a tier: " + repr(info)


@needs_z3
def test_fixture_findings_carry_the_rule_tiers() -> None:
    result = verify_program(parse_nous(FIXTURE_SRC), _fixture_pricing())
    got = {(i.code, i.severity): i.tier for i in result.items
           if i.severity in NON_AFFIRMATIVE}
    assert got == {
        ("VR001", "ERROR"): VerificationTier.ESTIMATED,
        ("VR002", "WARNING"): VerificationTier.ESTIMATED,
        ("VR003", "ERROR"): None,
        ("VD001", "INFO"): None,
    }, "fixture tiers: " + repr(got)


@needs_api
def test_api_verify_serves_no_proven_tier_outside_proven() -> None:
    from fastapi.testclient import TestClient
    import nous_api_server as N
    source = (ROOT / "templates" / "market_monitor.nous").read_text(encoding="utf-8")
    r = TestClient(N.app).post("/v1/verify", json={"source": source})
    assert r.status_code == 200
    j = r.json()
    entries = [(k, e["code"], e["tier"]) for k in ("errors", "warnings", "info")
               for e in j.get(k, [])]
    assert entries, "market_monitor served no non-affirmative entry"
    assert [e for e in entries if e[2] == "PROVEN"] == [], repr(entries)
    assert [e for e in entries if e[0] == "info" and e[2] is not None] == [], repr(entries)
