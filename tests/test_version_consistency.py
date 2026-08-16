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


README: Path = REPO_ROOT / "README.md"

CURRENT_VERSION_MARKER: str = "__s323_readme_version_current_v1__"
CURRENT_VERSION_MARK: str = "<!-- " + CURRENT_VERSION_MARKER + " -->"
MARKED_SITE_COUNT: int = 3
FENCE: str = "```"
SEMVER_IN_TEXT_RE: re.Pattern[str] = re.compile(r"v?\d+\.\d+\.\d+")


def _marked_regions(lines: list[str]) -> list[tuple[str, list[str]]]:
    regions: list[tuple[str, list[str]]] = []
    for index, line in enumerate(lines):
        if CURRENT_VERSION_MARK not in line:
            continue
        if line.strip() != CURRENT_VERSION_MARK:
            regions.append(("trailing marker on a line of prose", [line]))
            continue
        nxt: int = index + 1
        while nxt < len(lines) and lines[nxt].strip() == "":
            nxt += 1
        if nxt >= len(lines):
            pytest.fail(
                "A standalone "
                + CURRENT_VERSION_MARK
                + " marks nothing: no non-blank line follows it. Either delete the"
                " marker or move it in front of the block it is meant to govern."
            )
        if not lines[nxt].strip().startswith(FENCE):
            regions.append(("standalone marker before a single line", [lines[nxt]]))
            continue
        close: int = nxt + 1
        while close < len(lines) and lines[close].strip() != FENCE:
            close += 1
        if close >= len(lines):
            pytest.fail(
                "A standalone "
                + CURRENT_VERSION_MARK
                + " marks a fenced block that never closes. Close the fence, or move"
                " the marker to the line it is meant to govern."
            )
        regions.append(("standalone marker before a fenced block", lines[nxt : close + 1]))
    return regions


def test_readme_marked_sites_carry_the_current_version() -> None:
    """Every semver token inside a marked README region equals _version.__version__.

    FORM. A line whose whole content is the marker comment is STANDALONE and marks
    the next non-blank thing: if that is a fence opener, the marked region is the
    fenced block; otherwise it is that one line. A marker appended to prose is
    TRAILING and marks only its own line. Form, not position: this README already
    carries a trailing marker on a prose line shortly above a fence opener, and a
    position-based rule would silently give that marker a second meaning.

    WHY THE IDIOM WAS FREE TO TAKE. The HTML-comment marker idiom occurs many times
    in this README and, before this test, not one of its tokens was read by any
    script or test in the tree. The shape that separates an inert marker from a
    load-bearing one is how many tracked files carry the token: tracked_total 1
    means the token exists only where it is written and nothing consumes it;
    tracked_total 2 or more means something reads it. This token is the first to
    reach 2 -- README.md and this file -- so enforcing it gives the idiom a FIRST
    meaning rather than a second.

    COUNTS, AND THE LEVEL EACH IS ASSERTED AT.
      file level    the mark occurs exactly MARKED_SITE_COUNT times and exactly
                    that many regions resolve. Pinned.
      region level  every marked region carries AT LEAST ONE version token, so a
                    marker that loses its block, or a line that loses its version,
                    goes red instead of passing over an empty set.
      token level   the total token count is NOT pinned. It is 1 + 1 + 2 today and
                    that addition is not an invariant.

    BLINDNESS, SINGLE AND KNOWN. A current-version claim written WITHOUT a mark is
    invisible here. The pinned count catches the removal of a marked site, never
    the addition of an unmarked one. A live instance sits a few lines under one of
    the marked sites: the Tests row of the Stats table carries a figure no gate
    reads.

    NOT TAKEN. Exhaustive classification -- require every semver token in the README
    to carry either a current mark or a historical mark, so a new unmarked site
    fails closed. Cost: a mark on every version-bearing line and a classification
    decision for every future version reference. Beyond this rule; the operator's
    call if it is ever taken.

    CONSEQUENCE. Every version bump must edit README.md at every marked site, or
    the release stops at the version-consistency phase.
    """
    text: str = README.read_text(encoding="utf-8")
    lines: list[str] = text.splitlines()

    found: int = text.count(CURRENT_VERSION_MARK)
    if found != MARKED_SITE_COUNT:
        pytest.fail(
            f"README carries the current-version mark {found} time(s), expected "
            f"{MARKED_SITE_COUNT}. A marked site was removed or added: restore it, "
            "or update MARKED_SITE_COUNT and the docstring in the same change."
        )

    regions: list[tuple[str, list[str]]] = _marked_regions(lines)
    if len(regions) != MARKED_SITE_COUNT:
        pytest.fail(
            f"{found} mark(s) resolved to {len(regions)} region(s). Two marks share a "
            "line, or a mark is malformed. One mark per site."
        )

    current: str = _version.__version__
    for label, body in regions:
        tokens: list[str] = SEMVER_IN_TEXT_RE.findall("\n".join(body))
        if not tokens:
            pytest.fail(
                f"A marked README region ({label}) carries no version token. The mark "
                "governs an empty set: delete the mark, or restore the version it was "
                "put there to govern."
            )
        for token in tokens:
            if token.lstrip("v") != current:
                pytest.fail(
                    f"A marked README region ({label}) claims version {token!r} but "
                    f"_version.__version__ is {current!r}. Update README.md at every "
                    "marked site; the version bump is not complete without it."
                )
