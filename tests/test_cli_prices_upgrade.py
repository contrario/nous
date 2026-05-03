"""
NOUS Phase 5b Step 7 -- `nous prices upgrade` CLI tests.

Covers:
  - v1 -> v2 migration via -o output path
  - --in-place rewrite
  - Idempotent on v2 (no-op message)
  - Reject v3+ (unknown schema)
  - Reject input with no _schema_version
  - Refuse overwrite without --force
  - --force allows overwrite
  - --in-place and -o mutually exclusive
  - Comments and blank lines preserved verbatim
  - All five renamed fields handled
  - Validates post-migration via PricingTable

# __nous_cli_prices_upgrade_pytest_v1__
# __session70_phase5b_step7_upgrade_cli_v1__
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest
import tomllib

from cli_prices import (
    _V1_TO_V2_FIELD_RENAMES,
    _migrate_v1_text,
    cmd_prices_upgrade,
)
from pricing import PricingTable, _translate_v1_to_v2


V1_BASIC = dedent("""\
    # Header comment
    _schema_version = "1.0"
    _currency = "USD"

    # Section A -- Anthropic
    [models."claude-opus-4-7"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m_usd = "5.00"
    output_per_1m_usd = "25.00"
    input_cached_per_1m_usd = "0.50"
    input_cache_write_per_1m_usd = "6.25"
    verified_date = "2026-04-28"

    # Section B -- self-hosted
    [models."llama-local"]
    provider = "self-hosted"
    pricing_model = "per_hour"
    hourly_cost_usd = "2.50"
    verified_date = "2026-04-28"
""")


V2_ALREADY = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."test"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2026-04-28"
""")


V3_UNKNOWN = dedent("""\
    _schema_version = "3.0"

    [models."test"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    verified_date = "2026-04-28"
""")


def _make_args(
    input_path: Path,
    output: Path | None = None,
    in_place: bool = False,
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        input=str(input_path),
        output=str(output) if output else None,
        in_place=in_place,
        force=force,
    )


class TestMigrateV1Text:

    def test_all_five_fields_renamed(self) -> None:
        new_text, counts, bumped = _migrate_v1_text(V1_BASIC)
        assert bumped is True
        assert counts["input_per_1m_usd"] == 1
        assert counts["output_per_1m_usd"] == 1
        assert counts["input_cached_per_1m_usd"] == 1
        assert counts["input_cache_write_per_1m_usd"] == 1
        assert counts["hourly_cost_usd"] == 1
        assert "input_per_1m_usd" not in new_text
        assert "input_per_1m " in new_text or 'input_per_1m=' in new_text

    def test_comments_preserved(self) -> None:
        new_text, _, _ = _migrate_v1_text(V1_BASIC)
        assert "# Header comment" in new_text
        assert "# Section A -- Anthropic" in new_text
        assert "# Section B -- self-hosted" in new_text

    def test_blank_lines_preserved(self) -> None:
        new_text, _, _ = _migrate_v1_text(V1_BASIC)
        # Original has 2 blank lines between sections; migrated must too.
        assert V1_BASIC.count("\n\n") == new_text.count("\n\n")

    def test_schema_version_bumped(self) -> None:
        new_text, _, bumped = _migrate_v1_text(V1_BASIC)
        assert bumped is True
        assert '_schema_version = "2.0"' in new_text
        assert '_schema_version = "1.0"' not in new_text

    def test_no_field_in_comments_changed(self) -> None:
        body = dedent("""\
            _schema_version = "1.0"
            # The field input_per_1m_usd was renamed in v2.0.
            [models."x"]
            provider = "test"
            pricing_model = "per_token"
            input_per_1m_usd = "1.00"
            output_per_1m_usd = "5.00"
            verified_date = "2026-04-28"
        """)
        new_text, counts, _ = _migrate_v1_text(body)
        # The comment line is preserved unchanged
        assert (
            "# The field input_per_1m_usd was renamed in v2.0."
            in new_text
        )
        # Both real keys renamed (1 each)
        assert counts["input_per_1m_usd"] == 1
        assert counts["output_per_1m_usd"] == 1

    def test_post_migration_validates_via_pricingtable(self) -> None:
        new_text, _, _ = _migrate_v1_text(V1_BASIC)
        data = tomllib.loads(new_text)
        # Translator is no-op on v2 input
        translated = _translate_v1_to_v2(data, source="<test>")
        table = PricingTable.model_validate(translated)
        assert table.schema_version == "2.0"
        e = table.models["claude-opus-4-7"]
        assert e.input_per_1m == Decimal("5.00")
        assert e.input_cache_write_per_1m == Decimal("6.25")
        h = table.models["llama-local"]
        assert h.hourly_cost == Decimal("2.50")


