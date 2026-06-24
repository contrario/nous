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


def test_build_dossier_spec_proven_emits_cost_leg_and_reproves(  # __s175_g2_cost_leg_test_v1__
    tmp_path: Path,
) -> None:
    import hashlib as _hashlib
    import json as _json
    import subprocess
    import sys as _sys
    out = tmp_path / "out"
    result = build_dossier_spec(
        FIXTURES / "minimal",
        cap_override="0.50USD",
        output=out,
        key_path=_isolated_key(tmp_path),
    )
    assert result.verdict == "proven"
    assert "cost.farkas.json" in result.files
    cost_path = out / "cost.farkas.json"
    assert cost_path.is_file()
    manifest = _json.loads(
        (out / "manifest.json").read_text(encoding="utf-8")
    )
    cost_sha = manifest.get("cost_farkas_sha256")
    assert cost_sha is not None
    assert (
        _hashlib.sha256(cost_path.read_bytes()).hexdigest() == cost_sha
    )
    proc = subprocess.run(
        [_sys.executable, str(out / "verify_offline.py")],
        capture_output=True,
        text=True,
        cwd=str(out),
    )
    assert proc.returncode == 0, proc.stderr
    assert "cost-cap Farkas certificate PROVEN offline" in proc.stdout


def test_build_dossier_spec_refuted_omits_cost_leg(  # __s175_g2_cost_leg_test_v1__
    tmp_path: Path,
) -> None:
    import json as _json
    out = tmp_path / "out"
    result = build_dossier_spec(
        FIXTURES / "basic",
        cap_override="0.50USD",
        output=out,
        key_path=_isolated_key(tmp_path),
    )
    assert result.verdict == "refuted"
    assert "cost.farkas.json" not in result.files
    assert not (out / "cost.farkas.json").exists()
    manifest = _json.loads(
        (out / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.get("cost_farkas_sha256") is None


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
    expected = {  # __s112_dossier_cli_nine_set_v1__
        "source.nous",
        "manifest.json",
        "SKILL.md",
        "nous.yaml",
        "pricing.toml",
        "pricing.canonical.json",
        "public_key.b64",
        "README.md",
        "verify_offline.py",
    }
    assert set(result.files) == expected
    for f in expected:
        assert (tmp_path / "out" / f).is_file()
    import hashlib as _hashlib  # __s112_dossier_cli_recompute_v1__
    import json as _json
    _manifest = _json.loads(
        (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    _canon = (tmp_path / "out" / "pricing.canonical.json").read_bytes()
    assert (
        _hashlib.sha256(_canon).hexdigest()
        == _manifest["pricing_sha256"]
    ), "shipped pricing.canonical.json must recompute to manifest hash"


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
