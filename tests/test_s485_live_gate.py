"""S485 SU1: the live gate skips by the live marker, not by keywords.

pytest puts every node's name in an item's keywords, a directory's
included, so a checkout in a directory named live had every test
skipped by a gate that asked whether "live" was in item.keywords
(FG-S481-I; measured: 11 of 11 skipped in such a clone). The gate now
asks item.get_closest_marker("live").
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
REASON = "live test; pass --run-live to run"


def _load():
    spec = importlib.util.spec_from_file_location("_s485_conftest", _CONFTEST)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Cfg:
    def __init__(self, run_live):
        self.run_live = run_live

    def getoption(self, name):
        assert name == "--run-live"
        return self.run_live


class _Item:
    def __init__(self, keywords, marked):
        self.keywords = dict.fromkeys(keywords, 1)
        self.marked = marked
        self.added = []

    def get_closest_marker(self, name):
        return pytest.mark.live.mark if (self.marked and name == "live") else None

    def add_marker(self, m):
        self.added.append(m)


def _skips(item):
    return [m for m in item.added if m.mark.name == "skip"]


def test_L1_a_node_named_live_is_not_a_live_test():
    c = _load()
    item = _Item({"test_x", "test_s485_sdist_normalize.py", "tests", "live"}, marked=False)
    c.pytest_collection_modifyitems(_Cfg(False), [item])
    assert _skips(item) == []


def test_L2_a_marked_item_is_skipped_with_the_reason():
    c = _load()
    item = _Item({"test_tsa", "test_c3_anchors.py", "live"}, marked=True)
    c.pytest_collection_modifyitems(_Cfg(False), [item])
    s = _skips(item)
    assert len(s) == 1 and s[0].mark.kwargs.get("reason") == REASON


def test_L3_run_live_skips_nothing():
    c = _load()
    a = _Item({"test_tsa", "live"}, marked=True)
    b = _Item({"test_x", "live"}, marked=False)
    c.pytest_collection_modifyitems(_Cfg(True), [a, b])
    assert a.added == [] and b.added == []


def test_L4_the_gate_asks_the_marker_not_the_keywords():
    src = inspect.getsource(_load().pytest_collection_modifyitems)
    assert 'get_closest_marker("live")' in src
    assert "in item.keywords" not in src
