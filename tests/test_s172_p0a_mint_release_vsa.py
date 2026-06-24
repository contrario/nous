"""
S172 P0(a) -- release-VSA MINT tool repo placement guard.

mint_release_vsa.py is now a committed top-level module (Rule 9: declared in
pyproject.toml py-modules AND scripts/release.py wheel-gate `required`). This
test enforces, at pytest time:

  1. Module placement + public surface (it imports and exposes the mint API).
  2. The _root1_self_verify cosmetic fix (no unconditional stderr forward on
     the expected rc==2 ROOT-1 PASS path).
  3. Rule 9 dual-registration (mint_release_vsa in py-modules AND wheel gate).
  4. Release-VSA drift guard: every shipped tag at or above the first
     published release-VSA version (5.60.1) has a published
     website/.well-known/nous/release-vsa/<ver>/ directory OR an explicit
     waiver recorded here. As each anchor/backfill lands, its version moves
     from the waiver set to a published directory in the SAME patch; a
     companion test fails if a waived version gains a directory, forcing the
     waiver to be removed.

# __s172_p0a_test_mint_release_vsa_v1__
"""
from __future__ import annotations

import ast
import subprocess
import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO / "pyproject.toml"
_RELEASE = _REPO / "scripts" / "release.py"
_RELEASE_VSA_DIR = _REPO / "website" / ".well-known" / "nous" / "release-vsa"

_RELEASE_VSA_FLOOR = (5, 60, 1)
_RELEASE_VSA_WAIVERS = frozenset({"5.65.0"})  # __s174_waiver_5650_twine_no_federation__  # __s173_p0d_anchor_5610_dewaiver__


def _pyproject_py_modules() -> set[str]:
    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    return {str(m) for m in data["tool"]["setuptools"]["py-modules"]}


def _wheel_gate_py_stems() -> set[str]:
    tree = ast.parse(_RELEASE.read_text(encoding="utf-8"))
    stems: set[str] = set()
    for node in ast.walk(tree):
        target_name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target_name = node.targets[0].id
            value = node.value
        if target_name != "required" or not isinstance(value, ast.List):
            continue
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                if elt.value.endswith(".py"):
                    stems.add(elt.value[:-3])
    return stems


def _parse_version(tag: str) -> tuple[int, int, int] | None:
    raw = tag[1:] if tag.startswith("v") else tag
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def test_mint_release_vsa_importable_surface() -> None:
    import mint_release_vsa

    for name in ("mint", "build_arg_parser", "main", "MintError", "_root1_self_verify"):
        assert hasattr(mint_release_vsa, name), "missing public symbol: " + name
    assert mint_release_vsa.REPOSITORY == "contrario/nous"
    assert (
        mint_release_vsa.COMMITTED_RELEASE_PIN_B64
        == "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="
    )


def test_mint_release_vsa_root1_stderr_suppressed() -> None:
    import mint_release_vsa

    src = Path(mint_release_vsa.__file__).read_text(encoding="utf-8")
    assert "__s172_p0a_root1_stderr_suppress_v1__" in src
    assert "if result.stderr and not is_root1_pass:" in src
    assert "    if result.stderr:\n        sys.stderr.write(result.stderr)\n" not in src


def test_mint_release_vsa_rule9_dual_registered() -> None:
    assert "mint_release_vsa" in _pyproject_py_modules()
    assert "mint_release_vsa" in _wheel_gate_py_stems()


@pytest.mark.skipif(
    not (_REPO / ".git").exists(),
    reason="release-VSA drift guard needs a git checkout to enumerate shipped tags",
)
def test_release_vsa_no_unwaived_drift() -> None:
    proc = subprocess.run(
        ["git", "tag", "-l", "v*.*.*"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, "git tag enumeration failed: " + proc.stderr
    missing: list[str] = []
    for line in proc.stdout.splitlines():
        tag = line.strip()
        ver = _parse_version(tag)
        if ver is None or ver < _RELEASE_VSA_FLOOR:
            continue
        version = tag[1:] if tag.startswith("v") else tag
        if (_RELEASE_VSA_DIR / version).is_dir():
            continue
        if version in _RELEASE_VSA_WAIVERS:
            continue
        missing.append(version)
    assert not missing, (
        "shipped tags at/above 5.60.1 lack a release-vsa dir and an explicit "
        "waiver (anchor them or add a waiver): " + ", ".join(sorted(missing))
    )


def test_release_vsa_waivers_have_no_published_dir() -> None:
    stale: list[str] = []
    for version in sorted(_RELEASE_VSA_WAIVERS):
        if (_RELEASE_VSA_DIR / version).is_dir():
            stale.append(version)
    assert not stale, (
        "waived versions now have a published release-vsa dir; remove them "
        "from _RELEASE_VSA_WAIVERS in the same patch as the anchor: "
        + ", ".join(stale)
    )
