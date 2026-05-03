"""
NOUS Phase 3b — pricing module tests.

Covers:
  - Schema strict-mode (unknown fields rejected)
  - Float values rejected (Decimal preservation)
  - Alias resolution + cycle detection
  - Lifecycle (deprecated, removed, renamed)
  - Staleness (warn / error thresholds)
  - sha256 deterministic
  - Layered loader priority
  - get_price_for_smt() rejections
  - Free / per_hour edge cases

# __nous_pricing_pytest_v1__
# __session70_phase5b_v2_schema_rename_v1__
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest

from pricing import (
    PricingEntry,
    PricingTable,
    STALENESS_ERROR_DAYS_UNDER_SMT,
    STALENESS_WARN_DAYS,
    get_price_for_smt,
    lifecycle_status,
    load_pricing,
    staleness_status,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

VALID_MIN_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."test-model"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2026-04-28"
""")


def _write(tmp_path: Path, body: str, name: str = "p.toml") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _load(tmp_path: Path, body: str) -> PricingTable:
    p = _write(tmp_path, body)
    import tomllib
    data = tomllib.loads(body)
    table = PricingTable.model_validate(data)
    table.source_path = p
    return table


# ─────────────────────────────────────────────────────────────────────
# Schema strictness
# ─────────────────────────────────────────────────────────────────────

