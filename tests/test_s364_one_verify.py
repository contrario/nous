"""
NOUS Session 364 -- arc B phase P2: `nous verify` and /v1/verify return
the same finding set for the same program, and with a pricing table VR001
prices each soul by its declared model (docs/ONE_PRICE_SOURCE_DESIGN.md
sections 9, 16.4 and 16.7).

Before S364 the CLI called the verifier with no table at nine sites, so
VR003 ran only from the API, and VR001 priced every soul from tier-label
constants with a silent Tier1 fallback. The API turned a pricing load
failure into None and skipped VR003 without a finding.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
import tomllib

import cli
import dated_prices
import verifier
from parser import parse_nous
from pricing import PricingTable, load_pricing
from verifier import verify_program

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "templates").glob("*.nous"))
PINNED_TODAY = date(2026, 9, 19)

needs_api_z3 = pytest.mark.skipif(
    importlib.util.find_spec("slowapi") is None
    or importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("z3") is None,
    reason="needs the server extra and z3",
)

TIER_VS_MODEL_SRC = dedent("""\
    world TierVsModel {
        law cost_ceiling = $0.001 per cycle
    }

    soul Scout {
        mind: claude-opus-4-7 @ Tier0A
        heal {
            on error => alert(operator)
        }
    }
""")

UNPRICEABLE_SRC = dedent("""\
    world Unpriceable {
        law cost_ceiling = $0.10 per cycle
    }

    soul Scout {
        mind: totally-unknown-model-xyz @ Tier1
        heal {
            on error => alert(operator)
        }
    }
