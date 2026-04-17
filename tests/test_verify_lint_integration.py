"""Integration tests for `nous verify` + governance lint.
__verify_lint_integration_tests_v1__
"""
from __future__ import annotations
import argparse
import io
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from cli import cmd_verify


PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append((name, detail))


CLEAN_SRC = (
    'world CleanWorld {\n'
    '    heartbeat = 1s\n'
    '    policy Cost {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.5\n'
    '        weight: 5.0\n'
    '        action: log_only\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '    heal {\n'
    '        on timeout => retry(3, exponential)\n'
    '        on api_error => retry(2, exponential)\n'
    '        on budget_exceeded => hibernate until next_cycle\n'
    '    }\n'
    '}\n'
)

RESERVED_PREFIX_SRC = (
    'world ReservedWorld {\n'
    '    heartbeat = 1s\n'
    '    policy __private {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.5\n'
    '        weight: 5.0\n'
    '        action: log_only\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '    heal {\n'
    '        on timeout => retry(3, exponential)\n'
    '        on api_error => retry(2, exponential)\n'
    '        on budget_exceeded => hibernate until next_cycle\n'
    '    }\n'
    '}\n'
)


def _tmp_nous(src: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".nous", delete=False) as fd:
        fd.write(src)
        return fd.name


def _ns(file: str, **kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "no_lint": False,
        "lint_strict": False,
        "lint_error_on": None,
    }
    defaults.update(kwargs)
    defaults["file"] = file
    return argparse.Namespace(**defaults)


def _run(ns: argparse.Namespace) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cmd_verify(ns)
    return code, out.getvalue() + err.getvalue()


def test_verify_runs_lint_by_default() -> None:
    path = _tmp_nous(CLEAN_SRC)
    try:
        _, output = _run(_ns(path))
        _check("default_runs_lint", "Lint:" in output, f"no Lint section in output")
    finally:
        Path(path).unlink()


def test_verify_no_lint_skips_section() -> None:
    path = _tmp_nous(CLEAN_SRC)
    try:
        _, output = _run(_ns(path, no_lint=True))
        _check("nolint_no_lint_section", "Lint:" not in output, f"lint ran despite --no-lint")
    finally:
        Path(path).unlink()


def test_verify_lint_invalid_error_on_exits_two() -> None:
    path = _tmp_nous(CLEAN_SRC)
    try:
        code, _ = _run(_ns(path, lint_error_on="L999"))
        _check("invalid_error_on_exit_two", code == 2, f"code={code}")
    finally:
        Path(path).unlink()


def test_verify_lint_strict_elevates_warning() -> None:
    path = _tmp_nous(RESERVED_PREFIX_SRC)
    try:
        code, _ = _run(_ns(path, lint_strict=True))
        _check("strict_elevates_warning", code == 1, f"code={code}")
    finally:
        Path(path).unlink()


def test_verify_lint_error_on_elevates_warning() -> None:
    path = _tmp_nous(RESERVED_PREFIX_SRC)
    try:
        code, _ = _run(_ns(path, lint_error_on="L010"))
        _check("error_on_l010_fails", code == 1, f"code={code}")
    finally:
        Path(path).unlink()


def run_all() -> int:
    tests = [
        test_verify_runs_lint_by_default,
        test_verify_no_lint_skips_section,
        test_verify_lint_invalid_error_on_exits_two,
        test_verify_lint_strict_elevates_warning,
        test_verify_lint_error_on_elevates_warning,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:
            FAILED.append((t.__name__, f"exception: {exc!r}"))
    total = len(PASSED) + len(FAILED)
    if FAILED:
        print("=" * 60)
        print(f"VERIFY LINT INTEGRATION TESTS -- FAILED ({len(FAILED)}/{total})")
        for name, detail in FAILED:
            print(f"  FAIL {name}: {detail}")
        print("=" * 60)
        return 1
    print("=" * 60)
    print(f"VERIFY LINT INTEGRATION TESTS -- ALL GREEN ({len(PASSED)}/{total})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
