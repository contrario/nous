"""
tests/test_cli_skill_export.py

CLI surface coverage for `nous skill-export`. Exercises the cmd_skill_export
entrypoint with argparse.Namespace fixtures. No FastAPI, no subprocess.

# __session77_test_cli_skill_export_v1__
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from cli_skill_export import cmd_skill_export


def _ns(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "input": None,
        "description": "Test export",
        "output": None,
        "name": None,
        "license": None,
        "compatibility": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


SIMPLE_NOUS: str = """world MarketMonitor {
    law cost_ceiling = $3.00 per cycle
    heartbeat = 20s
}
soul Scanner {
    mind: claude-sonnet-4-6 @ Tier1
    senses: [http_get]
    memory { count: int = 0 }
}
"""


def test_cmd_writes_skill_md_and_nous_yaml(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    out = tmp_path / "out"
    rc = cmd_skill_export(
        _ns(input=str(src), output=str(out), description="demo")
    )
    assert rc == 0
    assert (out / "SKILL.md").is_file()
    assert (out / "nous.yaml").is_file()


def test_cmd_default_output_is_input_stem_skill(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    rc = cmd_skill_export(
        _ns(input=str(src), description="demo")
    )
    assert rc == 0
    assert (tmp_path / "demo.skill" / "SKILL.md").is_file()


def test_cmd_input_file_not_found(tmp_path: Path) -> None:
    rc = cmd_skill_export(
        _ns(
            input=str(tmp_path / "nonexistent.nous"),
            description="demo",
        )
    )
    assert rc == 1


def test_cmd_parse_failure_returns_nonzero(tmp_path: Path) -> None:
    src = tmp_path / "bad.nous"
    src.write_text("this is not valid nous", encoding="utf-8")
    rc = cmd_skill_export(
        _ns(input=str(src), description="demo")
    )
    assert rc == 1


def test_cmd_no_cost_law_returns_nonzero(tmp_path: Path) -> None:
    src = tmp_path / "nocost.nous"
    src.write_text(
        "world X {\n    heartbeat = 20s\n}\n"
        "soul S {\n    mind: m @ Tier1\n    senses: [t]\n}\n",
        encoding="utf-8",
    )
    rc = cmd_skill_export(
        _ns(input=str(src), description="demo")
    )
    assert rc == 1


def test_cmd_explicit_name_override(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    out = tmp_path / "out"
    rc = cmd_skill_export(
        _ns(
            input=str(src),
            output=str(out),
            name="my-explicit-name",
            description="demo",
        )
    )
    assert rc == 0
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "name: my-explicit-name" in md


def test_cmd_bad_explicit_name_returns_nonzero(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    rc = cmd_skill_export(
        _ns(
            input=str(src),
            output=str(tmp_path / "out"),
            name="BadName",
            description="demo",
        )
    )
    assert rc == 1


def test_cmd_license_and_compatibility_propagate(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    out = tmp_path / "out"
    rc = cmd_skill_export(
        _ns(
            input=str(src),
            output=str(out),
            description="demo",
            license="MIT",
            compatibility=">=3.11",
        )
    )
    assert rc == 0
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "license: MIT" in md
    assert 'compatibility: ">=3.11"' in md


def test_cmd_empty_description_returns_nonzero(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    rc = cmd_skill_export(
        _ns(input=str(src), description="")
    )
    assert rc == 1


def test_cmd_creates_missing_output_dir(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    out = tmp_path / "nested" / "deeply" / "out"
    rc = cmd_skill_export(
        _ns(input=str(src), output=str(out), description="demo")
    )
    assert rc == 0
    assert (out / "SKILL.md").is_file()


def test_cmd_atomic_write_replaces_existing(tmp_path: Path) -> None:
    src = tmp_path / "demo.nous"
    src.write_text(SIMPLE_NOUS, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "SKILL.md").write_text("old content", encoding="utf-8")
    rc = cmd_skill_export(
        _ns(input=str(src), output=str(out), description="demo")
    )
    assert rc == 0
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "old content" not in md
    assert "name: market-monitor" in md
