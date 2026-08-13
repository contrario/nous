"""S316 V1-V3b: phase_pytest decides on the exit state before it reads
the summary, and the two later predicates still decide.

scripts/ is not a package, so scripts/release.py is loaded by file path
in the shape of tests/test_s311_supersession_tool.py:33-38. The module
is NOT registered in sys.modules: scripts/release.py declares no
dataclass, measured in S316, so the FG-S314-G mechanism has no purchase
here, and a global name in sys.modules is the kind of cross-test
residue named by the open order-dependence finding from S312.

The floor is read from the module as PYTEST_FLOOR and never written as
a literal, so these tests do not move when the ratchet moves.

SET: phase_pytest as loaded from scripts/release.py.
SHAPE: the phase is driven through a stubbed run() returning a fixed
exit code and fixed streams. BLIND TO what pytest actually emits, to
whether any real invocation produces these inputs, to every other
phase, and to main().

The negative control removes the exit-state block from a copy of the
module source in memory, located by its marker and by indentation, and
requires V1's input to stop raising. It asserts what the removed text
contains, not how many lines it is: a dimensional assertion would make
one defect print two failures, and one mechanism carries one meaning
(D315-11). The file on disk is not touched.

__s316_p1_exit_state_tests_v1__
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RELEASE = _REPO / "scripts" / "release.py"
_MARKER = "__s316_p1_pytest_exit_state_v1__"


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _load_release():
    spec = importlib.util.spec_from_file_location("_s316_release", _RELEASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub(module, returncode: int, stdout: str, stderr: str = "") -> None:
    module.run = lambda *a, **k: _Result(returncode, stdout, stderr)


def _above(floor: int) -> str:
    return f"{floor + 110} passed, 12 skipped in 118s\n"


def _below(floor: int) -> str:
    return f"{floor - 100} passed in 12s\n"


def test_v1_non_zero_exit_with_passes_above_floor_aborts():
    """The uncovered case of D315-2: the code accepted this before P1."""
    module = _load_release()
    _stub(module, 1, _above(module.PYTEST_FLOOR), "traceback on stderr\n")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pytest()
    assert "exited 1" in str(exc.value)


def test_v1b_both_streams_are_printed_whole_on_the_abort(capsys):
    module = _load_release()
    _stub(module, 1, _above(module.PYTEST_FLOOR), "traceback on stderr\n")
    with pytest.raises(module.ReleaseError):
        module.phase_pytest()
    out = capsys.readouterr().out
    assert "traceback on stderr" in out
    assert str(module.PYTEST_FLOOR + 110) in out


def test_v2_zero_exit_with_passes_above_floor_returns():
    """The control. The ordinary green path is unchanged."""
    module = _load_release()
    _stub(module, 0, _above(module.PYTEST_FLOOR))
    assert module.phase_pytest() is None


def test_v3_zero_exit_below_floor_still_aborts_on_the_floor():
    """D315-5: no exit code encodes suite shrinkage."""
    module = _load_release()
    _stub(module, 0, _below(module.PYTEST_FLOOR))
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pytest()
    message = str(exc.value)
    assert "below floor" in message
    assert "exited" not in message


def test_v3b_zero_exit_without_the_word_passed_still_aborts():
    """The presence test still decides once rc is tested in front of it.

    This locks the code path. It does NOT evidence that any real pytest
    invocation produces rc 0 with a summary lacking the word; that is a
    separate and unmeasured question.
    """
    module = _load_release()
    _stub(module, 0, "12 skipped in 1s\n")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pytest()
    message = str(exc.value)
    assert "did not report any passes" in message
    assert "exited" not in message


def _module_without_the_guard() -> dict:
    lines = _RELEASE.read_text(encoding="utf-8").splitlines(True)
    heads = [i for i, line in enumerate(lines) if _MARKER in line]
    assert len(heads) == 1
    start = heads[0]
    end = start + 1
    while end < len(lines) and lines[end].startswith("        "):
        end += 1
    removed = "".join(lines[start:end])
    assert "result.returncode" in removed
    assert "raise ReleaseError" in removed
    kept = lines[:start] + lines[end:]
    namespace = {"__file__": str(_RELEASE), "__name__": "_s316_mutated"}
    exec("".join(kept), namespace)
    return namespace


def test_v1_negative_control_the_guard_is_what_raises():
    """Without the block, V1's input stops raising. In memory only."""
    namespace = _module_without_the_guard()
    floor = namespace["PYTEST_FLOOR"]
    namespace["run"] = lambda *a, **k: _Result(1, _above(floor), "x\n")
    assert namespace["phase_pytest"]() is None
