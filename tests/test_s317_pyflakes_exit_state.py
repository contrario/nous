"""S317 V4: phase_pyflakes decides on the exit state when the tool
produced nothing on stdout, and the substring scan still decides
everything else.

scripts/ is not a package, so scripts/release.py is loaded by file path
in the shape of tests/test_s316_release_exit_state.py:48-53. The module
is NOT registered in sys.modules, for the reason measured in S316:
release.py declares no dataclass, so the FG-S314-G mechanism has no
purchase, and a global name in sys.modules is the residue named by the
open order-dependence finding from S312.

THIS FILE DOES NOT COMPOSE ITS SEAM FROM THE S316 TESTS. FG-S317-A:
those tests stub module.run, and phase_pytest reaches the subprocess
through run(). phase_pyflakes calls subprocess.run directly, measured
at release.py:239 with RUNDEF_HITS 1, so module.run has no purchase
here. The seam is module.subprocess, replaced on the freshly loaded
module object only. The real subprocess module is never patched.

SET: phase_pyflakes as loaded from scripts/release.py.
SHAPE: the phase is driven through a stubbed subprocess.run returning a
fixed exit code and fixed streams, over a single target that exists on
disk under a redirected REPO_ROOT.

BLIND TO: what pyflakes actually emits for any real input; whether any
real invocation produces these combinations; which of the two
indistinguishable causes produced an empty stdout, that being exactly
the distinction V5 measured to be unavailable; every other phase; and
main().

THE PREDICATE DECIDES AN UNCOVERED REGION AND HAD TO. V5 measured
stdout as empty or non-empty and never as whitespace-only. Both a bare
truth test and a stripped one decide that region, in opposite
directions: bare treats a lone newline as a report and lets the phase
go green, which is the defect class this arc exists to remove. The
stripped form fails closed there and converts no ran-and-reported case
into an abort. test_v4b locks that direction so a later seat meets a
decision rather than a silence.

The negative control removes the block from a copy of the module source
in memory, located by its marker and by an indentation of twelve. Eight
would over-consume: the sibling loop that follows the block sits at
eight in this phase, unlike phase_pytest where the guard sits at four.
FG-S317-B. It asserts what the removed text contains, not how many
lines it is (D315-11). The file on disk is not touched.

__s317_p2_exit_state_tests_v1__
"""
from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RELEASE = _REPO / "scripts" / "release.py"
_MARKER = "__s317_p2_pyflakes_exit_state_v1__"


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _load_release():
    spec = importlib.util.spec_from_file_location("_s317_release", _RELEASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arm(tmp_path, returncode: int, stdout: str, stderr: str = ""):
    """Load the module and redirect its target set, root and subprocess.

    The seam is module.subprocess, not module.run. FG-S317-A.
    """
    module = _load_release()
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    module.REPO_ROOT = tmp_path
    module.PYFLAKES_TARGETS = ("x.py",)
    module.subprocess = types.SimpleNamespace(
        run=lambda *a, **k: _Result(returncode, stdout, stderr)
    )
    return module


def test_v4a_non_zero_exit_with_empty_stdout_aborts(tmp_path):
    """The uncovered case of the F1 class in this phase."""
    module = _arm(tmp_path, 1, "", "no module named pyflakes\n")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pyflakes()
    message = str(exc.value)
    assert "did not analyse" in message
    assert "x.py" in message
    assert "exit 1" in message


def test_v4b_whitespace_only_stdout_is_decided_toward_failing_closed(
    tmp_path,
):
    """V5 never measured this input. Both predicates decide it."""
    module = _arm(tmp_path, 1, "\n  \n", "")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pyflakes()
    assert "did not analyse" in str(exc.value)


def test_v4c_non_zero_exit_with_a_report_takes_the_older_path(tmp_path):
    """A reported finding is not a failure to analyse."""
    module = _arm(tmp_path, 1, "x.py:1: undefined name 'q'\n")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pyflakes()
    message = str(exc.value)
    assert "undefined name(s) in production sources" in message
    assert "did not analyse" not in message


def test_v4d_non_zero_exit_with_an_unreported_class_still_returns(
    tmp_path,
):
    """THE SCOPE TEST. pyflakes exits 1 for an unused import too.

    The rule is not returncode != 0 on its own: that would convert every
    unused import in the seven declared targets into a release abort,
    which is a change of scope and not the repair of a defect. This test
    is what fails if a later seat widens the predicate.
    """
    module = _arm(tmp_path, 1, "x.py:1: 'os' imported but unused\n")
    assert module.phase_pyflakes() is None


def test_v4e_zero_exit_with_empty_stdout_returns(tmp_path):
    """The control. The ordinary clean path is unchanged."""
    module = _arm(tmp_path, 0, "")
    assert module.phase_pyflakes() is None


def test_v4f_both_streams_are_printed_whole_on_the_abort(
    tmp_path, capsys
):
    """D315-4's second property. Under this predicate stdout is
    blank-or-empty rather than empty, so both streams are printed."""
    module = _arm(tmp_path, 2, " \n", "traceback on stderr\n")
    with pytest.raises(module.ReleaseError):
        module.phase_pyflakes()
    out = capsys.readouterr().out
    assert "  traceback on stderr" in out
    assert "\n   \n" in out


def test_v4g_missing_target_still_raises_before_the_new_guard(tmp_path):
    """FG-S316-B: the absent-path case cannot reach the exit state.

    The phase raises on a missing target before it calls the subprocess,
    so the undetectable bucket is two causes and not three.
    """
    module = _arm(tmp_path, 1, "")
    module.PYFLAKES_TARGETS = ("absent_s317.py",)
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pyflakes()
    message = str(exc.value)
    assert "target missing" in message
    assert "did not analyse" not in message


def test_v4h_the_message_names_no_cause_and_says_so(tmp_path):
    """The limit is in the message, and this is what holds it there.

    V5 measured that a syntax error in an existing target and pyflakes
    being unimportable are indistinguishable on rc, stdout and stderr,
    and S316 removed the third candidate. So the message may name only
    what was detected. A later seat reading P1's message beside this one
    will be tempted to strengthen the weaker one by supplying a cause.
    That temptation meets this test.

    BLIND TO: a cause supplied in words this list does not spell. It
    locks a decision, not a semantics.
    """
    module = _arm(tmp_path, 1, "", "no module named pyflakes\n")
    with pytest.raises(module.ReleaseError) as exc:
        module.phase_pyflakes()
    message = str(exc.value)
    assert "does not distinguish the causes" in message
    assert "is named" in message
    for word in (
        "syntax error",
        "not importable",
        "no module named",
        "because",
        "caused by",
    ):
        assert word not in message


def _module_without_the_guard(tmp_path) -> dict:
    lines = _RELEASE.read_text(encoding="utf-8").splitlines(True)
    heads = [i for i, line in enumerate(lines) if _MARKER in line]
    assert len(heads) == 1
    start = heads[0]
    end = start + 1
    while end < len(lines) and lines[end].startswith(" " * 12):
        end += 1
    removed = "".join(lines[start:end])
    assert "result.returncode" in removed
    assert "did not analyse" in removed
    kept = lines[:start] + lines[end:]
    namespace = {"__file__": str(_RELEASE), "__name__": "_s317_mutated"}
    exec("".join(kept), namespace)
    return namespace


def test_v4a_negative_control_the_guard_is_what_raises(tmp_path):
    """Without the block, V4a's input stops raising. In memory only."""
    namespace = _module_without_the_guard(tmp_path)
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    namespace["REPO_ROOT"] = tmp_path
    namespace["PYFLAKES_TARGETS"] = ("x.py",)
    namespace["subprocess"] = types.SimpleNamespace(
        run=lambda *a, **k: _Result(1, "", "no module named pyflakes\n")
    )
    assert namespace["phase_pyflakes"]() is None


def test_v4_negative_control_stops_before_the_sibling_loop():
    """FG-S317-B. A walk on eight would eat the substring scan.

    The removed text must not carry the scan that follows it, or the
    control would pass for the wrong reason.
    """
    lines = _RELEASE.read_text(encoding="utf-8").splitlines(True)
    start = [i for i, line in enumerate(lines) if _MARKER in line][0]
    end = start + 1
    while end < len(lines) and lines[end].startswith(" " * 12):
        end += 1
    removed = "".join(lines[start:end])
    assert "undefined name" not in removed
    assert lines[end].startswith(" " * 8)
    assert not lines[end].startswith(" " * 12)
