"""
NOUS Runtime v2 — Εκτέλεση (Ektelesi)
========================================
Event-driven execution engine for NOUS programs.
Zero-cost sleep for listener souls. Circuit breaker for cost control.
Sense caching for deduplication. Graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

import httpx

log = logging.getLogger("nous.runtime")

TIER_COSTS: dict[str, dict[str, float]] = {
    "Tier0A": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    "Tier0B": {"input_per_1k": 0.0005, "output_per_1k": 0.0025},
    "Tier1":  {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "Tier2":  {"input_per_1k": 0.005, "output_per_1k": 0.025},
    "Tier3":     {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "Groq":      {"input_per_1k": 0.0003, "output_per_1k": 0.001},
    "Together":  {"input_per_1k": 0.0005, "output_per_1k": 0.002},
    "Fireworks": {"input_per_1k": 0.0002, "output_per_1k": 0.0008},
    "Cerebras":  {"input_per_1k": 0.0001, "output_per_1k": 0.0004},
}


class CircuitBreakerTripped(Exception):
    def __init__(self, soul_name: str, spent: float, ceiling: float) -> None:
        self.soul_name = soul_name
        self.spent = spent
        self.ceiling = ceiling
        super().__init__(
            f"Circuit breaker: {soul_name} pushed cycle cost to ${spent:.6f}, "
            f"ceiling is ${ceiling:.2f}"
        )


@dataclass
class CycleMetrics:
    cycle_id: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    total_cost: float = 0.0
    soul_costs: dict[str, float] = field(default_factory=dict)
    sense_calls: int = 0
    sense_cache_hits: int = 0
    messages_sent: int = 0
    circuit_broken: bool = False


class CostTracker:
    """Tracks cumulative cost within a single heartbeat cycle.
    Shared across all souls that execute in the same cycle cascade."""

    def __init__(self, ceiling: float) -> None:
        self._ceiling = ceiling
        self._spent = 0.0
        self._soul_costs: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def ceiling(self) -> float:
        return self._ceiling

    @property
    def remaining(self) -> float:
        return max(0.0, self._ceiling - self._spent)

    async def charge(self, soul_name: str, input_tokens: int, output_tokens: int, tier: str) -> float:
        tier_info = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
        cost = (
            (input_tokens / 1000) * tier_info["input_per_1k"]
            + (output_tokens / 1000) * tier_info["output_per_1k"]
        )
        async with self._lock:
            self._spent += cost
            self._soul_costs[soul_name] = self._soul_costs.get(soul_name, 0.0) + cost
            if self._spent > self._ceiling:
                raise CircuitBreakerTripped(soul_name, self._spent, self._ceiling)
        return cost

    async def pre_check(self, soul_name: str, est_input: int, est_output: int, tier: str) -> bool:
        tier_info = TIER_COSTS.get(tier, TIER_COSTS["Tier1"])
        est_cost = (
            (est_input / 1000) * tier_info["input_per_1k"]
            + (est_output / 1000) * tier_info["output_per_1k"]
        )
        async with self._lock:
            return (self._spent + est_cost) <= self._ceiling

    def reset(self) -> CycleMetrics:
        metrics = CycleMetrics(
            total_cost=self._spent,
            soul_costs=dict(self._soul_costs),
        )
        self._spent = 0.0
        self._soul_costs.clear()
        return metrics


class SenseCache:
    """Deduplicates sense calls within a single instinct execution.
    Key = (tool_name, frozenset(args)). Cleared after each instinct run."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, tool_name: str, args: dict[str, Any]) -> str:
        sorted_args = tuple(sorted(
            ((k, self._freeze(v)) for k, v in args.items()),
            key=lambda x: x[0]
        ))
        return f"{tool_name}:{sorted_args}"

    def _freeze(self, val: Any) -> Any:
        if isinstance(val, dict):
            return tuple(sorted(val.items()))
        if isinstance(val, list):
            return tuple(val)
        return val

    def get(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, Any]:
        key = self._make_key(tool_name, args)
        if key in self._cache:
            self._hits += 1
            return True, self._cache[key]
        self._misses += 1
        return False, None

    def put(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        key = self._make_key(tool_name, args)
        self._cache[key] = result

    def clear(self) -> tuple[int, int]:
        hits, misses = self._hits, self._misses
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        return hits, misses


class Channel:
    """Named async channel with backpressure."""

    def __init__(self, name: str, maxsize: int = 100) -> None:
        self.name = name
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self._total_sent = 0
        self._total_received = 0

    async def send(self, message: Any, timeout: float = 5.0) -> None:
        try:
            await asyncio.wait_for(self._queue.put(message), timeout=timeout)
            self._total_sent += 1
            log.debug(f"Channel [{self.name}]: sent ({self._queue.qsize()} queued)")
        except asyncio.TimeoutError:
            log.warning(f"Channel [{self.name}]: backpressure — send timeout after {timeout}s")
            raise

    async def receive(self, timeout: Optional[float] = None) -> Any:
        try:
            if timeout is not None:
                msg = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                msg = await self._queue.get()
            self._total_received += 1
            return msg
        except asyncio.TimeoutError:
            return None

    @property
    def pending(self) -> int:
        return self._queue.qsize()


class ChannelRegistry:
    """Thread-safe registry of named channels."""

    def __init__(self, default_maxsize: int = 100) -> None:
        self._channels: dict[str, Channel] = {}
        self._default_maxsize = default_maxsize
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> Channel:
        async with self._lock:
            if name not in self._channels:
                self._channels[name] = Channel(name, self._default_maxsize)
            return self._channels[name]

    async def send(self, name: str, message: Any) -> None:
        ch = await self.get(name)
        await ch.send(message)

    async def receive(self, name: str, timeout: Optional[float] = None) -> Any:
        ch = await self.get(name)
        return await ch.receive(timeout=timeout)


class SenseExecutor:
    """Executes sense calls via httpx or registered tool functions.
    Integrates with SenseCache for deduplication."""

    def __init__(self, cache: SenseCache) -> None:
        self._cache = cache
        self._tools: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    def register_tool(self, name: str, func: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        self._tools[name] = func

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def call(self, tool_name: str, args: dict[str, Any]) -> Any:
        cached, result = self._cache.get(tool_name, args)
        if cached:
            log.debug(f"Sense [{tool_name}]: cache hit")
            return result

        if tool_name in self._tools:
            result = await self._tools[tool_name](**args)
        elif tool_name == "http_get":
            client = await self._get_http()
            url = args.get("url", args.get("_pos_0", ""))
            resp = await client.get(str(url))
            result = resp.json() if "json" in resp.headers.get("content-type", "") else resp.text
        else:
            log.warning(f"Sense [{tool_name}]: no handler registered, returning None")
            result = None

        self._cache.put(tool_name, args, result)
        return result

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


@dataclass
class SoulWakeStrategy:
    HEARTBEAT = "heartbeat"
    LISTENER = "listener"


class SoulRunner:
    """Manages a single soul's lifecycle.
    Entrypoint souls wake on heartbeat. Listener souls wake on message."""

    def __init__(
        self,
        name: str,
        wake_strategy: str,
        instinct_fn: Callable[..., Coroutine[Any, Any, None]],
        heal_fn: Callable[[Exception], Coroutine[Any, Any, bool]],
        listen_channel: Optional[str] = None,
        heartbeat_seconds: float = 300.0,
        tier: str = "Tier1",
        cost_tracker: Optional[CostTracker] = None,
        sense_cache: Optional[SenseCache] = None,
    ) -> None:
        self.name = name
        self.wake_strategy = wake_strategy
        self._instinct = instinct_fn
        self._heal = heal_fn
        self._listen_channel = listen_channel
        self._heartbeat = heartbeat_seconds
        self._tier = tier
        self._cost_tracker = cost_tracker
        self._sense_cache = sense_cache
        self._alive = True
        self._cycle_count = 0
        self._last_latency_ms: float = 0.0
        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None
        self._telemetry_engine: Optional[Any] = None
        self._hot_reload_engine: Optional[Any] = None
        self._symbiosis_engine: Optional[Any] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    def set_shutdown_event(self, event: asyncio.Event) -> None:
        self._shutdown_event = event

    async def run(self, channels: ChannelRegistry) -> None:
        log.info(f"Soul [{self.name}]: started ({self.wake_strategy})")
        while self._alive:
            if self._shutdown_event and self._shutdown_event.is_set():
                log.info(f"Soul [{self.name}]: shutdown signal received")
                break

            try:
                if self.wake_strategy == SoulWakeStrategy.HEARTBEAT:
                    await self._run_heartbeat_cycle()
                else:
                    await self._run_listener_cycle(channels)
            except CircuitBreakerTripped as cb:
                log.warning(f"Soul [{self.name}]: {cb}")
                if self.wake_strategy == SoulWakeStrategy.HEARTBEAT:
                    await self._sleep_or_shutdown(self._heartbeat)
            except asyncio.CancelledError:
                log.info(f"Soul [{self.name}]: cancelled")
                break
            except Exception as e:
                log.error(f"Soul [{self.name}]: fatal error in run loop: {e}")
                recovered = await self._heal(e)
                if not recovered and self._immune_engine:
                    log.info(f"Soul [{self.name}]: heal failed, trying immune system")
                    try:
                        immune_ok, immune_result = await self._immune_engine.handle_error(
                            self.name, e, {"cycle_count": self._cycle_count}
                        )
                        if immune_ok:
                            self._immune_recoveries = getattr(self, '_immune_recoveries', 0) + 1
                            backoff = min(2 ** self._immune_recoveries, self._heartbeat)
                            log.info(f"Soul [{self.name}]: immune recovery succeeded — backoff {backoff}s before retry")
                            await self._sleep_or_shutdown(backoff)
                            recovered = True
                    except Exception as ie:
                        log.error(f"Soul [{self.name}]: immune engine error: {ie}")
                if not recovered:
                    log.critical(f"Soul [{self.name}]: unrecoverable, stopping")
                    self._alive = False

        log.info(f"Soul [{self.name}]: stopped after {self._cycle_count} cycles")

    async def _run_heartbeat_cycle(self) -> None:
        if self._sense_cache:
            self._sense_cache.clear()

        _t0 = time.time()
        await self._instinct()
        _latency_ms = (time.time() - _t0) * 1000
        self._cycle_count += 1
        self._last_latency_ms = _latency_ms
        log.info(f"Soul [{self.name}]: cycle {self._cycle_count} complete ({_latency_ms:.0f}ms)")
        if hasattr(self, '_telemetry_engine') and self._telemetry_engine and self._telemetry_engine.enabled:
            _tspan = self._telemetry_engine.start_span(
                kind=__import__('telemetry_engine').SpanKind.CYCLE,
                soul_name=self.name,
                cycle_count=self._cycle_count,
                latency_ms=round(_latency_ms, 2),
                wake_strategy=self.wake_strategy,
            )
            _tspan.end_time = time.time()
            _tspan.start_time = _t0
            import asyncio as _aio
            _aio.ensure_future(self._telemetry_engine.record(_tspan))
        if hasattr(self, '_dream_engine') and self._dream_engine:
            self._dream_engine.mark_active(self.name)
        await self._sleep_or_shutdown(self._heartbeat)

    async def _run_listener_cycle(self, channels: ChannelRegistry) -> None:
        if not self._listen_channel:
            log.error(f"Soul [{self.name}]: listener with no channel, falling back to heartbeat")
            await self._sleep_or_shutdown(self._heartbeat)
            return

        ch = await channels.get(self._listen_channel)
        log.debug(f"Soul [{self.name}]: waiting on channel [{self._listen_channel}]")

        msg = await ch.receive(timeout=self._heartbeat)
        if msg is None:
            return

        if self._sense_cache:
            self._sense_cache.clear()

        if self._cost_tracker:
            can_run = await self._cost_tracker.pre_check(self.name, 500, 200, self._tier)
            if not can_run:
                log.warning(f"Soul [{self.name}]: pre-check failed, budget exhausted, skipping")
                return

        _t0 = time.time()
        await self._instinct()
        _latency_ms = (time.time() - _t0) * 1000
        self._cycle_count += 1
        self._last_latency_ms = _latency_ms
        log.info(f"Soul [{self.name}]: cycle {self._cycle_count} complete (message-driven, {_latency_ms:.0f}ms)")

    async def _sleep_or_shutdown(self, seconds: float) -> None:
        if self._shutdown_event:
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=seconds)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(seconds)

    def stop(self) -> None:
        self._alive = False


class NousRuntime:
    """Top-level runtime orchestrator.
    Manages soul lifecycle, channels, cost tracking, graceful shutdown."""

    def __init__(
        self,
        world_name: str = "Unknown",
        heartbeat_seconds: float = 300.0,
        cost_ceiling: float = 0.10,
        channel_maxsize: int = 100,
    ) -> None:
        self.world_name = world_name
        self.heartbeat_seconds = heartbeat_seconds
        self.cost_ceiling = cost_ceiling

        self.channels = ChannelRegistry(default_maxsize=channel_maxsize)
        self.cost_tracker = CostTracker(ceiling=cost_ceiling)
        self.sense_cache = SenseCache()
        self.sense_executor = SenseExecutor(cache=self.sense_cache)

        self._runners: list[SoulRunner] = []
        self._shutdown = asyncio.Event()
        self._cycle_id = 0
        self._metrics_history: list[CycleMetrics] = []
        self._mitosis_engine: Optional[Any] = None
        self._immune_engine: Optional[Any] = None
        self._dream_engine: Optional[Any] = None
        self._telemetry_engine: Optional[Any] = None

    def add_soul(self, runner: SoulRunner) -> None:
        runner.set_shutdown_event(self._shutdown)
        runner._cost_tracker = self.cost_tracker
        runner._sense_cache = self.sense_cache
        runner._immune_engine = self._immune_engine
        runner._telemetry_engine = self._telemetry_engine
        self._runners.append(runner)

    def remove_soul(self, name: str) -> bool:
        for i, runner in enumerate(self._runners):
            if runner.name == name:
                runner.stop()
                self._runners.pop(i)
                log.info(f"Soul [{name}]: removed from runtime ({len(self._runners)} remaining)")
                return True
        log.warning(f"Soul [{name}]: not found in runtime for removal")
        return False

    def register_sense(self, name: str, func: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        self.sense_executor.register_tool(name, func)

    async def run(self) -> None:
        log.info(f"═══ NOUS Runtime v2 — {self.world_name} ═══")
        log.info(f"  Heartbeat:     {self.heartbeat_seconds}s")
        log.info(f"  Cost ceiling:  ${self.cost_ceiling:.2f}/cycle")
        log.info(f"  Souls:         {len(self._runners)}")
        for r in self._runners:
            log.info(f"    [{r.name}] strategy={r.wake_strategy}")

        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            try:
                loop.add_signal_handler(
                    getattr(signal, sig_name),
                    self._handle_shutdown,
                )
            except (NotImplementedError, AttributeError):
                pass

        for runner in self._runners:
            if self._immune_engine and runner._immune_engine is None:
                runner._immune_engine = self._immune_engine

        if self._dream_engine:
            async def _check_dream_cache(**kwargs):
                soul_name = kwargs.get("soul", "")
                query = kwargs.get("query", "")
                if not self._dream_engine or not soul_name:
                    return ""
                insight = self._dream_engine.check_cache(soul_name, query)
                if insight:
                    return insight.precomputed_result
                return ""
            self.sense_executor.register_tool("check_dream_cache", _check_dream_cache)
            self.sense_executor.register_tool("dream_cache", _check_dream_cache)

        try:
            async with asyncio.TaskGroup() as tg:
                for runner in self._runners:
                    tg.create_task(runner.run(self.channels))
                tg.create_task(self._heartbeat_cost_reset())
                if self._mitosis_engine:
                    tg.create_task(self._mitosis_engine.run())
                if self._immune_engine:
                    tg.create_task(self._immune_engine.run())
                if self._dream_engine:
                    tg.create_task(self._dream_engine.run())
                if self._telemetry_engine:
                    tg.create_task(self._telemetry_engine.run())
                if self._symbiosis_engine:
                    tg.create_task(self._symbiosis_engine.run())
                if self._hot_reload_engine:
                    tg.create_task(self._hot_reload_engine.run())
        except* CircuitBreakerTripped as eg:
            for exc in eg.exceptions:
                log.warning(f"Circuit breaker ended cycle: {exc}")
        except* asyncio.CancelledError:
            log.info("Runtime cancelled")
        finally:
            await self.sense_executor.close()
            log.info(f"═══ NOUS Runtime shutdown complete ═══")

    async def _heartbeat_cost_reset(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self.heartbeat_seconds)
                break
            except asyncio.TimeoutError:
                metrics = self.cost_tracker.reset()
                self._cycle_id += 1
                metrics.cycle_id = self._cycle_id
                self._metrics_history.append(metrics)
                if len(self._metrics_history) > 1000:
                    self._metrics_history = self._metrics_history[-500:]
                hits, misses = self.sense_cache.clear()
                log.info(
                    f"Cycle {self._cycle_id} summary: "
                    f"cost=${metrics.total_cost:.6f}/{self.cost_ceiling:.2f} "
                    f"sense_cache={hits}hit/{misses}miss"
                )

    def _handle_shutdown(self) -> None:
        log.info("Shutdown signal received")
        self._shutdown.set()
        if self._mitosis_engine:
            self._mitosis_engine.stop()
        if self._immune_engine:
            self._immune_engine.stop()
        if self._dream_engine:
            self._dream_engine.stop()
        if self._telemetry_engine:
            self._telemetry_engine.stop()
        if self._symbiosis_engine:
            self._symbiosis_engine.stop()
        if self._hot_reload_engine:
            self._hot_reload_engine.stop()
        for runner in self._runners:
            runner.stop()

    async def shutdown(self) -> None:
        self._handle_shutdown()


def determine_wake_strategies(
    souls: list[str],
    routes: list[tuple[str, str]],
) -> dict[str, str]:
    """Analyze nervous_system routes to classify souls.
    Souls with no incoming routes = entrypoint (heartbeat).
    Souls with incoming routes = listener (message-driven)."""
    has_incoming: set[str] = set()
    for src, tgt in routes:
        has_incoming.add(tgt)

    strategies: dict[str, str] = {}
    for soul in souls:
        if soul in has_incoming:
            strategies[soul] = SoulWakeStrategy.LISTENER
        else:
            strategies[soul] = SoulWakeStrategy.HEARTBEAT
    return strategies


def determine_listen_channels(
    soul_name: str,
    routes: list[tuple[str, str]],
) -> Optional[str]:
    """Find the primary listen channel for a listener soul.
    Returns the first source that routes into this soul."""
    for src, tgt in routes:
        if tgt == soul_name:
            return src
    return None


class DistributedChannelBridge:
    """Wraps DistributedChannelRegistry with the same interface as ChannelRegistry.
    SoulRunner calls .get(), .send(), .receive() — this bridges to TCP transport."""

    def __init__(self, dist_registry: Any) -> None:
        self._dist = dist_registry
        self._local_channels: dict[str, Channel] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> Channel:
        async with self._lock:
            if name not in self._local_channels:
                ch = Channel(name)
                self._local_channels[name] = ch
            return self._local_channels[name]

    async def send(self, name: str, message: Any) -> None:
        await self._dist.send(name, message)

    async def receive(self, name: str, timeout: Optional[float] = None) -> Any:
        return await self._dist.receive(name, timeout=timeout)


class DistributedRuntime(NousRuntime):
    """NousRuntime subclass for multi-machine execution.
    Replaces local ChannelRegistry with TCP-backed DistributedChannelRegistry."""

    def __init__(
        self,
        world_name: str = "Unknown",
        heartbeat_seconds: float = 300.0,
        cost_ceiling: float = 0.10,
        channel_maxsize: int = 100,
        node_name: str = "local",
        node_host: str = "0.0.0.0",
        node_port: int = 9100,
        topology: Optional[list[Any]] = None,
        local_souls: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            world_name=world_name,
            heartbeat_seconds=heartbeat_seconds,
            cost_ceiling=cost_ceiling,
            channel_maxsize=channel_maxsize,
        )
        self.node_name = node_name
        self.node_host = node_host
        self.node_port = node_port
        self._topology_nodes = topology or []
        self._local_soul_names = local_souls or []
        self._dist_registry: Optional[Any] = None
        self._bridge: Optional[DistributedChannelBridge] = None

    def _build_dist_registry(self) -> None:
        from distributed import DistributedChannelRegistry, NodeInfo
        nodes = []
        for n in self._topology_nodes:
            if isinstance(n, dict):
                nodes.append(NodeInfo(
                    name=n["name"],
                    host=n["host"],
                    port=n.get("port", 9100),
                    souls=n.get("souls", []),
                ))
            elif isinstance(n, NodeInfo):
                nodes.append(n)
            else:
                nodes.append(n)
        self._dist_registry = DistributedChannelRegistry(
            local_node=self.node_name,
            local_souls=self._local_soul_names,
            topology=nodes,
        )
        self._bridge = DistributedChannelBridge(self._dist_registry)
        self.channels = self._bridge

    def set_route_map(self, routes: list[tuple[str, str]], speak_channels: dict[str, str]) -> None:
        if self._dist_registry:
            self._dist_registry.set_route_map(routes, speak_channels)

    async def run(self) -> None:
        self._build_dist_registry()

        log.info(f"═══ NOUS Distributed Runtime — {self.world_name} ═══")
        log.info(f"  Node:          {self.node_name}")
        log.info(f"  Listen:        {self.node_host}:{self.node_port}")
        log.info(f"  Heartbeat:     {self.heartbeat_seconds}s")
        log.info(f"  Cost ceiling:  ${self.cost_ceiling:.2f}/cycle")
        log.info(f"  Local souls:   {self._local_soul_names}")
        log.info(f"  Cluster nodes: {len(self._topology_nodes)}")

        await self._dist_registry.start(self.node_host, self.node_port)

        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            try:
                loop.add_signal_handler(
                    getattr(signal, sig_name),
                    self._handle_shutdown,
                )
            except (NotImplementedError, AttributeError):
                pass

        connection_results = await self._dist_registry.connect_all()
        for name, ok in connection_results.items():
            status = "connected" if ok else "FAILED"
            log.info(f"  → {name}: {status}")

        try:
            async with asyncio.TaskGroup() as tg:
                for runner in self._runners:
                    tg.create_task(runner.run(self.channels))
                tg.create_task(self._heartbeat_cost_reset())
        except* CircuitBreakerTripped as eg:
            for exc in eg.exceptions:
                log.warning(f"Circuit breaker ended cycle: {exc}")
        except* asyncio.CancelledError:
            log.info("Runtime cancelled")
        finally:
            await self._dist_registry.stop()
            await self.sense_executor.close()
            log.info(f"═══ NOUS Distributed Runtime shutdown complete ═══")

    async def shutdown(self) -> None:
        self._handle_shutdown()

    async def health(self) -> dict[str, Any]:
        if self._dist_registry:
            return await self._dist_registry.health()
        return {"node": self.node_name, "status": "not_started"}
