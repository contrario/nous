"""S497 phase 1 (FG-S492-I): Noesis is consulted only when the process
opts in with NOUS_NOESIS=1; an opted-in process that cannot load it
fails loudly; a Noesis answer is logged without the query's text.
Fake noesis_engine and noesis_oracle modules stand in through
sys.modules; no lattice, network or untracked module is read. The fake
engine accepts any load, for the lattice's absolute path exists on
server A and not elsewhere."""
import asyncio
import logging
import sys
import types

import pytest

import nous_runtime


class _Result:
    def __init__(self, score, response):
        self.score = score
        self.response = response


def _fakes(monkeypatch, calls, score=0.9):
    eng = types.ModuleType("noesis_engine")

    class NoesisEngine:
        def __init__(self, oracle_fn=None, oracle_threshold=None):
            calls.append("init")
            self.lattice = types.SimpleNamespace(size=0)

        def load(self, path):
            calls.append("load")

        def think(self, query, use_oracle=True):
            calls.append("think")
            return _Result(score, "FAKE_NOESIS_ANSWER")

    eng.NoesisEngine = NoesisEngine
    ora = types.ModuleType("noesis_oracle")
    ora.create_oracle_fn = lambda: ((lambda *a, **k: None), None)
    monkeypatch.setitem(sys.modules, "noesis_engine", eng)
    monkeypatch.setitem(sys.modules, "noesis_oracle", ora)


def _rt():
    rt = nous_runtime.NousRuntime(mode="dry-run", max_cycles=1)
    rt.register_soul("s497", "m", "Tier0", [])
    return rt


def test_t1_default_off(monkeypatch):
    monkeypatch.delenv("NOUS_NOESIS", raising=False)
    calls = []
    _fakes(monkeypatch, calls)
    rt = _rt()
    out = asyncio.run(rt.think("s497", "a query"))
    assert out.startswith("[DRY-RUN]")
    assert calls == []
    assert rt._get_noesis() is None


def test_t2_optin_unloadable_raises(monkeypatch):
    monkeypatch.setenv("NOUS_NOESIS", "1")
    monkeypatch.setitem(sys.modules, "noesis_engine", None)
    rt = _rt()
    with pytest.raises(RuntimeError):
        rt._get_noesis()


def test_t3_hit_recorded_without_query(monkeypatch, caplog):
    monkeypatch.setenv("NOUS_NOESIS", "1")
    calls = []
    _fakes(monkeypatch, calls)
    caplog.set_level(logging.DEBUG, logger="nous.runtime")
    rt = _rt()
    out = asyncio.run(rt.think("s497", "QUERY_TEXT_S497"))
    assert out == "FAKE_NOESIS_ANSWER"
    hits = [r for r in caplog.records if r.name == "nous.runtime"
            and r.levelno >= logging.WARNING and "Noesis hit" in r.getMessage()]
    assert len(hits) == 1
    assert all("QUERY_TEXT_S497" not in r.getMessage() for r in caplog.records)


def test_t4_optin_hit_kept(monkeypatch):
    monkeypatch.setenv("NOUS_NOESIS", "1")
    calls = []
    _fakes(monkeypatch, calls)
    rt = _rt()
    asyncio.run(rt.think("s497", "a query"))
    assert any(e.get("type") == "noesis_hit" for e in rt.rlog.entries)


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_t5_only_1_enables(monkeypatch, value):
    monkeypatch.setenv("NOUS_NOESIS", value)
    calls = []
    _fakes(monkeypatch, calls)
    rt = _rt()
    asyncio.run(rt.think("s497", "a query"))
    assert calls == []


def test_t6_failed_load_never_cached(monkeypatch):
    monkeypatch.setenv("NOUS_NOESIS", "1")
    calls = []
    _fakes(monkeypatch, calls)

    def _bad_load(self, path):
        calls.append("load")
        raise OSError("S497_LOAD_FAIL")

    monkeypatch.setattr(sys.modules["noesis_engine"].NoesisEngine,
                        "load", _bad_load)
    rt = _rt()

    class _P:
        def __init__(self, p):
            self.p = p

        def exists(self):
            return True

    monkeypatch.setattr(nous_runtime, "Path", _P)
    for _ in range(2):
        with pytest.raises(RuntimeError) as ei:
            rt._get_noesis()
        assert "S497_LOAD_FAIL" not in str(ei.value)
        assert rt._noesis_engine is None
    assert calls.count("load") == 2
