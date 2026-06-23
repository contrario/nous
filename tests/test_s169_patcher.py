"""Tests for the seeded patch-primitive: the delta-only ASCII gate.

Locks the S168 acceptance: grandfathered non-ASCII in an unchanged region is
permitted (the byte survives), while non-ASCII in the inserted or modified
region is refused with a typed error and no writes. Also asserts the module is
import-side-effect-free so consuming patches inherit a clean primitive.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tools.patcher import (
    AsciiGateError,
    PatchPrimitiveError,
    _require_ascii_inserted,
)

EM_DASH = "\u2014"
E_ACUTE = "\u00e9"
GRANDFATHERED_PREFIX = "title " + EM_DASH + " body\n"


def test_grandfathered_unchanged_prefix_byte_is_permitted_and_survives() -> None:
    original = GRANDFATHERED_PREFIX + "value = 1\n"
    candidate = GRANDFATHERED_PREFIX + "value = 2\n"
    _require_ascii_inserted(original, candidate)
    assert EM_DASH in candidate


def test_grandfathered_byte_in_unchanged_suffix_is_permitted() -> None:
    original = "value = 1\n" + GRANDFATHERED_PREFIX
    candidate = "value = 2\n" + GRANDFATHERED_PREFIX
    _require_ascii_inserted(original, candidate)
    assert EM_DASH in candidate


def test_inserted_nonascii_is_refused() -> None:
    original = "value = 1\n"
    candidate = "value = " + E_ACUTE + "\n"
    with pytest.raises(AsciiGateError) as excinfo:
        _require_ascii_inserted(original, candidate)
    assert str(excinfo.value).startswith("non-ASCII character")


def test_nonascii_in_modified_window_is_refused() -> None:
    original = GRANDFATHERED_PREFIX + "value = 1\n"
    candidate = GRANDFATHERED_PREFIX + "value = " + E_ACUTE + "\n"
    with pytest.raises(AsciiGateError):
        _require_ascii_inserted(original, candidate)


def test_append_only_ascii_tail_passes() -> None:
    original = "line one\n"
    candidate = "line one\nline two\n"
    _require_ascii_inserted(original, candidate)


def test_new_file_ascii_whole_content_passes() -> None:
    _require_ascii_inserted("", "line one\nline two\n")


def test_new_file_nonascii_whole_content_refused() -> None:
    with pytest.raises(AsciiGateError):
        _require_ascii_inserted("", "header " + EM_DASH + "\n")


def test_identical_text_is_a_noop() -> None:
    text = GRANDFATHERED_PREFIX + "value = 1\n"
    _require_ascii_inserted(text, text)


def test_error_type_hierarchy() -> None:
    assert issubclass(AsciiGateError, PatchPrimitiveError)
    assert issubclass(PatchPrimitiveError, Exception)


def test_tools_package_resolves_to_ours() -> None:
    import tools

    assert os.path.basename(tools.__file__) == "__init__.py"
    from tools import patcher

    assert hasattr(patcher, "_require_ascii_inserted")


def test_module_import_is_side_effect_free() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probe = (
        "import sys, os, tempfile\n"
        "repo = os.environ['NOUS_REPO']\n"
        "sys.path.insert(0, repo)\n"
        "d = tempfile.mkdtemp()\n"
        "os.chdir(d)\n"
        "baseline = list(sys.path)\n"
        "import tools.patcher\n"
        "assert sys.path == baseline, 'import mutated sys.path'\n"
        "assert os.listdir(d) == [], 'import wrote to cwd'\n"
        "print('OK')\n"
    )
    env = dict(os.environ)
    env["NOUS_REPO"] = repo_root
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