class TestCmdPricesUpgrade:

    def test_basic_migration_to_separate_output(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "in.toml"
        out_p = tmp_path / "out.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        rc = cmd_prices_upgrade(_make_args(in_p, output=out_p))
        assert rc == 0
        assert out_p.is_file()
        assert in_p.read_text(encoding="utf-8") == V1_BASIC  # untouched
        out_text = out_p.read_text(encoding="utf-8")
        assert '_schema_version = "2.0"' in out_text
        assert "input_per_1m_usd" not in out_text
        captured = capsys.readouterr()
        assert "OK: migrated v1.0 -> v2.0" in captured.out
        assert "5 total" in captured.out

    def test_in_place_migration(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "prices.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=None, in_place=True),
        )
        assert rc == 0
        out_text = in_p.read_text(encoding="utf-8")
        assert '_schema_version = "2.0"' in out_text
        assert "input_per_1m_usd" not in out_text

    def test_already_v2_is_noop(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "v2.toml"
        in_p.write_text(V2_ALREADY, encoding="utf-8")
        out_p = tmp_path / "out.toml"
        rc = cmd_prices_upgrade(_make_args(in_p, output=out_p))
        assert rc == 0
        captured = capsys.readouterr()
        assert "already v2.0" in captured.out
        # Output file NOT created (idempotent no-op)
        assert not out_p.exists()

    def test_v3_rejected(self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "v3.toml"
        in_p.write_text(V3_UNKNOWN, encoding="utf-8")
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=tmp_path / "out.toml"),
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "only v1.0 -> v2.0" in captured.err

    def test_no_schema_version_rejected(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "no-sv.toml"
        in_p.write_text(
            '[models."x"]\nprovider = "test"\n',
            encoding="utf-8",
        )
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=tmp_path / "out.toml"),
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "_schema_version" in captured.err

    def test_overwrite_refused_without_force(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "in.toml"
        out_p = tmp_path / "out.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        out_p.write_text("# pre-existing\n", encoding="utf-8")
        rc = cmd_prices_upgrade(_make_args(in_p, output=out_p))
        assert rc == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.err
        assert "--force" in captured.err
        # Output file untouched
        assert out_p.read_text(encoding="utf-8") == "# pre-existing\n"

    def test_force_allows_overwrite(
            self, tmp_path: Path) -> None:
        in_p = tmp_path / "in.toml"
        out_p = tmp_path / "out.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        out_p.write_text("# pre-existing\n", encoding="utf-8")
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=out_p, force=True),
        )
        assert rc == 0
        out_text = out_p.read_text(encoding="utf-8")
        assert "# pre-existing" not in out_text
        assert '_schema_version = "2.0"' in out_text

    def test_inplace_and_output_mutually_exclusive(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "in.toml"
        out_p = tmp_path / "out.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=out_p, in_place=True),
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "mutually exclusive" in captured.err

    def test_neither_inplace_nor_output_rejected(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "in.toml"
        in_p.write_text(V1_BASIC, encoding="utf-8")
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=None, in_place=False),
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "must specify" in captured.err

    def test_input_not_found(
            self, tmp_path: Path, capsys) -> None:
        in_p = tmp_path / "missing.toml"
        rc = cmd_prices_upgrade(
            _make_args(in_p, output=tmp_path / "out.toml"),
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_round_trip_with_eur_currency(
            self, tmp_path: Path) -> None:
        body = dedent("""\
            _schema_version = "1.0"
            _currency = "EUR"

            [models."mistral-large-2"]
            provider = "mistral"
            pricing_model = "per_token"
            input_per_1m_usd = "2.00"
            output_per_1m_usd = "6.00"
            verified_date = "2026-04-28"
        """)
        in_p = tmp_path / "eur.toml"
        out_p = tmp_path / "eur_v2.toml"
        in_p.write_text(body, encoding="utf-8")
        rc = cmd_prices_upgrade(_make_args(in_p, output=out_p))
        assert rc == 0
        data = tomllib.loads(out_p.read_text(encoding="utf-8"))
        assert data["_currency"] == "EUR"
        assert data["_schema_version"] == "2.0"
        assert (
            data["models"]["mistral-large-2"]["input_per_1m"]
            == "2.00"
        )

    def test_field_rename_map_is_complete(self) -> None:
        """Sanity check: the renames must match pricing module."""
        from pricing import _V1_TO_V2_FIELD_MAP
        assert _V1_TO_V2_FIELD_RENAMES == _V1_TO_V2_FIELD_MAP
