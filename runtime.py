"""
NOUS Runtime — Ζωή (Zoi / Life)
=================================
Connects generated NOUS programs to the live Noosphere ecosystem.
Dispatches sense calls to real tools, LLM calls to real providers,
tracks costs against world laws, and runs perception triggers.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import time
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from pydantic import BaseModel, Field

log = logging.getLogger("nous.runtime")

NOOSPHERE_TOOLS_DIR = Path("/opt/aetherlang_agents/tools")
NOOSPHERE_CORE_DIR = Path("/opt/aetherlang_agents/core")


class DataProxy:
    """Makes dict data accessible via dot notation."""

    def __init__(self, data: Any) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        d = object.__getattribute__(self, "_data")
        if isinstance(d, dict) and name in d:
            val = d[name]
            if isinstance(val, dict):
                return DataProxy(val)
            return val
        raise AttributeError(f"No field '{name}'")

    def get(self, key: str, default: Any = None) -> Any:
        d = object.__getattribute__(self, "_data")
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    def __repr__(self) -> str:
        return f"DataProxy({object.__getattribute__(self, '_data')})"

    def __iter__(self):
        d = object.__getattribute__(self, "_data")
        if isinstance(d, (list, tuple)):
            return iter(d)
        return iter([])

    def __len__(self) -> int:
        d = object.__getattribute__(self, "_data")
        if isinstance(d, (list, tuple, dict)):
            return len(d)
        return 0


class ToolResult(BaseModel):
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    cost: float = 0.0
    latency_ms: float = 0.0

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in ("success", "data", "error", "cost", "latency_ms", "model_fields", "model_config", "model_computed_fields"):
            raise AttributeError(name)
        if isinstance(self.data, dict) and name in self.data:
            val = self.data[name]
            if isinstance(val, dict):
                return DataProxy(val)
            return val
        raise AttributeError(f"ToolResult has no field '{name}'")

    def _primary_value(self) -> Any:
        if isinstance(self.data, (int, float, str, bool)):
            return self.data
        if isinstance(self.data, dict):
            for k, v in self.data.items():
                if k in ("success", "error", "latency_ms", "cost", "count", "query"):
                    continue
                if isinstance(v, (int, float)):
                    return v
            return self.data
        return self.data

    def __lt__(self, other: Any) -> bool:
        return self._primary_value() < other

    def __le__(self, other: Any) -> bool:
        return self._primary_value() <= other

    def __gt__(self, other: Any) -> bool:
        return self._primary_value() > other

    def __ge__(self, other: Any) -> bool:
        return self._primary_value() >= other

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ToolResult):
            return self.data == other.data
        return self._primary_value() == other

    def __float__(self) -> float:
        return float(self._primary_value())

    def __int__(self) -> int:
        return int(self._primary_value())

    def __sub__(self, other: Any) -> float:
        return float(self._primary_value()) - float(other)

    def __rsub__(self, other: Any) -> float:
        return float(other) - float(self._primary_value())

    def __mul__(self, other: Any) -> float:
        return float(self._primary_value()) * float(other)

    def __rmul__(self, other: Any) -> float:
        return float(other) * float(self._primary_value())

    def filter(self, field: str, op: str, value: Any) -> list[Any]:
        if not isinstance(self.data, list):
            return []
        ops = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        fn = ops.get(op, lambda a, b: True)
        result = []
        for item in self.data:
            if isinstance(item, dict):
                val = item.get(field, 0)
            elif hasattr(item, field):
                val = getattr(item, field)
            else:
                continue
            if fn(val, value):
                result.append(DataProxy(item) if isinstance(item, dict) else item)
        return result

    def __iter__(self):
        if isinstance(self.data, list):
            return iter([DataProxy(item) if isinstance(item, dict) else item for item in self.data])
        return iter([])

    def __len__(self) -> int:
        if isinstance(self.data, list):
            return len(self.data)
        return 0

    def __bool__(self) -> bool:
        return self.success


class CostTracker:
    def __init__(self, budget_per_cycle: float = 1.0) -> None:
        self.budget_per_cycle = budget_per_cycle
        self.current_cycle_cost = 0.0
        self.total_cost = 0.0
        self.cycle_count = 0
        self._lock = asyncio.Lock()

    async def record(self, cost: float, soul_name: str, operation: str) -> None:
        async with self._lock:
            self.current_cycle_cost += cost
            self.total_cost += cost
            log.debug(f"Cost: {soul_name}.{operation} = ${cost:.6f} (cycle total: ${self.current_cycle_cost:.6f})")

    async def check_budget(self, soul_name: str) -> bool:
        async with self._lock:
            if self.current_cycle_cost >= self.budget_per_cycle:
                log.warning(f"Budget exceeded for {soul_name}: ${self.current_cycle_cost:.4f} >= ${self.budget_per_cycle:.4f}")
                return False
            return True

    def new_cycle(self) -> None:
        self.cycle_count += 1
        log.info(f"Cycle {self.cycle_count} cost: ${self.current_cycle_cost:.6f}")
        self.current_cycle_cost = 0.0


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._stubs: dict[str, Callable[..., Coroutine[Any, Any, ToolResult]]] = {}

    def scan_noosphere(self) -> int:
        if not NOOSPHERE_TOOLS_DIR.exists():
            log.warning(f"Tools directory not found: {NOOSPHERE_TOOLS_DIR}")
            return 0

        count = 0
        for tool_file in sorted(NOOSPHERE_TOOLS_DIR.glob("*.py")):
            if tool_file.name.startswith("_"):
                continue
            tool_name = tool_file.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"nous_tool_{tool_name}", str(tool_file)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._tools[tool_name] = module
                    count += 1
            except Exception as e:
                log.warning(f"Failed to load tool {tool_name}: {e}")

        log.info(f"Loaded {count} tools from Noosphere")
        return count

    def register_stub(self, name: str, func: Callable[..., Coroutine[Any, Any, ToolResult]]) -> None:
        self._stubs[name] = func

    async def call(self, tool_name: str, *args: Any, **kwargs: Any) -> ToolResult:
        start = time.monotonic()

        if tool_name in self._stubs:
            try:
                result = await self._stubs[tool_name](*args, **kwargs)
                result.latency_ms = (time.monotonic() - start) * 1000
                return result
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=str(e),
                    latency_ms=(time.monotonic() - start) * 1000,
                )

        module = self._tools.get(tool_name)
        if module is None:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}. Available: {sorted(self._tools.keys())}",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        execute_fn = getattr(module, "execute", None)
        if execute_fn is None:
            tool_cls = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "execute"):
                    tool_cls = attr
                    break
            if tool_cls:
                instance = tool_cls()
                execute_fn = instance.execute
            else:
                return ToolResult(
                    success=False,
                    error=f"Tool {tool_name} has no execute() function or class",
                    latency_ms=(time.monotonic() - start) * 1000,
                )

        try:
            if asyncio.iscoroutinefunction(execute_fn):
                raw = await execute_fn(*args, **kwargs)
            else:
                raw = execute_fn(*args, **kwargs)

            if isinstance(raw, ToolResult):
                raw.latency_ms = (time.monotonic() - start) * 1000
                return raw

            if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
                return ToolResult(
                    success=raw.get("success", True),
                    data=raw["data"],
                    latency_ms=(time.monotonic() - start) * 1000,
                )

            return ToolResult(
                success=True,
                data=raw,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=(time.monotonic() - start) * 1000,
            )

    @property
    def available(self) -> list[str]:
        return sorted(set(list(self._tools.keys()) + list(self._stubs.keys())))


TIER_PROVIDERS: dict[str, dict[str, Any]] = {
    "Tier0A": {
        "provider": "anthropic",
        "base_url": None,
        "api_key_env": "ANTHROPIC_API_KEY",
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
    "Tier0B": {
        "provider": "openai",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "cost_per_1k_input": 0.005,
        "cost_per_1k_output": 0.015,
    },
    "Tier1": {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "cost_per_1k_input": 0.001,
        "cost_per_1k_output": 0.002,
    },
    "Tier2": {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    "Tier3": {
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
}


class LLMCaller:
    def __init__(self) -> None:
        self._http: Any = None

    async def _get_http(self) -> Any:
        if self._http is None:
            import httpx
            self._http = httpx.AsyncClient(timeout=60.0)
        return self._http

    async def call(
        self,
        model: str,
        tier: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> tuple[str, float]:
        tier_config = TIER_PROVIDERS.get(tier, TIER_PROVIDERS["Tier1"])
        provider = tier_config["provider"]

        if provider == "anthropic":
            return await self._call_anthropic(model, prompt, system, temperature, max_tokens, tier_config)
        elif provider == "ollama":
            return await self._call_openai_compat(model, prompt, system, temperature, max_tokens, tier_config)
        else:
            return await self._call_openai_compat(model, prompt, system, temperature, max_tokens, tier_config)

    async def _call_anthropic(
        self, model: str, prompt: str, system: str, temperature: float, max_tokens: int, config: dict[str, Any]
    ) -> tuple[str, float]:
        import os
        http = await self._get_http()
        api_key = os.environ.get(config["api_key_env"], "")
        if not api_key:
            raise RuntimeError(f"Missing env var: {config['api_key_env']}")

        messages = [{"role": "user", "content": prompt}]
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system

        resp = await http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = (
            input_tokens / 1000 * config["cost_per_1k_input"]
            + output_tokens / 1000 * config["cost_per_1k_output"]
        )
        return text, cost

    async def _call_openai_compat(
        self, model: str, prompt: str, system: str, temperature: float, max_tokens: int, config: dict[str, Any]
    ) -> tuple[str, float]:
        import os
        http = await self._get_http()
        base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        api_key = ""
        if config.get("api_key_env"):
            api_key = os.environ.get(config["api_key_env"], "")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers: dict[str, str] = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"

        resp = await http.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = (
            input_tokens / 1000 * config["cost_per_1k_input"]
            + output_tokens / 1000 * config["cost_per_1k_output"]
        )
        return text, cost

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None


class ChannelRegistry:
    def __init__(self, max_size: int = 100) -> None:
        self._channels: dict[str, asyncio.Queue[Any]] = {}
        self._max_size = max_size
        self._stats: dict[str, dict[str, int]] = {}

    def get(self, key: str) -> asyncio.Queue[Any]:
        if key not in self._channels:
            self._channels[key] = asyncio.Queue(maxsize=self._max_size)
            self._stats[key] = {"sent": 0, "received": 0}
        return self._channels[key]

    async def send(self, key: str, message: Any) -> None:
        await self.get(key).put(message)
        self._stats.setdefault(key, {"sent": 0, "received": 0})["sent"] += 1
        log.debug(f"Channel {key}: sent #{self._stats[key]['sent']}")

    async def receive(self, key: str, timeout: float = 30.0) -> Any:
        try:
            msg = await asyncio.wait_for(self.get(key).get(), timeout=timeout)
            self._stats.setdefault(key, {"sent": 0, "received": 0})["received"] += 1
            return msg
        except asyncio.TimeoutError:
            raise TimeoutError(f"Channel {key}: receive timeout after {timeout}s")

    @property
    def stats(self) -> dict[str, dict[str, int]]:
        return dict(self._stats)


class PerceptionEngine:
    def __init__(self, souls: dict[str, Any], channels: ChannelRegistry) -> None:
        self._souls = souls
        self._channels = channels
        self._cron_tasks: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self, rules: list[dict[str, Any]]) -> None:
        self._running = True
        for rule in rules:
            trigger = rule.get("trigger", {})
            action = rule.get("action", {})
            kind = trigger.get("kind", "")

            if kind == "cron":
                cron_expr = trigger.get("args", [""])[0] if trigger.get("args") else ""
                task = asyncio.create_task(self._cron_loop(cron_expr, action))
                self._cron_tasks.append(task)
            elif kind == "telegram":
                log.info(f"Perception: telegram trigger registered for {action}")
            elif kind == "system_error":
                log.info(f"Perception: system_error trigger registered → {action}")

    async def _cron_loop(self, expr: str, action: dict[str, Any]) -> None:
        interval = self._parse_cron_interval(expr)
        while self._running:
            await asyncio.sleep(interval)
            await self._execute_action(action)

    async def _execute_action(self, action: dict[str, Any]) -> None:
        kind = action.get("kind", "")
        target = action.get("target")

        if kind == "wake" and target:
            soul = self._souls.get(target)
            if soul and hasattr(soul, "instinct"):
                log.info(f"Perception: waking {target}")
                asyncio.create_task(soul.instinct())
        elif kind == "wake_all":
            for name, soul in self._souls.items():
                if hasattr(soul, "instinct"):
                    log.info(f"Perception: waking {name}")
                    asyncio.create_task(soul.instinct())
        elif kind == "alert":
            log.warning(f"Perception: alert → {target}")

    @staticmethod
    def _parse_cron_interval(expr: str) -> float:
        parts = expr.split()
        if len(parts) >= 1 and parts[0].startswith("*/"):
            try:
                return float(parts[0][2:]) * 60
            except ValueError:
                pass
        return 300.0

    async def stop(self) -> None:
        self._running = False
        for task in self._cron_tasks:
            task.cancel()
        self._cron_tasks.clear()


class BudgetExceededError(Exception):
    pass


class NousRuntime:
    def __init__(
        self,
        world_name: str = "Unknown",
        heartbeat_seconds: float = 300.0,
        budget_per_cycle: float = 1.0,
        laws: Optional[dict[str, Any]] = None,
    ) -> None:
        self.world_name = world_name
        self.heartbeat_seconds = heartbeat_seconds
        self.tools = ToolRegistry()
        self.llm = LLMCaller()
        self.channels = ChannelRegistry()
        self.costs = CostTracker(budget_per_cycle)
        self.perception: Optional[PerceptionEngine] = None
        self.souls: dict[str, Any] = {}
        self.laws = laws or {}
        self._running = False

    def boot(self) -> None:
        log.info(f"Booting NOUS runtime: {self.world_name}")
        tool_count = self.tools.scan_noosphere()
        log.info(f"Runtime ready: {tool_count} tools loaded")

    async def sense(self, soul_name: str, tool_name: str, *args: Any, **kwargs: Any) -> ToolResult:
        if not await self.costs.check_budget(soul_name):
            raise BudgetExceededError(
                f"{soul_name}: budget exceeded (${self.costs.current_cycle_cost:.4f} >= ${self.costs.budget_per_cycle:.4f})"
            )

        result = await self.tools.call(tool_name, *args, **kwargs)

        if result.cost > 0:
            await self.costs.record(result.cost, soul_name, f"sense:{tool_name}")

        if not result.success:
            log.error(f"{soul_name}.sense({tool_name}): {result.error}")

        return result

    async def think(
        self,
        soul_name: str,
        model: str,
        tier: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ) -> tuple[str, float]:
        if not await self.costs.check_budget(soul_name):
            raise BudgetExceededError(f"{soul_name}: budget exceeded")

        text, cost = await self.llm.call(model, tier, prompt, system, temperature)
        await self.costs.record(cost, soul_name, f"think:{model}")
        return text, cost

    def register_soul(self, name: str, soul: Any) -> None:
        self.souls[name] = soul
        if hasattr(soul, "_runtime"):
            soul._runtime = self
        log.info(f"Registered soul: {name}")

    async def run(self, perception_rules: Optional[list[dict[str, Any]]] = None) -> None:
        self._running = True
        self.boot()

        if perception_rules:
            self.perception = PerceptionEngine(self.souls, self.channels)
            await self.perception.start(perception_rules)

        log.info(f"Starting {len(self.souls)} souls")

        try:
            async with asyncio.TaskGroup() as tg:
                for name, soul in self.souls.items():
                    if hasattr(soul, "run"):
                        tg.create_task(soul.run())
                        log.info(f"Soul {name}: running")
        except* Exception as eg:
            for exc in eg.exceptions:
                log.error(f"Soul crashed: {exc}")
        finally:
            self._running = False
            if self.perception:
                await self.perception.stop()
            await self.llm.close()
            log.info(f"Runtime stopped. Total cost: ${self.costs.total_cost:.6f}")

    async def shutdown(self) -> None:
        self._running = False
        for soul in self.souls.values():
            if hasattr(soul, "_alive"):
                soul._alive = False
        if self.perception:
            await self.perception.stop()
        await self.llm.close()


_runtime: Optional[NousRuntime] = None


def get_runtime() -> NousRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NousRuntime()
    return _runtime


def init_runtime(**kwargs: Any) -> NousRuntime:
    global _runtime
    _runtime = NousRuntime(**kwargs)
    return _runtime
