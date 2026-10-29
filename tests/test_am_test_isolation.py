"""Tests that depend on what ran before them, and tests that cannot fail.

Q1  The inject tests pass after an asyncio.run() in the same process
    (FG-S431-AM: four of them asked asyncio for the thread's current
    loop, which raises once asyncio.run() has left the thread without
    one).
Q2  No file under tests/ asks asyncio for the current loop that way.
Q3  Six files record checks through a helper whose result each call
    discards; the helper must raise on a false condition, or pytest
    passes the test whatever the condition. __am_check_raises_v1__
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
HELPERS = (
    ("test_governance_dashboard.py", "check"),
    ("test_governance_lint.py", "_check"),
    ("test_governance_simulator.py", "_check"),
    ("test_inject_message.py", "check"),
    ("test_lsp_lint_integration.py", "_check"),
    ("test_verify_lint_integration.py", "_check"),
)


def test_q1_inject_tests_pass_after_asyncio_run(tmp_path):
    first = tmp_path / "test_zz_first.py"
    first.write_text(
        "import asyncio\n\n"
        "def test_runs_asyncio_run():\n"
        "    async def f():\n"
        "        return 1\n"
        "    assert asyncio.run(f()) == 1\n",
        encoding="ascii",
    )
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--tb=line", str(first), str(TESTS / "test_inject_message.py")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600,
    )
    tail = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    assert p.returncode == 0 and re.search(r"\b14 passed\b", tail), (
        p.returncode, tail, p.stdout[-2000:])


def test_q2_no_test_calls_get_event_loop():
    hits = []
    for f in sorted(TESTS.rglob("*.py")):
        text = f.read_text(encoding="utf-8")
        n = text.count("asyncio.get_event_loop" + "()")
        if n:
            hits.append((f.name, n))
    assert hits == [], hits


def _load(name):
    path = TESTS / name
    spec = importlib.util.spec_from_file_location(
        "am_probe_" + name[:-3], str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a module-level dataclass needs it
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name,helper", HELPERS)
def test_q3_check_helper_raises_on_a_false_condition(name, helper):
    mod = _load(name)
    fn = getattr(mod, helper)
    with pytest.raises(AssertionError):
        fn("am probe", False, "a false condition must fail the test")
