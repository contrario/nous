"""
tests/test_s358_skill_chain_e2e.py

The documented workflow, end to end, in-process.

`nous skill-export` emits a SKILL.md that instructs the reader to run
`nous dossier-spec` on the directory. No test covered that chain:
tests/test_dossier_spec_cli.py exercises build_dossier_spec over fixtures
whose models resolve, and tests/test_cli_skill_export.py stops at the
export. The suite was green while the shipped, documented path refused.

TWO PRECONDITIONS, BOTH MEASURED RATHER THAN ASSUMED:

  1. skill-export refuses a world with no cost law ("cannot derive
     cost_cap"). Only 4 of the 12 shipped templates declare one, so the
     chain is reachable from those 4 alone -- and all 4 carry the same
     unpriceable model, which is why the defect is total on the reachable
     surface rather than partial.
  2. dossier-spec requires the skill directory name to equal the SKILL.md
     name (agentskills.io spec). Renaming the directory converts the
     pricing refusal into a name refusal and silently stops reproducing
     the defect.

THE CONTROL IS SYNTHETIC BY NECESSITY. No shipped template both exports
and prices, so a green control has to be built here. It isolates chain
machinery from the pricing defect: if the control fails, the diagnosis is
the harness, not the table.

The assertion is that the chain COMPLETES. A REFUTED cost verdict is a
sound outcome; a refusal that emits nothing is not.

# __s358_skill_chain_e2e_v1__
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import pytest

from cli_skill_export import cmd_skill_export
from dossier_spec import DossierSpecError, DossierSpecResult, build_dossier_spec

_SKILL_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"^SKILL_NAME:[ \t]*(\S+)[ \t]*$",
    re.MULTILINE,
)

CAP_OVERRIDE: str = "0.50USD"

PRICEABLE_SOURCE: str = """world ChainControl {
    law cost_ceiling = $3.00 per cycle
    heartbeat = 20s
}
soul Scanner {
    mind: claude-sonnet-4-6 @ Tier1
    senses: [http_get]
    memory { count: int = 0 }
}
"""

SHIPPED_EXPORTABLE: str = "market_monitor.nous"


def _repo_root() -> Path:
    here: Path = Path(__file__).resolve()
    candidates: list[Path] = [here.parent, *here.parents, Path.cwd().resolve()]
    for base in candidates:
        if (base / "pricing" / "defaults.toml").is_file() and (base / "templates").is_dir():
            return base
    raise RuntimeError(
        "repo root not found: no ancestor of this file and not the working "
        "directory carries both pricing/defaults.toml and templates/"
    )


def _template(name: str) -> Path:
    path: Path = _repo_root() / "templates" / name
    if not path.is_file():
        raise RuntimeError(f"shipped template missing: {path}")
    return path


def _synthetic_source(tmp_path: Path) -> Path:
    path: Path = tmp_path / "chain_control.nous"
    path.write_text(PRICEABLE_SOURCE, encoding="utf-8")
    return path


def _export_namespace(source: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        input=str(source),
        description="s358 chain coverage",
        output=str(output),
        name=None,
        license=None,
        compatibility=None,
    )


def _export(
    source: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, str]:
    export_dir: Path = tmp_path / "export"
    rc: int = cmd_skill_export(_export_namespace(source, export_dir))
    captured = capsys.readouterr()
    if rc != 0:
        pytest.fail(
            f"skill-export returned {rc} for {source.name}; "
            f"stdout={captured.out!r} stderr={captured.err!r}"
        )
    match = _SKILL_NAME_PATTERN.search(captured.out)
    if match is None:
        pytest.fail(
            f"skill-export reported no SKILL_NAME for {source.name}; "
            f"stdout={captured.out!r} stderr={captured.err!r}"
        )
    skill_md: Path = export_dir / "SKILL.md"
    nous_yaml: Path = export_dir / "nous.yaml"
    for emitted in (skill_md, nous_yaml):
        if not emitted.is_file():
            pytest.fail(f"skill-export did not emit {emitted.name}")
    return export_dir, match.group(1)


def _stage(export_dir: Path, directory_name: str, tmp_path: Path) -> Path:
    staged: Path = tmp_path / "staged" / directory_name
    staged.mkdir(parents=True)
    for name in ("SKILL.md", "nous.yaml"):
        shutil.copy2(export_dir / name, staged / name)
    return staged


def _run_chain(source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> DossierSpecResult:
    export_dir, skill_name = _export(source, tmp_path, capsys)
    staged: Path = _stage(export_dir, skill_name, tmp_path)
    return build_dossier_spec(
        staged,
        cap_override=CAP_OVERRIDE,
        output=tmp_path / "dossier",
        key_path=tmp_path / "signing.key",
    )


def test_chain_completes_for_a_priceable_world(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_chain(_synthetic_source(tmp_path), tmp_path, capsys)
    assert isinstance(result, DossierSpecResult)


def test_chain_completes_for_a_shipped_exportable_template(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_chain(_template(SHIPPED_EXPORTABLE), tmp_path, capsys)
    assert isinstance(result, DossierSpecResult)


def test_exported_sidecar_default_model_is_priceable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pricing import load_pricing

    export_dir, _ = _export(_template(SHIPPED_EXPORTABLE), tmp_path, capsys)
    sidecar: str = (export_dir / "nous.yaml").read_text(encoding="utf-8")
    match = re.search(r"^default_model:[ \t]*(\S+)[ \t]*$", sidecar, re.MULTILINE)
    if match is None:
        pytest.fail(f"exported nous.yaml declares no default_model: {sidecar!r}")
    model: str = match.group(1)
    load_pricing().resolve(model)


def test_dossier_spec_refuses_when_directory_name_differs_from_skill_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    export_dir, skill_name = _export(_synthetic_source(tmp_path), tmp_path, capsys)
    mismatched: Path = _stage(export_dir, f"{skill_name}-renamed", tmp_path)
    with pytest.raises(DossierSpecError) as excinfo:
        build_dossier_spec(
            mismatched,
            cap_override=CAP_OVERRIDE,
            output=tmp_path / "dossier",
            key_path=tmp_path / "signing.key",
        )
    assert skill_name in str(excinfo.value)
