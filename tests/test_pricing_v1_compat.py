"""
NOUS Phase 5b -- pricing schema v1.0 backward-compatibility tests.

Covers the loader-side v1->v2 translator in `pricing._translate_v1_to_v2`.

Locks in:
  - Loading a v1.0 TOML emits exactly one DeprecationWarning
  - After load, fields are accessible under v2 names
  - Decimal precision preserved through translation
  - sha256 of v1 file == sha256 of equivalent hand-written v2 file
  - Dual-name (both v1 and v2 on same entry) is rejected
  - schema_version is "2.0" post-translation (raw_text retains v1)
  - All five renamed fields are translated
  - Non-v1 versions pass through untouched

# __nous_pricing_v1_compat_pytest_v1__
# __session70_phase5b_v2_schema_rename_v1__
"""
from __future__ import annotations

import warnings
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest

from pricing import (
    PricingTable,
    _translate_v1_to_v2,
    _load_from_path,
)


V1_MIN_TOML = dedent("""\
    _schema_version = "1.0"
    _currency = "USD"

    [models."test-model"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m_usd = "1.00"
    output_per_1m_usd = "5.00"
    verified_date = "2026-04-28"
""")


V2_EQUIVALENT_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."test-model"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2026-04-28"
""")


V1_FULL_FIELDS_TOML = dedent("""\
    _schema_version = "1.0"
    _currency = "USD"

    [models."full-fields"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m_usd = "5.00"
    output_per_1m_usd = "25.00"
    prompt_caching_supported = true
    input_cached_per_1m_usd = "0.50"
    input_cache_write_per_1m_usd = "6.25"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"

    [models."hour-billed"]
    provider = "self-hosted"
    pricing_model = "per_hour"
    hourly_cost_usd = "2.50"
    verified_date = "2026-04-28"
""")


def _write(tmp_path: Path, body: str, name: str = "p.toml") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


class TestV1ToV2Translator:

    def test_v1_emits_deprecation_warning(self, tmp_path: Path) -> None:
        p = _write(tmp_path, V1_MIN_TOML)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _load_from_path(p, layer_index=2)
        depr = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(depr) == 1, f"expected 1 DeprecationWarning, got {len(depr)}"
        assert "v1.0" in str(depr[0].message)

    def test_v2_emits_no_warning(self, tmp_path: Path) -> None:
        p = _write(tmp_path, V2_EQUIVALENT_TOML)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _load_from_path(p, layer_index=2)
        depr = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(depr) == 0

    def test_v1_fields_accessible_under_v2_names(
            self, tmp_path: Path) -> None:
        p = _write(tmp_path, V1_MIN_TOML)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            table = _load_from_path(p, layer_index=2)
        e = table.models["test-model"]
        assert e.input_per_1m == Decimal("1.00")
        assert e.output_per_1m == Decimal("5.00")

    def test_all_five_renamed_fields_translate(
            self, tmp_path: Path) -> None:
        p = _write(tmp_path, V1_FULL_FIELDS_TOML)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            table = _load_from_path(p, layer_index=2)
        full = table.models["full-fields"]
        assert full.input_per_1m == Decimal("5.00")
        assert full.output_per_1m == Decimal("25.00")
        assert full.input_cached_per_1m == Decimal("0.50")
        assert full.input_cache_write_per_1m == Decimal("6.25")
        hour = table.models["hour-billed"]
        assert hour.hourly_cost == Decimal("2.50")

    def test_decimal_precision_preserved(
            self, tmp_path: Path) -> None:
        body = V1_MIN_TOML.replace(
            'input_per_1m_usd = "1.00"',
            'input_per_1m_usd = "0.001"',
        )
        p = _write(tmp_path, body)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            table = _load_from_path(p, layer_index=2)
        e = table.models["test-model"]
        assert e.input_per_1m == Decimal("0.001")
        assert e.input_per_1m.as_integer_ratio() == (1, 1000)

    def test_schema_version_bumped_to_v2_in_memory(
            self, tmp_path: Path) -> None:
        p = _write(tmp_path, V1_MIN_TOML)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            table = _load_from_path(p, layer_index=2)
        assert table.schema_version == "2.0"

    def test_raw_text_retains_v1_source(self, tmp_path: Path) -> None:
        p = _write(tmp_path, V1_MIN_TOML)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            table = _load_from_path(p, layer_index=2)
        assert table.raw_text is not None
        assert '_schema_version = "1.0"' in table.raw_text
        assert "input_per_1m_usd" in table.raw_text

    def test_sha256_v1_equals_v2_equivalent(self, tmp_path: Path) -> None:
        """Critical sha-stability invariant: same data, same hash."""
        p1 = _write(tmp_path, V1_MIN_TOML, name="v1.toml")
        p2 = _write(tmp_path, V2_EQUIVALENT_TOML, name="v2.toml")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            t1 = _load_from_path(p1, layer_index=2)
        t2 = _load_from_path(p2, layer_index=2)
        assert t1.sha256() == t2.sha256()

    def test_dual_name_rejected(self, tmp_path: Path) -> None:
        body = dedent("""\
            _schema_version = "1.0"

            [models."conflicting"]
            provider = "test"
            pricing_model = "per_token"
            input_per_1m_usd = "1.00"
            input_per_1m = "2.00"
            output_per_1m_usd = "5.00"
            verified_date = "2026-04-28"
        """)
        p = _write(tmp_path, body)
        with pytest.raises(ValueError, match="both legacy v1"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                _load_from_path(p, layer_index=2)

    def test_non_v1_data_passes_through(self) -> None:
        """Translator is no-op for non-v1 inputs."""
        v2_data: dict = {
            "_schema_version": "2.0",
            "models": {
                "x": {
                    "provider": "test",
                    "pricing_model": "per_token",
                    "input_per_1m": "1.00",
                    "output_per_1m": "5.00",
                    "verified_date": "2026-04-28",
                }
            },
        }
        result = _translate_v1_to_v2(v2_data, source="<test>")
        assert result is v2_data


class TestV1LoaderIntegration:

    def test_v1_loaded_via_pricingtable_validate(
            self, tmp_path: Path) -> None:
        """Direct PricingTable.model_validate on v1 dict (post-translate)."""
        import tomllib
        data = tomllib.loads(V1_MIN_TOML)
        translated = _translate_v1_to_v2(data, source="<test>")
        table = PricingTable.model_validate(translated)
        e = table.models["test-model"]
        assert e.input_per_1m == Decimal("1.00")
        assert table.schema_version == "2.0"

    def test_unsupported_schema_v3_rejected(self) -> None:
        """v3.0 is unknown; must reject (not run translator)."""
        body_v3 = V1_MIN_TOML.replace(
            '_schema_version = "1.0"',
            '_schema_version = "3.0"',
        )
        import tomllib
        data = tomllib.loads(body_v3)
        # Translator is no-op for non-v1; PricingTable rejects v3.
        translated = _translate_v1_to_v2(data, source="<test>")
        with pytest.raises(Exception):
            PricingTable.model_validate(translated)
