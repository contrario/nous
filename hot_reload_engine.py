"""
NOUS Hot Reload Engine — Ζεστή Επαναφόρτωση (Zesti Epanafortosi)
=================================================================
Watches .nous source file for changes during runtime.
On change: reparse → recompile → diff souls → swap runners.
Zero downtime. No process restart.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import os
import py_compile
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("nous.hot_reload")


class HotReloadEngine:

    def __init__(
        self,
        runtime: Any,
        source_path: Path,
        poll_interval: float = 2.0,
    ) -> None:
        self._runtime = runtime
        self._source_path = source_path
        self._poll_interval = poll_interval
        self._alive = True
        self._last_mtime: float = 0.0
        self._reload_count = 0
        self._last_reload_time: float = 0.0
        self._errors: list[str] = []
        self._soul_versions: dict[str, int] = {}

    async def run(self) -> None:
        self._last_mtime = self._get_mtime()
        log.info(
            f"Hot reload engine started (source={self._source_path.name}, "
            f"interval={self._poll_interval}s)"
        )
        while self._alive:
            try:
                await asyncio.sleep(self._poll_interval)
                current_mtime = self._get_mtime()
                if current_mtime > self._last_mtime:
                    self._last_mtime = current_mtime
                    log.info(f"═══ HOT RELOAD: change detected in {self._source_path.name} ═══")
                    await self._reload()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Hot reload engine error: {e}")

        log.info(f"Hot reload engine stopped: {self._reload_count} reloads")

    def _get_mtime(self) -> float:
        try:
            return self._source_path.stat().st_mtime
        except OSError:
            return 0.0

    async def _reload(self) -> None:
        t0 = time.perf_counter()
        self._errors.clear()

        new_program = self._parse()
        if new_program is None:
            return

        if not self._validate(new_program):
            return

        gen_path = self._compile(new_program)
        if gen_path is None:
            return

        module = self._load_module(gen_path)
        if module is None:
            return

        await self._swap_souls(module, new_program)

        elapsed = (time.perf_counter() - t0) * 1000
        self._reload_count += 1
        self._last_reload_time = time.time()

        log.info(
            f"  Reload #{self._reload_count} complete ({elapsed:.0f}ms)\n"
            f"  ═══ HOT RELOAD COMPLETE ═══"
        )

    def _parse(self) -> Any:
        try:
            script_dir = str(self._source_path.parent)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)

            nous_dir = str(Path(__file__).parent)
            if nous_dir not in sys.path:
                sys.path.insert(0, nous_dir)

            import parser as parser_mod
            if hasattr(parser_mod, '_PARSER_CACHE'):
                parser_mod._PARSER_CACHE.clear()

            from parser import parse_nous
            source = self._source_path.read_text(encoding="utf-8")
            program = parse_nous(source)
            soul_count = len(program.souls)
            log.info(f"  Parse OK: {soul_count} souls")
            return program
        except Exception as e:
            self._errors.append(f"Parse error: {e}")
            log.error(f"  Parse FAILED: {e}")
            return None

    def _validate(self, program: Any) -> bool:
        try:
            from validator import NousValidator
            v = NousValidator(program)
            result = v.validate()
            if not result.ok:
                for e in result.errors:
                    self._errors.append(f"Validate: {e}")
                    log.error(f"  Validate ERROR: {e}")
                return False
            for w in result.warnings:
                log.warning(f"  Validate WARN: {w}")
            log.info(f"  Validate OK")
            return True
        except Exception as e:
            self._errors.append(f"Validate error: {e}")
            log.error(f"  Validate FAILED: {e}")
            return False

    def _compile(self, program: Any) -> Optional[Path]:
        try:
            from codegen import NousCodeGen
            cg = NousCodeGen(program)
            code = cg.generate()

            tmp = tempfile.NamedTemporaryFile(
                suffix=".py", mode="w", delete=False,
                dir=str(self._source_path.parent),
                prefix="_hot_reload_",
            )
            tmp.write(code)
            tmp.close()
            tmp_path = Path(tmp.name)

            try:
                py_compile.compile(str(tmp_path), doraise=True)
            except py_compile.PyCompileError as e:
                self._errors.append(f"py_compile: {e}")
                log.error(f"  Compile FAILED: {e}")
                tmp_path.unlink(missing_ok=True)
                return None

            log.info(f"  Compile OK: {code.count(chr(10)) + 1} lines")
            return tmp_path
        except Exception as e:
            self._errors.append(f"Compile error: {e}")
            log.error(f"  Compile FAILED: {e}")
            return None

    def _load_module(self, gen_path: Path) -> Any:
        try:
            mod_name = f"_hot_reload_{self._reload_count}"
            spec = importlib.util.spec_from_file_location(mod_name, str(gen_path))
            if spec is None or spec.loader is None:
                log.error("  Module load FAILED: invalid spec")
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            log.info(f"  Module loaded: {mod_name}")
            return module
        except Exception as e:
            self._errors.append(f"Module load: {e}")
            log.error(f"  Module load FAILED: {e}")
            return None
        finally:
            gen_path.unlink(missing_ok=True)

    async def _swap_souls(self, module: Any, program: Any) -> None:
        if not hasattr(module, 'build_runtime'):
            log.error("  Swap FAILED: no build_runtime() in generated module")
            return

        new_soul_names = {s.name for s in program.souls}
        old_soul_names = {r.name for r in self._runtime._runners}

        added = new_soul_names - old_soul_names
        removed = old_soul_names - new_soul_names
        common = new_soul_names & old_soul_names

        if removed:
            for name in removed:
                self._runtime.remove_soul(name)
                log.info(f"  Soul REMOVED: {name}")

        new_rt = module.build_runtime()

        if added or common:
            new_runners = {r.name: r for r in new_rt._runners}

            for name in common:
                old_runner = None
                for r in self._runtime._runners:
                    if r.name == name:
                        old_runner = r
                        break

                new_runner = new_runners.get(name)
                if old_runner and new_runner:
                    old_runner._instinct = new_runner._instinct
                    old_runner._heal = new_runner._heal
                    old_runner._tier = new_runner._tier
                    old_runner._heartbeat = new_runner._heartbeat
                    version = self._soul_versions.get(name, 0) + 1
                    self._soul_versions[name] = version
                    log.info(f"  Soul SWAPPED: {name} (v{version})")

            for name in added:
                new_runner = new_runners.get(name)
                if new_runner:
                    self._runtime.add_soul(new_runner)
                    asyncio.create_task(new_runner.run(self._runtime.channels))
                    self._soul_versions[name] = 1
                    log.info(f"  Soul ADDED: {name} (v1)")

        if new_rt._mitosis_engine and self._runtime._mitosis_engine:
            me = new_rt._mitosis_engine
            for soul_name, config in me._configs.items():
                if soul_name in self._runtime._mitosis_engine._configs:
                    self._runtime._mitosis_engine._configs[soul_name] = config
                    log.info(f"  Mitosis config UPDATED: {soul_name}")

        log.info(
            f"  Swap summary: {len(added)} added, {len(common)} swapped, "
            f"{len(removed)} removed"
        )

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        return {
            "source": str(self._source_path),
            "reload_count": self._reload_count,
            "last_reload": self._last_reload_time,
            "poll_interval": self._poll_interval,
            "soul_versions": dict(self._soul_versions),
            "errors": list(self._errors),
        }

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Hot Reload Status ═══")
        lines.append("")
        lines.append(f"  Source:           {self._source_path.name}")
        lines.append(f"  Poll interval:    {self._poll_interval}s")
        lines.append(f"  Total reloads:    {self._reload_count}")
        if self._last_reload_time:
            ago = time.time() - self._last_reload_time
            lines.append(f"  Last reload:      {ago:.0f}s ago")
        lines.append("")
        if self._soul_versions:
            lines.append("  Soul versions:")
            for name, ver in sorted(self._soul_versions.items()):
                lines.append(f"    {name}: v{ver}")
        if self._errors:
            lines.append("")
            lines.append("  Last errors:")
            for e in self._errors[-3:]:
                lines.append(f"    ✗ {e}")
        lines.append("")
        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
