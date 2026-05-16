"""
Tests for skill_md.py parser layer (file I/O + frontmatter).
# __session77_skill_md_tests_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skill_md import (
    ParsedSkill,
    SkillMDError,
    parse_sidecar_file,
    parse_skill_dir,
    parse_skill_md_file,
)

FIXTURES = Path(__file__).parent / "skill_md_fixtures"


def test_parse_skill_dir_minimal_happy_path() -> None:
    ps = parse_skill_dir(FIXTURES / "minimal")
    assert isinstance(ps, ParsedSkill)
    assert ps.frontmatter.name == "minimal"
    assert len(ps.sidecar.tools) == 1


def test_parse_skill_dir_basic_canonical() -> None:
    ps = parse_skill_dir(FIXTURES / "basic")
    assert ps.frontmatter.name == "basic"
    assert len(ps.sidecar.tools) == 2
    assert ps.sidecar.cost_cap.currency == "USD"


def test_parse_skill_md_file_requires_path_not_str() -> None:
    with pytest.raises((TypeError, SkillMDError)):
        parse_skill_md_file(str(FIXTURES / "minimal" / "SKILL.md"))


def test_parse_sidecar_file_requires_path_not_str() -> None:
    with pytest.raises((TypeError, SkillMDError)):
        parse_sidecar_file(str(FIXTURES / "minimal" / "nous.yaml"))


def test_parse_skill_dir_rejects_str() -> None:
    with pytest.raises((TypeError, SkillMDError)):
        parse_skill_dir(str(FIXTURES / "minimal"))


def test_parse_skill_dir_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(SkillMDError):
        parse_skill_dir(tmp_path / "does_not_exist")


def test_parse_skill_dir_missing_sidecar_raises(tmp_path: Path) -> None:
    d = tmp_path / "no_sidecar"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: no_sidecar\ndescription: x\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillMDError):
        parse_skill_dir(d)


def test_parse_skill_dir_missing_skill_md_raises(tmp_path: Path) -> None:
    d = tmp_path / "no_skill_md"
    d.mkdir()
    (d / "nous.yaml").write_text(
        'spec_version: "1.0"\n'
        "cost_cap: 0.50USD\n"
        "default_model: claude-haiku-4-5\n"
        "tools:\n"
        "  - name: t\n"
        "    max_calls: 1\n"
        "    input_tokens: 10\n"
        "    output_tokens: 10\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillMDError):
        parse_skill_dir(d)


def test_parse_skill_md_no_opening_delim(tmp_path: Path) -> None:
    d = tmp_path / "no_delim"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    (d / "nous.yaml").write_text(
        'spec_version: "1.0"\ncost_cap: 0.50USD\n'
        "default_model: claude-haiku-4-5\n"
        "tools:\n  - name: t\n    max_calls: 1\n"
        "    input_tokens: 10\n    output_tokens: 10\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillMDError):
        parse_skill_dir(d)


def test_parse_skill_md_unclosed_frontmatter(tmp_path: Path) -> None:
    d = tmp_path / "unclosed"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: unclosed\ndescription: x\n",
        encoding="utf-8",
    )
    (d / "nous.yaml").write_text(
        'spec_version: "1.0"\ncost_cap: 0.50USD\n'
        "default_model: claude-haiku-4-5\n"
        "tools:\n  - name: t\n    max_calls: 1\n"
        "    input_tokens: 10\n    output_tokens: 10\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillMDError):
        parse_skill_dir(d)


def test_parse_skill_dir_name_dir_mismatch(tmp_path: Path) -> None:
    d = tmp_path / "wrong-dirname"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: other-name\ndescription: x\n---\nbody\n",
        encoding="utf-8",
    )
    (d / "nous.yaml").write_text(
        'spec_version: "1.0"\ncost_cap: 0.50USD\n'
        "default_model: claude-haiku-4-5\n"
        "tools:\n  - name: t\n    max_calls: 1\n"
        "    input_tokens: 10\n    output_tokens: 10\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillMDError):
        parse_skill_dir(d)


def test_parse_skill_dir_missing_nous_block_fixture() -> None:
    with pytest.raises(SkillMDError):
        parse_skill_dir(FIXTURES / "missing-nous-block")
