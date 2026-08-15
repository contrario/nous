"""S319 gate B: phase_preflight decides on the exit state at both of
its git call sites, and everything downstream of them still decides.

scripts/ is not a package, so scripts/release.py is loaded by file path
in the shape of tests/test_s316_release_exit_state.py:48-53. The module
is NOT registered in sys.modules, for the reason measured in S316:
release.py declares no dataclass, so the FG-S314-G mechanism has no
purchase, and a global name in sys.modules is the residue named by the
open order-dependence finding from S312.

THE SEAM IS module.run AND THAT IS MEASURED, NOT INHERITED. Both call
sites, at release.py:139 and release.py:158, reach the subprocess
through run(). This file therefore composes from the S316 tests and NOT
from the S317 file, whose seam is module.subprocess because
phase_pyflakes calls it directly. FG-S317-A names the error of
borrowing the wrong seam.

phase_preflight calls run() up to four times in one invocation, so a
single lambda cannot express "this call fails and that one does not".
The stub dispatches on the git subcommand, which also makes each test
say which command it is characterising.

THE DEFAULT BRANCH RAISES AND DOES NOT RETURN SUCCESS. A stub that
answers an unstubbed subcommand with a green result would keep these
tests passing over a phase that had grown a new git call, which is the
D315-12 blindness reproduced inside the test written against it.

SET: phase_preflight as loaded from scripts/release.py.
SHAPE: the phase is driven through a stubbed run() returning fixed exit
codes and fixed streams per git subcommand.

BLIND TO: what git actually emits for any real repository; whether any
real invocation produces these combinations; which of the two
indistinguishable causes produced a non-zero exit, that being exactly
the distinction D318-7 measured to be unavailable; the import of
_version at release.py:131, which is left real; every other phase; and
main().

__s319_a_exit_state_tests_v1__
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RELEASE = _REPO / "scripts" / "release.py"
_MARKER_A = "__s319_a1_preflight_status_exit_state_v1__"
_MARKER_B = "__s319_a2_preflight_tag_exit_state_v1__"

_FAILED = "fatal: not a git repository (or any of the parent directories)"


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _load_release():
    spec = importlib.util.spec_from_file_location("_s319_release", _RELEASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dispatch(status, tag):
    def _run(cmd, *args, **kwargs):
        if list(cmd[:2]) == ["git", "status"]:
            return _Result(*status)
        if list(cmd[:2]) == ["git", "tag"]:
            return _Result(*tag)
        raise AssertionError("unstubbed git call: " + " ".join(cmd))

    return _run


def _stub(module, status=(0, "", ""), tag=(0, "", "")) -> None:
    module.run = _dispatch(status, tag)


def test_v1_status_non_zero_exit_aborts():
    """D318-2: a failed git and a clean tree are the same on stdout."""
    module = _load_release()
    _stub(module, status=(128, "", _FAILED))
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_preflight()
    assert "working-tree check did not complete" in str(exc.value)


def test_v1b_status_abort_prints_both_streams(capsys):
    module = _load_release()
    _stub(module, status=(128, "partial stdout", _FAILED))
    with pytest.raises(module.ReleaseError):
        module.phase_preflight()
    out = capsys.readouterr().out
    assert _FAILED in out
    assert "partial stdout" in out


def test_v2_tag_non_zero_exit_aborts():
    """D318-2: a failed git and an absent tag are the same on stdout."""
    module = _load_release()
    _stub(module, tag=(128, "", _FAILED))
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_preflight()
    assert "tag lookup did not complete" in str(exc.value)


def test_v2b_tag_abort_prints_both_streams(capsys):
    module = _load_release()
    _stub(module, tag=(128, "partial stdout", _FAILED))
    with pytest.raises(module.ReleaseError):
        module.phase_preflight()
    out = capsys.readouterr().out
    assert _FAILED in out
    assert "partial stdout" in out


def test_v3_both_zero_returns_the_version():
    """The control. The ordinary green path is unchanged."""
    module = _load_release()
    _stub(module)
    version = module.phase_preflight()
    assert isinstance(version, str) and version


def test_v4_dirty_tree_still_aborts_on_its_own_message():
    """The guard did not widen. A clean exit with output still decides."""
    module = _load_release()
    _stub(module, status=(0, "?? untracked_thing\n", ""))
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_preflight()
    message = str(exc.value)
    assert "working tree not clean" in message
    assert "did not complete" not in message


def test_v5_present_tag_still_aborts_on_its_own_message():
    """The second guard did not widen either."""
    module = _load_release()
    _stub(module)
    version = module.phase_preflight()
    module._ALLOW_EXISTING_TAG = False
    _stub(module, tag=(0, "v" + version, ""))
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_preflight()
    message = str(exc.value)
    assert "already exists" in message
    assert "did not complete" not in message


def _module_without(marker: str) -> dict:
    lines = _RELEASE.read_text(encoding="utf-8").splitlines(True)
    heads = [i for i, line in enumerate(lines) if marker in line]
    assert len(heads) == 1
    start = heads[0]
    end = start + 1
    while end < len(lines) and lines[end].startswith("        "):
        end += 1
    removed = "".join(lines[start:end])
    assert "returncode" in removed
    assert "raise ReleaseError" in removed
    kept = lines[:start] + lines[end:]
    namespace = {"__file__": str(_RELEASE), "__name__": "_s319_mutated"}
    exec("".join(kept), namespace)
    return namespace


def test_v1_negative_control_the_first_guard_is_what_raises():
    """Without block A, V1's input stops raising. In memory only."""
    namespace = _module_without(_MARKER_A)
    namespace["run"] = _dispatch((128, "", _FAILED), (0, "", ""))
    assert isinstance(namespace["phase_preflight"](), str)


def test_v2_negative_control_the_second_guard_is_what_raises():
    """Without block B, V2's input stops raising. In memory only."""
    namespace = _module_without(_MARKER_B)
    namespace["run"] = _dispatch((0, "", ""), (128, "", _FAILED))
    assert isinstance(namespace["phase_preflight"](), str)
