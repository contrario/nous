"""test_replay_e2e.py — end-to-end deterministic replay proof."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

THIS = Path(__file__).resolve()
ROOT = THIS.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser import parse_nous_file  # type: ignore
from codegen import NousCodeGen  # type: ignore


NOUS_SOURCE = THIS.parent / "test_replay_e2e.nous"
JSONL_PATH = Path("/tmp/nous_replay_e2e.jsonl")


GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def green(msg: str) -> None:
    print(f"{GREEN}  ✓ {msg}{RESET}")


def red(msg: str) -> None:
    print(f"{RED}  ✗ {msg}{RESET}")


def step(msg: str) -> None:
    print(f"{CYAN}[STEP]{RESET} {msg}")


def compile_world(source_path: Path) -> Path:
    program = parse_nous_file(source_path)
    generated = NousCodeGen(program).generate()
    tmp = Path(tempfile.mkstemp(prefix="gen_replay_e2e_", suffix=".py")[1])
    tmp.write_text(generated, encoding="utf-8")
    return tmp


def compile_world_with_mode(source_path: Path, mode: str) -> Path:
    """Re-parse the source and flip replay.mode, then compile."""
    program = parse_nous_file(source_path)
    assert program.world and program.world.replay, "source has no replay block"
    program.world.replay.mode = mode
    generated = NousCodeGen(program).generate()
    tmp = Path(tempfile.mkstemp(prefix=f"gen_replay_e2e_{mode}_", suffix=".py")[1])
    tmp.write_text(generated, encoding="utf-8")
    return tmp


def load_module(pyfile: Path, mod_name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(mod_name, pyfile)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def find_soul_class(mod, preferred_name: str | None = None):
    """Find the soul class in a generated module.
    Generated soul classes are named with the 'Soul_' prefix."""
    candidates: list[type] = []
    for name in dir(mod):
        if name.startswith("Soul_"):
            obj = getattr(mod, name)
            if isinstance(obj, type):
                if preferred_name and name == f"Soul_{preferred_name}":
                    return obj
                candidates.append(obj)
    assert candidates, (
        f"no Soul_* class found in generated module; "
        f"available attributes starting with 'Soul': "
        f"{[n for n in dir(mod) if n.startswith('Soul')]}"
    )
    return candidates[0]


class CallCounter:
    """Tracks real sense executions. Lives across runs."""
    def __init__(self) -> None:
        self.n = 0
        self.values: list[int] = []

    async def tool(self, **_kwargs) -> int:
        self.n += 1
        v = 100 + self.n
        self.values.append(v)
        return v


async def run_cycles(rt_mod, counter: CallCounter, n_cycles: int,
                     preferred_soul: str = "Ticker") -> None:
    rt = rt_mod.build_runtime()
    rt.sense_executor.register_tool("counter_tick", counter.tool)
    soul_cls = find_soul_class(rt_mod, preferred_name=preferred_soul)
    soul = soul_cls(rt)
    for _ in range(n_cycles):
        await soul.instinct()
    if hasattr(rt, "replay_ctx") and hasattr(rt.replay_ctx, "close"):
        try:
            rt.replay_ctx.close()
        except Exception:
            pass


def read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def assert_event_kinds(events: list[dict], expected_kinds: list[str]) -> None:
    kinds = [e["kind"] for e in events]
    missing = [k for k in expected_kinds if k not in kinds]
    assert not missing, f"missing event kinds: {missing}; got kinds present: {sorted(set(kinds))}"


def main() -> int:
    if JSONL_PATH.exists():
        JSONL_PATH.unlink()

    # ───── STEP 1: compile world in RECORD mode ─────
    step("compile test_replay_e2e.nous (mode=record) → Python")
    gen_path = compile_world(NOUS_SOURCE)
    try:
        mod = load_module(gen_path, "gen_replay_e2e_record")
        green(f"generated + loaded: {gen_path.name}")

        # ───── STEP 2: RECORD mode, 3 cycles ─────
        step("RECORD: 3 cycles with counter tool")
        counter = CallCounter()
        asyncio.run(run_cycles(mod, counter, 3))
        assert counter.n == 3, f"expected 3 real sense calls, got {counter.n}"
        green(f"3 real sense executions (values: {counter.values})")

        # ───── STEP 3: inspect event log ─────
        step("inspect event log")
        assert JSONL_PATH.exists(), f"event log not written: {JSONL_PATH}"
        events = read_jsonl(JSONL_PATH)
        assert len(events) >= 12, f"expected >=12 events (3 cycles × 4+), got {len(events)}"
        green(f"{len(events)} events written")

        assert_event_kinds(
            events,
            ["cycle.start", "sense.invoke", "sense.result",
             "memory.write", "cycle.end"],
        )
        green("all expected event kinds present")

        starts = [e for e in events if e["kind"] == "cycle.start"]
        ends = [e for e in events if e["kind"] == "cycle.end"]
        assert len(starts) == 3, f"expected 3 cycle.start, got {len(starts)}"
        assert len(ends) == 3, f"expected 3 cycle.end, got {len(ends)}"
        green("3 cycle.start + 3 cycle.end")

        mw = [e for e in events if e["kind"] == "memory.write"]
        assert len(mw) == 6, f"expected 6 memory.write events, got {len(mw)}"
        fields = sorted({e["data"]["field"] for e in mw})
        assert fields == ["last_value", "ticks"], f"unexpected fields: {fields}"
        green("6 memory.write events (ticks + last_value × 3 cycles)")

        # Hash chain integrity
        step("verify hash chain integrity on recorded log")
        from replay_store import EventStore  # type: ignore
        st = EventStore.open(JSONL_PATH, mode="replay")
        ok, bad_seq, reason = st.verify()
        st.close()
        assert ok, f"chain broken at seq={bad_seq}: {reason}"
        green("hash chain intact")

        # ───── STEP 4: REPLAY mode, 0 real calls ─────
        step("compile test_replay_e2e.nous (mode=replay) → Python")
        gen_replay_path = compile_world_with_mode(NOUS_SOURCE, "replay")
        try:
            mod2 = load_module(gen_replay_path, "gen_replay_e2e_replay")
            green(f"generated + loaded: {gen_replay_path.name}")

            step("REPLAY: 3 cycles, real sense must NOT fire")
            replay_counter = CallCounter()
            asyncio.run(run_cycles(mod2, replay_counter, 3))
            assert replay_counter.n == 0, (
                f"REPLAY ISOLATION BROKEN — real tool fired {replay_counter.n} times"
            )
            green("0 real sense executions during replay — values came from event log")
        finally:
            gen_replay_path.unlink(missing_ok=True)

        # ───── STEP 5: tamper detection ─────
        step("TAMPER: mutate event 5 in place, expect chain break")
        raw = JSONL_PATH.read_bytes()
        lines = raw.splitlines(keepends=True)
        assert len(lines) >= 6, "not enough events to tamper"
        target = json.loads(lines[4].decode("utf-8"))
        if isinstance(target.get("data"), dict):
            for k in list(target["data"]):
                v = target["data"][k]
                if isinstance(v, str):
                    target["data"][k] = "X" + v
                    break
                if isinstance(v, (int, float)):
                    target["data"][k] = v + 999999
                    break
        lines[4] = (json.dumps(target, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        tampered_path = JSONL_PATH.with_suffix(".tampered.jsonl")
        tampered_path.write_bytes(b"".join(lines))
        from replay_store import EventStore as ES2  # type: ignore
        st2 = ES2.open(tampered_path, mode="replay")
        ok2, bad_seq2, reason2 = st2.verify()
        st2.close()
        tampered_path.unlink(missing_ok=True)
        assert not ok2, "tamper went undetected — chain still verifies"
        green(f"tamper detected at seq={bad_seq2}: {reason2}")

        print()
        print(f"{GREEN}================================================{RESET}")
        print(f"{GREEN}PHASE B E2E TEST — ALL GREEN{RESET}")
        print(f"{GREEN}================================================{RESET}")
        return 0

    finally:
        gen_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
