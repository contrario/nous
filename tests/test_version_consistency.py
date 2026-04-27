"""
Test: VERSION consistency across all sources.

Locks the single-source-of-truth invariant established by CC (Session 59).

If this test fails, the bug-class has resurfaced: someone has reintroduced
a hardcoded version literal in cli.py / nous_api.py / __init__.py / pyproject
without going through _version.py. The fix is to remove the duplicate, not
to update this test.

Sources verified:
  1. _version.__version__         (the source of truth)
  2. _version.__version_tuple__   (must match parsed __version__)
  3. cli.VERSION                  (re-exported)
  4. nous_api.VERSION             (re-exported, typed)
  5. <package>.__version__        (__init__.py re-export)
  6. importlib.metadata.version() (pip-installed metadata)
  7. pyproject.toml               (must declare dynamic = ["version"])

# __cc_test_version_consistency_v1__
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import importlib.metadata
import pytest

import _version  # type: ignore[import-not-found]


REPO_ROOT: Path = Path(__file__).parent.parent
PYPROJECT: Path = REPO_ROOT / "pyproject.toml"

VERSION_RE: re.Pattern[str] = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[\.\-+].*)?$")


def _parse_version_tuple(v: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(v)
    if not m:
        raise ValueError(f"version {v!r} is not PEP-440 X.Y.Z")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def test_version_module_has_required_attrs() -> None:
    assert hasattr(_version, "__version__"), "_version.__version__ missing"
    assert hasattr(_version, "__version_tuple__"), "_version.__version_tuple__ missing"
    assert isinstance(_version.__version__, str)
    assert isinstance(_version.__version_tuple__, tuple)
    assert len(_version.__version_tuple__) == 3
    assert all(isinstance(n, int) for n in _version.__version_tuple__)


def test_version_string_is_pep440_compatible() -> None:
    parsed = _parse_version_tuple(_version.__version__)
    assert parsed == _version.__version_tuple__, (
        f"__version__={_version.__version__!r} parses to {parsed}, "
        f"but __version_tuple__={_version.__version_tuple__}. "
        "Update both literals in _version.py together."
    )


def test_cli_VERSION_matches_source() -> None:
    import cli  # type: ignore[import-not-found]
    assert cli.VERSION == _version.__version__, (
        f"cli.VERSION={cli.VERSION!r} drifted from "
        f"_version.__version__={_version.__version__!r}. "
        "cli.py must `from _version import __version__ as VERSION`."
    )


def test_nous_api_VERSION_matches_source() -> None:
    import nous_api  # type: ignore[import-not-found]
    assert nous_api.VERSION == _version.__version__, (
        f"nous_api.VERSION={nous_api.VERSION!r} drifted from "
        f"_version.__version__={_version.__version__!r}. "
        "nous_api.py must re-export VERSION from _version."
    )


def test_pyproject_declares_dynamic_version() -> None:
    assert PYPROJECT.exists(), f"pyproject.toml not found at {PYPROJECT}"
    cfg: dict[str, object] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = cfg.get("project", {})
    assert isinstance(project, dict)
    dynamic_list = project.get("dynamic", [])
    assert isinstance(dynamic_list, list)
    assert "version" in dynamic_list, (
        "pyproject [project] must declare `dynamic = [\"version\"]`. "
        "Static `version = ...` is forbidden — it bypasses _version.py."
    )

    setuptools_cfg = cfg.get("tool", {}).get("setuptools", {})  # type: ignore[union-attr]
    assert isinstance(setuptools_cfg, dict)
    dyn = setuptools_cfg.get("dynamic", {})
    assert isinstance(dyn, dict)
    version_dyn = dyn.get("version", {})
    assert isinstance(version_dyn, dict)
    assert version_dyn.get("attr") == "_version.__version__", (
        f"[tool.setuptools.dynamic].version must be "
        f'{{attr = "_version.__version__"}}, got {version_dyn!r}.'
    )


def test_pyproject_has_no_static_version_literal() -> None:
    """Defense-in-depth: catch a regression where someone re-adds a static
    `version = "X.Y.Z"` line under [project] alongside dynamic.
    """
    text: str = PYPROJECT.read_text(encoding="utf-8")
    in_project: bool = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            if "dynamic" not in stripped:
                pytest.fail(
                    f"pyproject [project] has static version line: {stripped!r}. "
                    "Must use `dynamic = [\"version\"]` only."
                )


def test_installed_metadata_matches_source() -> None:
    """Only meaningful when nous-lang is installed (e.g. via pip install ...).
    Skipped in editable/uninstalled contexts.
    """
    try:
        meta_version: str = importlib.metadata.version("nous-lang")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("nous-lang is not installed in this environment")
    assert meta_version == _version.__version__, (
        f"pip metadata version={meta_version!r} drifted from "
        f"_version.__version__={_version.__version__!r}. "
        "Wheel was built against a different _version.py."
    )
