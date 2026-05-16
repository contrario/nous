"""
End-to-end tests for `nous dossier-spec` via build_dossier_spec.
Each test uses an isolated tmp_path signing key to avoid polluting
the user's XDG keystore.
# __session77_skill_md_tests_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dossier_spec import (
    DossierSpecError,
    DossierSpecResult,
    build_dossier_spec,
)

FIXTURES = Path(__file__).parent / "skill_md_fixtures"


def _isolated_key(tmp_path: Path) -> Path:
    return tmp_path / "signing.key"


def test_build_dossier_spec_minimal_returns_result(
    tmp_path: Path,
) -> None:
    result = build_dossier_spec(
        FIXTURES / "minimal",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
    )
    assert isinstance(result, DossierSpecResult)
    assert result.output_dir == (tmp_path / "out").resolve()
    assert result.world_name == "minimal"


def test_build_dossier_spec_emits_eight_files(tmp_path: Path) -> None:
    result = build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
    )
    expected = {
        "source.nous",
        "manifest.json",
        "SKILL.md",
        "nous.yaml",
        "pricing.toml",
        "public_key.b64",
        "README.md",
        "verify_offline.py",
    }
    assert set(result.files) == expected
    for f in expected:
        assert (tmp_path / "out" / f).is_file()


def test_build_dossier_spec_cap_override_applied(tmp_path: Path) -> None:
    result = build_dossier_spec(
        FIXTURES / "basic",
        cap_override="999USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
    )
    assert result.verdict == "proven"


def test_build_dossier_spec_gbp_cap_rejected(tmp_path: Path) -> None:
    with pytest.raises(DossierSpecError, match="USD"):
        build_dossier_spec(
            FIXTURES / "basic",
            cap_override="0.50GBP",
            output=tmp_path / "out",
            key_path=_isolated_key(tmp_path),
        )


def test_build_dossier_spec_missing_skill_dir(tmp_path: Path) -> None:
    with pytest.raises(DossierSpecError):
        build_dossier_spec(
            tmp_path / "nonexistent_skill",
            cap_override="0.50USD",
            output=tmp_path / "out",
            key_path=_isolated_key(tmp_path),
        )


def test_build_dossier_spec_refuses_nonempty_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "stale").write_text("x")
    with pytest.raises(DossierSpecError, match="not empty"):
        build_dossier_spec(
            FIXTURES / "basic",
            cap_override="0.50USD",
            output=output,
            key_path=_isolated_key(tmp_path),
        )


def test_build_dossier_spec_envelope_contains_skill_md_and_yaml(
    tmp_path: Path,
) -> None:
    build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=tmp_path / "out",
        key_path=_isolated_key(tmp_path),
    )
    envelope = (tmp_path / "out" / "source.nous").read_bytes()
    assert b"BEGIN SKILL.md" in envelope
    assert b"END SKILL.md" in envelope
    assert b"BEGIN nous.yaml" in envelope
    assert b"END nous.yaml" in envelope
    assert b"# NOUS skill_md dossier source envelope v1" in envelope
