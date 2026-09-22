"""
NOUS Session 366 -- UnpriceableSoulModel at the command line
(docs/ONE_PRICE_SOURCE_DESIGN.md section 19).

`nous run --hot` and `nous replay --mutate` report a model the pricing
table cannot price as a build error with the cause, not a traceback or a
divergence; a hot reload edit that the refusal stops leaves the live
world unchanged; a hot reload edit that changes a soul's model moves the
runner to the new model.

Each case runs with HOME and the working directory in a temporary
directory holding its own nous_prices.toml (layer 2), and the runtime's
memoised table is reset, so no case depends on the shipped table.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cli
import runtime

ROOT = Path(__file__).resolve().parent.parent
UNPRICED = "s366-unpriced"


def _table_text() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    out = f"_schema_version = \"2.0\"\n_last_verified  = \"{today}\"\n_currency       = \"USD\"\n"
    for name, inp, outp in (("s366-a", "1.00", "2.00"), ("s366-b", "3.00", "4.00")):
        out += (
            f"\n[models.\"{name}\"]\nprovider       = \"s366\"\npricing_model  = \"per_token\"\n"
            f"input_per_1m  = \"{inp}\"\noutput_per_1m = \"{outp}\"\n"
            f"reasoning_token_multiplier = \"1.0\"\nverified_date = \"{today}\"\nverified_by   = \"manual\"\n"
        )
    return out


def _prog(souls: list[tuple[str, str, str]]) -> str:
    out = "world W {\n  heartbeat = 10s\n}\n"
    for name, model, tier in souls:
        out += (
            f"soul {name} {{\n  mind: {model} @ {tier}\n"
            "  memory {\n    n: int = 0\n  }\n"
            "  instinct {\n    remember n = n + 1\n  }\n"
            "  heal {\n    on error => alert(operator)\n  }\n}\n"
        )
    return out


@pytest.fixture()
def iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    (work / "nous_prices.toml").write_text(_table_text(), encoding="utf-8")
    monkeypatch.setattr(runtime, "_RUNTIME_PRICING", None)
    return work


def _run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
             argv: list[str]) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["nous", *argv])
    try:
        rc = cli.main()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    cap = capsys.readouterr()
    return (rc if isinstance(rc, int) else 0), cap.out, cap.err


def _replay_source(model: str) -> str:
    text = (ROOT / "tests" / "test_replay_e2e.nous").read_text(encoding="utf-8")
    assert "deepseek-v4-flash @ Tier1" in text
    return text.replace("deepseek-v4-flash @ Tier1", model + " @ Tier1")


def _empty_baseline(work: Path) -> Path:
    from replay_store import EventStore
    log = work / "baseline.jsonl"
    EventStore.open(log, mode="record").close()
    return log


def test_run_hot_refuses_cleanly(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    src = iso / "unpriced.nous"
    src.write_text(_prog([("A", UNPRICED, "Tier1")]), encoding="utf-8")
    rc, out, err = _run_cli(monkeypatch, capsys, ["run", str(src), "--hot"])
    assert "Error: cannot build the runtime: unpriceable:" in err, "rc " + str(rc) + " stderr " + err[:300]
    assert UNPRICED in err, err[:300]
    assert "Traceback" not in (out + err), (out + err)[:300]
    assert rc == 1, "rc " + str(rc)


def test_replay_mutate_refuses_cleanly(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    log = _empty_baseline(iso)
    src = iso / "unpriced_replay.nous"
    src.write_text(_replay_source(UNPRICED), encoding="utf-8")
    rc, out, err = _run_cli(monkeypatch, capsys, ["replay", str(log), "--mutate", str(src)])
    assert "error: cannot build the runtime for " in err, "rc " + str(rc) + " stderr " + err[:300] + " stdout " + out[:300]
    assert UNPRICED in err, err[:300]
    assert "DIVERGENT" not in out, out[:300]
    assert not Path(f"/tmp/nous_mutate_{os.getpid()}.py").exists(), "temporary module left behind"
    assert rc == 1, "rc " + str(rc)


def test_replay_mutate_priced_is_equivalent(iso: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    log = _empty_baseline(iso)
    src = iso / "priced_replay.nous"
    src.write_text(_replay_source("s366-a"), encoding="utf-8")
    rc, out, err = _run_cli(monkeypatch, capsys, ["replay", str(log), "--mutate", str(src)])
    assert "EQUIVALENT" in out, "rc " + str(rc) + " stdout " + out[:300] + " stderr " + err[:300]
    assert rc == 0, "rc " + str(rc)


def _live(work: Path, souls: list[tuple[str, str, str]]):
    from hot_reload_engine import HotReloadEngine
    from codegen import NousCodeGen
    from parser import parse_nous
    text = _prog(souls)
    src = work / "world.nous"
    src.write_text(text, encoding="utf-8")
    gen = work / "gen0.py"
    gen.write_text(NousCodeGen(parse_nous(text)).generate(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("s366_gen0", gen)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rt = mod.build_runtime()
    return rt, HotReloadEngine(rt, src, poll_interval=60.0), src


def _runners(rt) -> dict[str, tuple[object, object]]:
    return {r.name: (getattr(r, "_model", None), getattr(r, "_tier", None)) for r in rt._runners}


def test_hot_reload_refused_swap_leaves_world_unchanged(iso: Path) -> None:
    async def go() -> None:
        rt, hr, src = _live(iso, [("A", "s366-a", "Tier3"), ("B", "s366-a", "Tier3")])
        before = _runners(rt)
        src.write_text(_prog([("A", "s366-a", "Tier3"), ("C", UNPRICED, "Tier1")]), encoding="utf-8")
        try:
            await hr._reload()
        except Exception as exc:
            pytest.fail("reload raised " + type(exc).__name__ + ": " + str(exc)[:200] + "; runners now " + repr(_runners(rt)))
        assert _runners(rt) == before, repr(_runners(rt)) + " != " + repr(before)
        assert any(e.startswith("Swap refused: unpriceable:") for e in hr._errors), repr(hr._errors)
        assert hr._reload_count == 0, "a refused swap counted as reload " + str(hr._reload_count)
    asyncio.run(go())


def test_hot_reload_swaps_model(iso: Path) -> None:
    async def go() -> None:
        rt, hr, src = _live(iso, [("A", "s366-a", "Tier3")])
        src.write_text(_prog([("A", "s366-b", "Tier1")]), encoding="utf-8")
        await hr._reload()
        assert _runners(rt) == {"A": ("s366-b", "Tier1")}, repr(_runners(rt))
    asyncio.run(go())


def test_hot_reload_priced_add(iso: Path) -> None:
    async def go() -> None:
        rt, hr, src = _live(iso, [("A", "s366-a", "Tier3")])
        src.write_text(_prog([("A", "s366-a", "Tier3"), ("C", "s366-b", "Tier1")]), encoding="utf-8")
        await hr._reload()
        assert set(_runners(rt)) == {"A", "C"}, repr(_runners(rt))
        assert _runners(rt)["C"] == ("s366-b", "Tier1"), repr(_runners(rt))
    asyncio.run(go())
