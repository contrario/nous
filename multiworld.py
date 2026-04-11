"""
NOUS Multi-World Runner — Πολύκοσμος (Polykosmos)
===================================================
Runs multiple .nous programs concurrently.
Each world gets its own runtime, channels, and task group.
Cross-world communication via shared channel bus.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("nous.multiworld")


class WorldInstance:
    def __init__(self, source_path: Path, compiled_code: str, world_name: str) -> None:
        self.source_path = source_path
        self.compiled_code = compiled_code
        self.world_name = world_name
        self.module: Any = None
        self.tmp_path: Path | None = None

    def load_module(self) -> Any:
        self.tmp_path = self.source_path.with_suffix(f".{self.world_name}.gen.py")
        self.tmp_path.write_text(self.compiled_code, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            f"nous_world_{self.world_name}", str(self.tmp_path)
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load compiled world: {self.world_name}")
        module = importlib.util.module_from_spec(spec)
        module.__name__ = f"nous_world_{self.world_name}"
        spec.loader.exec_module(module)
        self.module = module
        return module

    def cleanup(self) -> None:
        if self.tmp_path and self.tmp_path.exists():
            self.tmp_path.unlink()


class SharedChannelBus:
    def __init__(self) -> None:
        self._channels: dict[str, asyncio.Queue[Any]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = {}

    def get_queue(self, channel: str) -> asyncio.Queue[Any]:
        if channel not in self._channels:
            self._channels[channel] = asyncio.Queue(maxsize=100)
        return self._channels[channel]

    async def publish(self, channel: str, message: Any, source_world: str = "") -> None:
        log.info("[BUS] %s → %s: %s", source_world, channel, type(message).__name__)
        await self.get_queue(channel).put({"source": source_world, "data": message})

    async def subscribe(self, channel: str, timeout: float = 30.0) -> Any:
        try:
            msg = await asyncio.wait_for(self.get_queue(channel).get(), timeout=timeout)
            return msg.get("data") if isinstance(msg, dict) else msg
        except asyncio.TimeoutError:
            return None


class MultiWorldRunner:
    def __init__(self) -> None:
        self.worlds: list[WorldInstance] = []
        self.bus = SharedChannelBus()
        self._results: dict[str, str] = {}

    def add_world(self, source_path: Path, compiled_code: str, world_name: str) -> None:
        self.worlds.append(WorldInstance(source_path, compiled_code, world_name))

    async def run_all(self) -> dict[str, str]:
        log.info("=" * 60)
        log.info("NOUS Multi-World Runner — %d worlds", len(self.worlds))
        log.info("=" * 60)

        for w in self.worlds:
            log.info("  Loading: %s (%s)", w.world_name, w.source_path.name)
            try:
                w.load_module()
                log.info("  Loaded:  %s ✓", w.world_name)
            except Exception as e:
                log.error("  Failed:  %s — %s", w.world_name, e)
                self._results[w.world_name] = f"LOAD_ERROR: {e}"

        runnable = [w for w in self.worlds if w.module is not None]
        if not runnable:
            log.error("No worlds loaded successfully")
            return self._results

        log.info("")
        log.info("Starting %d worlds concurrently...", len(runnable))
        log.info("")

        try:
            async with asyncio.TaskGroup() as tg:
                for w in runnable:
                    tg.create_task(self._run_world(w))
        except* KeyboardInterrupt:
            log.info("Multi-world stopped by user")
        except* Exception as eg:
            for exc in eg.exceptions:
                log.error("World crashed: %s", exc)
        finally:
            for w in self.worlds:
                w.cleanup()

        return self._results

    async def _run_world(self, world: WorldInstance) -> None:
        run_fn = getattr(world.module, "run_world", None)
        if run_fn is None:
            self._results[world.world_name] = "ERROR: no run_world() found"
            log.error("%s: no run_world() function", world.world_name)
            return

        log.info("[%s] Starting...", world.world_name)
        t0 = time.perf_counter()
        try:
            await run_fn()
            elapsed = time.perf_counter() - t0
            self._results[world.world_name] = f"OK ({elapsed:.1f}s)"
        except Exception as e:
            elapsed = time.perf_counter() - t0
            self._results[world.world_name] = f"ERROR: {e} ({elapsed:.1f}s)"
            log.error("[%s] Crashed after %.1fs: %s", world.world_name, elapsed, e)


async def run_multi(
    sources: list[Path],
    compile_fn: Any,
    parse_fn: Any,
    validate_fn: Any,
) -> int:
    runner = MultiWorldRunner()

    for source in sources:
        if not source.exists():
            log.error("File not found: %s", source)
            continue

        try:
            program = parse_fn(source)
            world_name = program.world.name if program.world else source.stem
            result = validate_fn(program)
            if not result.ok:
                for e in result.errors:
                    log.error("[%s] %s", world_name, e)
                continue
            code = compile_fn(program)
            runner.add_world(source, code, world_name)
            log.info("Compiled: %s → %s", source.name, world_name)
        except Exception as e:
            log.error("Compile error for %s: %s", source.name, e)

    if not runner.worlds:
        log.error("No worlds compiled successfully")
        return 1

    results = await runner.run_all()
    log.info("")
    log.info("=" * 60)
    log.info("Multi-World Summary:")
    for name, status in results.items():
        log.info("  %s: %s", name, status)
    log.info("=" * 60)
    return 0
