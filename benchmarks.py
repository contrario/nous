"""
NOUS Benchmark Suite v1.0 — nous bench file.nous
==================================================
CI/CD-ready. Measures parse/validate/typecheck/codegen times.
Detects regressions against saved baselines.
"""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

BASELINE_PATH = Path.home() / ".nous" / "bench_baseline.json"
RESULTS_PATH = Path.home() / ".nous" / "bench_results.json"
REGRESSION_THRESHOLD = 1.5


@dataclass
class StageResult:
    name: str
    time_ms: float
    ok: bool
    error: str = ""


@dataclass
class BenchResult:
    file: str
    stages: list[StageResult] = field(default_factory=list)
    total_ms: float = 0.0
    parse_cold_ms: float = 0.0
    parse_cached_ms: float = 0.0
    parse_cached_min_ms: float = 0.0
    parse_cached_max_ms: float = 0.0
    memory_peak_kb: float = 0.0
    souls: int = 0
    messages: int = 0
    laws: int = 0
    lines: int = 0
    regressions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stages"] = [asdict(s) for s in self.stages]
        return d


def _time_stage(name: str, fn: Any) -> tuple[StageResult, Any]:
    try:
        t0 = time.perf_counter()
        result = fn()
        t1 = time.perf_counter()
        return StageResult(name=name, time_ms=(t1 - t0) * 1000, ok=True), result
    except Exception as e:
        return StageResult(name=name, time_ms=0, ok=False, error=str(e)), None


def run_benchmark(source_path: str, runs: int = 50) -> BenchResult:
    path = Path(source_path)
    source = path.read_text(encoding="utf-8")
    result = BenchResult(file=path.name, lines=source.count("\n") + 1)

    sys.path.insert(0, str(path.parent))

    from parser import parse_nous, _PARSER_CACHE

    _PARSER_CACHE.clear()
    tracemalloc.start()

    stage, program = _time_stage("parse_cold", lambda: parse_nous(source))
    result.stages.append(stage)
    result.parse_cold_ms = stage.time_ms

    if not stage.ok or program is None:
        tracemalloc.stop()
        return result

    cached_times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        parse_nous(source)
        t1 = time.perf_counter()
        cached_times.append((t1 - t0) * 1000)

    result.parse_cached_ms = sum(cached_times) / len(cached_times)
    result.parse_cached_min_ms = min(cached_times)
    result.parse_cached_max_ms = max(cached_times)
    result.stages.append(StageResult(
        name="parse_cached",
        time_ms=result.parse_cached_ms,
        ok=True,
    ))

    result.souls = len(program.souls)
    result.messages = len(program.messages)
    result.laws = len(program.world.laws) if program.world else 0

    try:
        from validator import validate_program
        stage_v, vresult = _time_stage("validate", lambda: validate_program(program))
        result.stages.append(stage_v)
    except ImportError:
        result.stages.append(StageResult(name="validate", time_ms=0, ok=False, error="validator not found"))

    try:
        from typechecker import typecheck_program
        stage_t, _ = _time_stage("typecheck", lambda: typecheck_program(program))
        result.stages.append(stage_t)
    except ImportError:
        result.stages.append(StageResult(name="typecheck", time_ms=0, ok=False, error="typechecker not found"))

    try:
        from codegen import generate_python
        stage_c, code = _time_stage("codegen", lambda: generate_python(program))
        result.stages.append(stage_c)
        if stage_c.ok and code:
            import py_compile
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                tmp = f.name
            try:
                stage_p, _ = _time_stage("py_compile", lambda: py_compile.compile(tmp, doraise=True))
                result.stages.append(stage_p)
            finally:
                Path(tmp).unlink(missing_ok=True)
    except ImportError:
        result.stages.append(StageResult(name="codegen", time_ms=0, ok=False, error="codegen not found"))

    try:
        from formatter import format_nous
        stage_f, _ = _time_stage("format", lambda: format_nous(source))
        result.stages.append(stage_f)
    except ImportError:
        pass

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result.memory_peak_kb = peak / 1024

    result.total_ms = sum(s.time_ms for s in result.stages if s.name != "parse_cached")

    result.regressions = _check_regressions(result)

    return result


