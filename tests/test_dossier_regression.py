"""
Regression guard: existing `nous dossier` subcommand must keep working
after S77 wiring in cli.py (3-anchor str_replace patch).

This complements tests/test_dossier.py by exercising the CLI dispatch
path end-to-end, ensuring the wiring patch did not break cmd_dossier.
# __session77_skill_md_tests_v2__
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cli
from cli_verify import cmd_verify
from cli_dossier import cmd_dossier

TEMPLATE = (
    Path(__file__).parent.parent
    / "templates"
    / "cost_cap_with_souls.nous"
)


def test_cli_dispatch_still_has_dossier_command() -> None:
    """The cli module must still expose cmd_dossier after wiring."""
    assert hasattr(cli, "cmd_dossier")
    assert callable(cli.cmd_dossier)
    assert hasattr(cli, "build_dossier_parser")
    assert callable(cli.build_dossier_parser)


def test_cmd_dossier_still_emits_expected_files(tmp_path: Path) -> None:
    """Run cmd_dossier on the canonical template post-S77."""
    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)

    verify_args = argparse.Namespace(
        file=str(src),
        smt=True,
        prices=None,
        timeout_ms=30000,
        no_manifest=False,
        manifest_out=None,
        key_path=str(tmp_path / "signing.key"),
        smt_margin=0,
        no_lint=True,
        lint_strict=False,
        lint_error_on=None,
    )

    rc = cmd_verify(verify_args)
    assert rc == 0
    assert src.with_suffix(".manifest.json").is_file()

    out_dir = tmp_path / "dossier_out"
    dossier_args = argparse.Namespace(
        file=str(src),
        format="annex_iv",
        manifest=None,
        prices=None,
        output=str(out_dir),
    )

    rc = cmd_dossier(dossier_args)
    assert rc == 0
    expected = {
        "source.nous", "manifest.json", "pricing.toml",
        "public_key.b64", "README.md", "verify_offline.py",
    }
    actual = {p.name for p in out_dir.iterdir()}
    assert expected.issubset(actual)