class TestSchemaStrictness:

    def test_unknown_top_level_field_rejected(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML + '\n_unknown_field = "x"\n'
        with pytest.raises(Exception):
            _load(tmp_path, body)

    def test_unknown_entry_field_rejected(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML.replace(
            'verified_date = "2026-04-28"',
            'verified_date = "2026-04-28"\nbogus_key = "x"',
        )
        with pytest.raises(Exception):
            _load(tmp_path, body)

    def test_float_values_rejected(self, tmp_path: Path) -> None:
        """Floats produce IEEE 754 rounding; only strings/ints allowed."""
        body = VALID_MIN_TOML.replace(
            'input_per_1m = "1.00"',
            "input_per_1m = 1.00",  # bare float
        )
        with pytest.raises(Exception):
            _load(tmp_path, body)

    def test_unsupported_schema_version_rejected(self,
                                                 tmp_path: Path) -> None:
        body = VALID_MIN_TOML.replace(
            '_schema_version = "2.0"', '_schema_version = "3.0"'
        )
        with pytest.raises(Exception):
            _load(tmp_path, body)

    def test_decimal_preserved_exactly(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML.replace(
            'input_per_1m = "1.00"',
            'input_per_1m = "0.001"',
        )
        table = _load(tmp_path, body)
        e = table.models["test-model"]
        assert e.input_per_1m == Decimal("0.001")
        assert e.input_per_1m.as_integer_ratio() == (1, 1000)


# ─────────────────────────────────────────────────────────────────────
# Aliases
# ─────────────────────────────────────────────────────────────────────

class TestAliases:

    def test_alias_resolves_to_canonical(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML + dedent("""\

            [models."test-alias"]
            alias_of = "test-model"
        """)
        table = _load(tmp_path, body)
        canonical, entry = table.resolve("test-alias")
        assert canonical == "test-model"
        assert entry.input_per_1m == Decimal("1.00")

    def test_alias_to_unknown_model_rejected(self,
                                             tmp_path: Path) -> None:
        body = VALID_MIN_TOML + dedent("""\

            [models."dangling-alias"]
            alias_of = "nonexistent"
        """)
        with pytest.raises(Exception):
            _load(tmp_path, body)

    def test_alias_cycle_rejected(self, tmp_path: Path) -> None:
        body = dedent("""\
            _schema_version = "2.0"

            [models."a"]
            alias_of = "b"

            [models."b"]
            alias_of = "a"
        """)
        with pytest.raises(Exception):
            _load(tmp_path, body)


# ─────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────

class TestLifecycle:

    def test_active_model_status_ok(self, tmp_path: Path) -> None:
        table = _load(tmp_path, VALID_MIN_TOML)
        e = table.models["test-model"]
        status, _ = lifecycle_status(e, today=date(2026, 4, 28))
        assert status == "ok"

    def test_deprecated_model_detected(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML.replace(
            'verified_date = "2026-04-28"',
            'verified_date = "2026-04-28"\n'
            'deprecated_after = "2026-01-01"',
        )
        table = _load(tmp_path, body)
        e = table.models["test-model"]
        status, msg = lifecycle_status(e, today=date(2026, 4, 28))
        assert status == "deprecated"
        assert "2026-01-01" in msg

    def test_removed_model_blocks_smt(self, tmp_path: Path) -> None:
        body = VALID_MIN_TOML.replace(
            'verified_date = "2026-04-28"',
            'verified_date = "2026-04-28"\n'
            'removed_after = "2026-01-01"',
        )
        table = _load(tmp_path, body)
        with pytest.raises(ValueError, match="cannot be used"):
            get_price_for_smt(table, "test-model",
                              today=date(2026, 4, 28))


# ─────────────────────────────────────────────────────────────────────
# Staleness
# ─────────────────────────────────────────────────────────────────────

class TestStaleness:

    def test_fresh_entry_is_ok(self, tmp_path: Path) -> None:
        table = _load(tmp_path, VALID_MIN_TOML)
        e = table.models["test-model"]
        status, _ = staleness_status(e, today=date(2026, 4, 28))
        assert status == "ok"

    def test_stale_entry_warns_above_30d(self, tmp_path: Path) -> None:
        table = _load(tmp_path, VALID_MIN_TOML)
        e = table.models["test-model"]
        status, _ = staleness_status(
            e, today=date(2026, 4, 28) + timedelta(days=45),
        )
        assert status == "warn"

    def test_stale_entry_errors_above_90d_under_smt(
            self, tmp_path: Path) -> None:
        table = _load(tmp_path, VALID_MIN_TOML)
        e = table.models["test-model"]
        status, _ = staleness_status(
            e, today=date(2026, 4, 28) + timedelta(days=120),
            under_smt=True,
        )
        assert status == "error"

    def test_get_price_for_smt_rejects_stale(self,
                                             tmp_path: Path) -> None:
        table = _load(tmp_path, VALID_MIN_TOML)
        with pytest.raises(ValueError, match="too old"):
            get_price_for_smt(
                table, "test-model",
                today=date(2026, 4, 28) + timedelta(days=120),
            )


# ─────────────────────────────────────────────────────────────────────
# Pricing model variants
# ─────────────────────────────────────────────────────────────────────

class TestPricingModels:

    def test_free_model_zero_prices(self, tmp_path: Path) -> None:
        body = dedent("""\
            _schema_version = "2.0"

            [models."local"]
            provider = "local"
            pricing_model = "free"
            input_per_1m = "0"
            output_per_1m = "0"
            verified_date = "2026-04-28"
        """)
        table = _load(tmp_path, body)
        canonical, e = get_price_for_smt(
            table, "local", today=date(2026, 4, 28),
        )
        assert canonical == "local"
        assert e.input_per_1m == Decimal("0")

    def test_per_hour_rejected_under_smt(self, tmp_path: Path) -> None:
        body = dedent("""\
            _schema_version = "2.0"

            [models."llama-local"]
            provider = "self-hosted"
            pricing_model = "per_hour"
            hourly_cost = "2.50"
            verified_date = "2026-04-28"
        """)
        table = _load(tmp_path, body)
        with pytest.raises(ValueError, match="per_hour"):
            get_price_for_smt(table, "llama-local",
                              today=date(2026, 4, 28))


# ─────────────────────────────────────────────────────────────────────
# sha256 + layered loader
# ─────────────────────────────────────────────────────────────────────

class TestSha256:

    def test_sha256_deterministic_across_reloads(
            self, tmp_path: Path) -> None:
        t1 = _load(tmp_path, VALID_MIN_TOML)
        t2 = _load(tmp_path, VALID_MIN_TOML)
        assert t1.sha256() == t2.sha256()
        assert len(t1.sha256()) == 64

    def test_sha256_changes_on_content_change(
            self, tmp_path: Path) -> None:
        t1 = _load(tmp_path, VALID_MIN_TOML)
        t2 = _load(tmp_path, VALID_MIN_TOML.replace(
            'input_per_1m = "1.00"',
            'input_per_1m = "1.50"',
        ))
        assert t1.sha256() != t2.sha256()

    def test_sha256_stable_across_whitespace(
            self, tmp_path: Path) -> None:
        """Adding whitespace/newlines must not change the canonical hash."""
        t1 = _load(tmp_path, VALID_MIN_TOML)
        t2 = _load(tmp_path, VALID_MIN_TOML + "\n\n# trailing comment\n")
        assert t1.sha256() == t2.sha256()


class TestLayeredLoader:

    def test_loads_shipped_defaults_when_no_overrides(
            self, monkeypatch, tmp_path: Path) -> None:
        """With no cwd or HOME overrides, falls back to package defaults."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        table = load_pricing()
        # Whatever ships, it must be schema 1.0 and have at least one model.
        assert table.schema_version == "2.0"
        assert len(table.models) > 0
        assert table.layer_index == 4