""")

CASES = [(p.name, p.read_text(encoding="utf-8")) for p in TEMPLATES] + [
    ("tier_vs_model", TIER_VS_MODEL_SRC),
    ("unpriceable", UNPRICEABLE_SRC),
]

CLI_VERIFY_COMMANDS = [
    "verify", "dream", "immune", "mitosis", "consciousness",
    "metabolism", "symbiosis", "telemetry", "retire",
]


def _table(entries: str, currency: str = "USD") -> PricingTable:
    head = f'_schema_version = "2.0"\n_currency = "{currency}"\n\n'
    return PricingTable.model_validate(tomllib.loads(head + dedent(entries)))


def _program(model: str, law: str = "$0.10") -> Any:
    return parse_nous(dedent(f"""\
        world Fixture {{
            law cost_ceiling = {law} per cycle
        }}

        soul Probe {{
            mind: {model} @ Tier1
            heal {{
                on error => alert(operator)
            }}
        }}
    """))


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bool, list[tuple[str, str, str]]]]:
    calls: list[tuple[bool, list[tuple[str, str, str]]]] = []
    original = verifier.NousVerifier.verify

    def recording_verify(self: verifier.NousVerifier) -> verifier.VerificationResult:
        result = original(self)
        calls.append((
            getattr(self, "_pricing", None) is not None,
            [(i.code, i.severity, i.message) for i in result.items],
        ))
        return result

    monkeypatch.setattr(verifier.NousVerifier, "verify", recording_verify)
    return calls


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
             argv: list[str]) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["nous", *argv])
    try:
        rc = cli.main()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    err = capsys.readouterr().err
    return (rc if isinstance(rc, int) else 0), err


def _post(source: str) -> Any:
    from fastapi.testclient import TestClient
    import nous_api_server as N
    return TestClient(N.app).post("/v1/verify", json={"source": source})


def _finding_set(items: list[tuple[str, str, str]]) -> Counter[tuple[str, str]]:
    return Counter((code, severity) for code, severity, _ in items)


@needs_api_z3
@pytest.mark.parametrize("name,source", CASES, ids=[c[0] for c in CASES])
def test_cli_and_api_return_the_same_finding_set(
        name: str, source: str, tmp_path: Path,
        recorder: list[tuple[bool, list[tuple[str, str, str]]]],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "program.nous"
    path.write_text(source, encoding="utf-8")
    _run_cli(monkeypatch, capsys, ["verify", str(path), "--no-lint"])
    assert len(recorder) == 1, name + ": the CLI ran the verifier " + str(len(recorder)) + " times"
    r = _post(source)
    assert r.status_code == 200, name + ": " + r.text[:300]
    assert len(recorder) == 2, name + ": the API did not run the verifier"
    cli_set = _finding_set(recorder[0][1])
    api_set = _finding_set(recorder[1][1])
    assert cli_set == api_set, (
        name + ": CLI only " + repr(dict(cli_set - api_set))
        + "; API only " + repr(dict(api_set - cli_set))
    )


@needs_api_z3
def test_vr001_prices_by_model_on_both_surfaces(
        tmp_path: Path, recorder: list[tuple[bool, list[tuple[str, str, str]]]],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    dated_prices.use_dated_shipped_prices(tmp_path, monkeypatch)  # __s371_a1_dated_v1__
    _, entry = load_pricing().resolve("claude-opus-4-7")
    expected = float(
        (entry.input_per_1m * 300 + entry.output_per_1m * 200 * entry.reasoning_token_multiplier)
        / Decimal(1000000)
    )
    tier_estimate = 0.3 * 0.00025 + 0.2 * 0.00125
    assert tier_estimate <= 0.001 < expected, "fixture no longer separates tier and model prices"
    path = tmp_path / "program.nous"
    path.write_text(TIER_VS_MODEL_SRC, encoding="utf-8")
    _run_cli(monkeypatch, capsys, ["verify", str(path), "--no-lint"])
    _post(TIER_VS_MODEL_SRC)
    assert len(recorder) == 2
    for surface, (_, items) in zip(("cli", "api"), recorder):
        vr001 = [(sev, msg) for code, sev, msg in items if code == "VR001"]
        assert len(vr001) == 1 and vr001[0][0] == "ERROR", surface + ": " + repr(vr001)
        assert f"${expected:.6f}" in vr001[0][1], surface + ": " + vr001[0][1]


@needs_api_z3
def test_unpriceable_model_is_a_vr001_error_on_both_surfaces(
        tmp_path: Path, recorder: list[tuple[bool, list[tuple[str, str, str]]]],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "program.nous"
    path.write_text(UNPRICEABLE_SRC, encoding="utf-8")
    rc, _ = _run_cli(monkeypatch, capsys, ["verify", str(path), "--no-lint"])
    r = _post(UNPRICEABLE_SRC)
    assert rc != 0
    assert r.status_code == 200 and r.json().get("ok") is False
    assert len(recorder) == 2
    for surface, (_, items) in zip(("cli", "api"), recorder):
        errors = [msg for code, sev, msg in items if code == "VR001" and sev == "ERROR"]
        assert errors and "totally-unknown-model-xyz" in errors[0], surface + ": " + repr(items)


@pytest.mark.parametrize("command", CLI_VERIFY_COMMANDS)
def test_every_cli_verify_site_passes_a_table(
        command: str, recorder: list[tuple[bool, list[tuple[str, str, str]]]],
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    argv = [command, str(ROOT / "templates" / "trading_floor.nous")]
    if command == "verify":
        argv.append("--no-lint")
    _run_cli(monkeypatch, capsys, argv)
    assert recorder, command + " did not run the verifier"
    assert all(supplied for supplied, _ in recorder), command + " ran the verifier without a pricing table"


def test_cli_pricing_load_failure_is_a_typed_error(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "program.nous"
    path.write_text(TIER_VS_MODEL_SRC, encoding="utf-8")
    rc, err = _run_cli(monkeypatch, capsys, [
        "verify", str(path), "--prices", str(tmp_path / "missing.toml"), "--no-lint",
    ])
    assert rc == 1, "rc " + str(rc) + " stderr " + err[:300]
    assert "Error: pricing table could not be loaded" in err, err[:300]


@needs_api_z3
def test_api_pricing_load_failure_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import nous_api_server as N
    import pricing

    def failing_load(custom_path: Any = None) -> PricingTable:
        raise OSError("simulated unreadable table")

    monkeypatch.setattr(N, "_DEFAULT_PRICING", None)
    monkeypatch.setattr(N, "_DEFAULT_PRICING_LOADED", False)
    monkeypatch.setattr(pricing, "load_pricing", failing_load)
    r = _post(TIER_VS_MODEL_SRC)
    assert r.status_code == 422, str(r.status_code) + " " + r.text[:300]
    assert "pricing table could not be loaded" in r.text, r.text[:300]


def test_stale_price_is_a_vr001_warning_not_a_refusal() -> None:
    table = _table("""\
        [models."p2-stale-model"]
        provider = "anthropic"
        pricing_model = "per_token"
        input_per_1m = "1.00"
        output_per_1m = "5.00"
        reasoning_token_multiplier = "1.0"
        verified_date = "2026-01-01"
    """)
    result = verify_program(_program("p2-stale-model"), table, today=PINNED_TODAY)
    vr001 = [(i.severity, i.message) for i in result.items if i.code == "VR001"]
    assert [s for s, _ in vr001 if s == "ERROR"] == [], repr(vr001)
    warnings = [m for s, m in vr001 if s == "WARNING"]
    assert len(warnings) == 1 and "p2-stale-model" in warnings[0], repr(vr001)


def test_removed_and_per_hour_entries_are_vr001_errors() -> None:
    table = _table("""\
        [models."p2-removed-model"]
        provider = "anthropic"
        pricing_model = "per_token"
        input_per_1m = "1.00"
        output_per_1m = "5.00"
        reasoning_token_multiplier = "1.0"
        verified_date = "2026-09-01"
        removed_after = "2026-07-24"

        [models."p2-hourly-model"]
        provider = "self-hosted"
        pricing_model = "per_hour"
        hourly_cost = "2.50"
        verified_date = "2026-09-01"
    """)
    for model, needle in (("p2-removed-model", "removed"), ("p2-hourly-model", "per hour")):
        result = verify_program(_program(model), table, today=PINNED_TODAY)
        errors = [i.message for i in result.items if i.code == "VR001" and i.severity == "ERROR"]
        assert errors and needle in errors[0] and model in errors[0], model + ": " + repr(errors)


def test_table_currency_must_match_the_cost_law() -> None:
    table = _table("""\
        [models."p2-eur-model"]
        provider = "anthropic"
        pricing_model = "per_token"
        input_per_1m = "1.00"
        output_per_1m = "5.00"
        reasoning_token_multiplier = "1.0"
        verified_date = "2026-09-01"
    """, currency="EUR")
    result = verify_program(_program("p2-eur-model"), table)
    errors = [i.message for i in result.items if i.code == "VR001" and i.severity == "ERROR"]
    assert errors and "EUR" in errors[0] and "USD" in errors[0], repr(errors)


def test_no_table_keeps_the_tier_estimate() -> None:
    result = verify_program(parse_nous(TIER_VS_MODEL_SRC))
    vr001 = [(i.severity, i.message) for i in result.items if i.code == "VR001"]
    assert len(vr001) == 1 and vr001[0][0] == "PROVEN", repr(vr001)
    assert "$0.000325" in vr001[0][1], repr(vr001)
