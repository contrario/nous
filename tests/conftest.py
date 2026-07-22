"""
Pytest configuration for NOUS test suite.

test_replay_phase_d.py is a standalone harness designed to run as
`python3 tests/test_replay_phase_d.py` with its own PASS/FAIL accounting.
However, its functions are named `test_*` (and some are async), so pytest
auto-collects them; positional args get confused for fixtures and async
functions fail without pytest-asyncio. The harness is fully green when run
standalone (6/6 in Session 60).

This file excludes only that single hybrid case from pytest collection.
Other harnesses with __main__ blocks but no `test_*` functions are
silently skipped by pytest already; dual-mode files (pytest tests +
__main__) continue to be collected normally.

Single source of truth for harness exclusions. To run the excluded harness:
    python3 tests/test_replay_phase_d.py
"""
from __future__ import annotations

collect_ignore: list[str] = [
    "test_replay_phase_d.py",
]


# __c2_live_gate_v1__ live tests (real TSA) run only with --run-live.
import pytest as _pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live", action="store_true", default=False,
        help="run tests marked @pytest.mark.live (real network / TSA calls)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip_live = _pytest.mark.skip(reason="live test; pass --run-live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