def _check_regressions(result: BenchResult) -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    try:
        baseline = json.loads(BASELINE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    if baseline.get("file") != result.file:
        return []

    regressions: list[str] = []
    bl_stages = {s["name"]: s["time_ms"] for s in baseline.get("stages", [])}

    for stage in result.stages:
        if stage.name in bl_stages and bl_stages[stage.name] > 0:
            ratio = stage.time_ms / bl_stages[stage.name]
            if ratio > REGRESSION_THRESHOLD:
                regressions.append(
                    f"{stage.name}: {stage.time_ms:.2f}ms vs baseline {bl_stages[stage.name]:.2f}ms ({ratio:.1f}x slower)"
                )

    bl_cached = baseline.get("parse_cached_ms", 0)
    if bl_cached > 0:
        ratio = result.parse_cached_ms / bl_cached
        if ratio > REGRESSION_THRESHOLD:
            regressions.append(
                f"parse_cached: {result.parse_cached_ms:.2f}ms vs baseline {bl_cached:.2f}ms ({ratio:.1f}x slower)"
            )

    return regressions


def save_baseline(result: BenchResult) -> Path:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(result.to_dict(), indent=2))
    return BASELINE_PATH


def save_results(result: BenchResult) -> Path:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, Any]] = []
    if RESULTS_PATH.exists():
        try:
            history = json.loads(RESULTS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    entry = result.to_dict()
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    history.append(entry)
    if len(history) > 100:
        history = history[-100:]
    RESULTS_PATH.write_text(json.dumps(history, indent=2))
    return RESULTS_PATH


def print_report(result: BenchResult) -> None:
    print(f"NOUS Benchmark — {result.file}")
    print(f"{'=' * 55}")
    print(f"  Lines: {result.lines} | Souls: {result.souls} | Messages: {result.messages} | Laws: {result.laws}")
    print()

    print(f"  {'Stage':<20} {'Time':>10} {'Status':>8}")
    print(f"  {'-' * 20} {'-' * 10} {'-' * 8}")
    for stage in result.stages:
        status = "\033[32mPASS\033[0m" if stage.ok else "\033[31mFAIL\033[0m"
        time_str = f"{stage.time_ms:.2f}ms"
        print(f"  {stage.name:<20} {time_str:>10} {status:>8}")

    print()
    print(f"  Parse cold:   {result.parse_cold_ms:.2f}ms")
    print(f"  Parse cached: {result.parse_cached_ms:.2f}ms (min={result.parse_cached_min_ms:.2f} max={result.parse_cached_max_ms:.2f})")
    print(f"  Memory peak:  {result.memory_peak_kb:.0f} KB")
    print(f"  Total:        {result.total_ms:.2f}ms")

    if result.regressions:
        print()
        print(f"  \033[31mREGRESSIONS ({len(result.regressions)}):\033[0m")
        for r in result.regressions:
            print(f"    ✗ {r}")
    elif BASELINE_PATH.exists():
        print()
        print(f"  \033[32m✓ No regressions detected\033[0m")

    all_ok = all(s.ok for s in result.stages)
    no_regress = len(result.regressions) == 0
    print()
    if all_ok and no_regress:
        print(f"  \033[32m✓ BENCH PASS\033[0m")
    else:
        print(f"  \033[31m✗ BENCH FAIL\033[0m")


def bench_cli(file: str, save_bl: bool = False, json_out: bool = False, runs: int = 50) -> int:
    result = run_benchmark(file, runs=runs)
    save_results(result)

    if save_bl:
        p = save_baseline(result)
        if not json_out:
            print(f"Baseline saved: {p}")

    if json_out:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_report(result)

    if result.regressions:
        return 1
    if not all(s.ok for s in result.stages):
        return 1
    return 0
