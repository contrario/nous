"""
NOUS Dream Engine — Ονειρεύομαι (Oneirevome)
==============================================
Speculative pre-computation during idle time.
When a soul has no work, it enters REM state:
1. Analyzes recent memory and past signals
2. Uses a cheap dream_mind LLM to pre-compute likely scenarios
3. Stores insights in DreamCache
4. On next real cycle, checks cache first — instant response if hit
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

import httpx

log = logging.getLogger("nous.dream")


@dataclass
class DreamInsight:
    key: str
    scenario: str
    precomputed_result: Any
    confidence: float
    created_at: float
    soul_name: str
    dream_mind: str
    cost_estimate: float = 0.0
    hits: int = 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


def _insight_key(scenario: str) -> str:
    return hashlib.sha256(scenario.lower().strip().encode()).hexdigest()[:16]


@dataclass
class DreamConfig:
    enabled: bool = True
    trigger_idle_sec: int = 30
    dream_mind_model: str = "deepseek-chat"
    dream_mind_tier: str = "Tier1"
    max_cache: int = 20
    speculation_depth: int = 3


@dataclass
class DreamMetrics:
    total_dreams: int = 0
    total_insights: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_cost: float = 0.0
    time_dreaming_sec: float = 0.0


class DreamCache:
    """Stores pre-computed insights with LRU eviction."""

    def __init__(self, max_size: int = 20) -> None:
        self._cache: dict[str, DreamInsight] = {}
        self._max_size = max_size

    def get(self, scenario: str) -> Optional[DreamInsight]:
        key = _insight_key(scenario)
        insight = self._cache.get(key)
        if insight:
            insight.hits += 1
            return insight
        return None

    def put(self, insight: DreamInsight) -> None:
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
            del self._cache[oldest_key]
        self._cache[insight.key] = insight

    def check_relevance(self, current_input: str, threshold: float = 0.15) -> Optional[DreamInsight]:
        current_words = set(current_input.lower().split())
        best: Optional[DreamInsight] = None
        best_score = 0.0
        for insight in self._cache.values():
            scenario_words = set(insight.scenario.lower().split())
            if not scenario_words:
                continue
            overlap = len(current_words & scenario_words)
            score = overlap / max(len(scenario_words), 1)
            if score > threshold and score > best_score:
                best = insight
                best_score = score
        return best

    @property
    def size(self) -> int:
        return len(self._cache)

    def all_insights(self) -> list[DreamInsight]:
        return list(self._cache.values())

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count


TIER_CONFIGS: dict[str, dict[str, str]] = {
    "Tier0A": {"env": "ANTHROPIC_API_KEY", "url": "https://api.anthropic.com/v1/messages", "type": "anthropic"},
    "Tier0B": {"env": "OPENAI_API_KEY", "url": "https://api.openai.com/v1/chat/completions", "type": "openai"},
    "Tier1": {"env": "DEEPSEEK_API_KEY", "url": "https://api.deepseek.com/v1/chat/completions", "type": "openai"},
    "Tier2": {"env": "GEMINI_API_KEY", "url": "https://generativelanguage.googleapis.com/v1beta/models", "type": "gemini"},
    "Tier3": {"env": "OLLAMA_HOST", "url": "http://localhost:11434/api/chat", "type": "ollama"},
    "Groq": {"env": "GROQ_API_KEY", "url": "https://api.groq.com/openai/v1/chat/completions", "type": "openai"},
    "Together": {"env": "TOGETHER_API_KEY", "url": "https://api.together.xyz/v1/chat/completions", "type": "openai"},
    "Fireworks": {"env": "FIREWORKS_API_KEY", "url": "https://api.fireworks.ai/inference/v1/chat/completions", "type": "openai"},
    "Cerebras": {"env": "CEREBRAS_API_KEY", "url": "https://api.cerebras.ai/v1/chat/completions", "type": "openai"},
}


class DreamEngine:
    """Manages speculative pre-computation for idle souls."""

    def __init__(self, runtime: Any) -> None:
        self._load_env()

        self._runtime = runtime
        self._configs: dict[str, DreamConfig] = {}
        self._caches: dict[str, DreamCache] = {}
        self._metrics: dict[str, DreamMetrics] = {}
        self._memory_snapshots: dict[str, dict[str, Any]] = {}
        self._last_active: dict[str, float] = {}
        self._dreaming: set[str] = set()
        self._alive = True


    @staticmethod
    def _load_env() -> None:
        from pathlib import Path
        env_file = Path("/opt/aetherlang_agents/.env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    def register(
        self,
        soul_name: str,
        config: DreamConfig,
    ) -> None:
        self._configs[soul_name] = config
        self._caches[soul_name] = DreamCache(max_size=config.max_cache)
        self._metrics[soul_name] = DreamMetrics()
        self._last_active[soul_name] = time.time()
        log.info(
            f"Dream registered: {soul_name} "
            f"(idle_trigger={config.trigger_idle_sec}s, "
            f"mind={config.dream_mind_model}@{config.dream_mind_tier}, "
            f"depth={config.speculation_depth})"
        )

    def mark_active(self, soul_name: str) -> None:
        self._last_active[soul_name] = time.time()

    def update_memory(self, soul_name: str, memory: dict[str, Any]) -> None:
        self._memory_snapshots[soul_name] = dict(memory)

    def check_cache(self, soul_name: str, current_input: str) -> Optional[DreamInsight]:
        cache = self._caches.get(soul_name)
        metrics = self._metrics.get(soul_name)
        if not cache or not metrics:
            return None
        insight = cache.check_relevance(current_input)
        if insight:
            metrics.cache_hits += 1
            log.info(
                f"Dream [{soul_name}]: CACHE HIT — "
                f"scenario matched (confidence={insight.confidence:.2f}, "
                f"age={insight.age_seconds:.0f}s)"
            )
            return insight
        metrics.cache_misses += 1
        return None

    async def run(self) -> None:
        log.info("Dream engine started")
        while self._alive:
            try:
                await asyncio.sleep(5)
                await self._check_idle_souls()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Dream engine error: {e}")

    async def _check_idle_souls(self) -> None:
        now = time.time()
        for soul_name, config in self._configs.items():
            if not config.enabled:
                continue
            if soul_name in self._dreaming:
                continue
            idle_time = now - self._last_active.get(soul_name, now)
            if idle_time >= config.trigger_idle_sec:
                self._dreaming.add(soul_name)
                asyncio.create_task(self._dream(soul_name, config))

    async def _dream(self, soul_name: str, config: DreamConfig) -> None:
        metrics = self._metrics[soul_name]
        cache = self._caches[soul_name]
        memory = self._memory_snapshots.get(soul_name, {})

        t0 = time.time()
        metrics.total_dreams += 1

        log.info(
            f"Dream [{soul_name}]: entering REM state "
            f"(depth={config.speculation_depth})"
        )

        try:
            scenarios = self._generate_scenarios(soul_name, memory, config)

            for scenario in scenarios[:config.speculation_depth]:
                try:
                    result = await self._speculate(
                        soul_name, scenario, memory, config
                    )
                    if result:
                        insight = DreamInsight(
                            key=_insight_key(scenario),
                            scenario=scenario,
                            precomputed_result=result,
                            confidence=result.get("confidence", 0.5),
                            created_at=time.time(),
                            soul_name=soul_name,
                            dream_mind=f"{config.dream_mind_model}@{config.dream_mind_tier}",
                        )
                        cache.put(insight)
                        metrics.total_insights += 1
                        log.info(
                            f"Dream [{soul_name}]: insight cached — "
                            f"\"{scenario[:60]}\" "
                            f"(confidence={insight.confidence:.2f})"
                        )
                except Exception as e:
                    log.warning(f"Dream [{soul_name}]: speculation failed: {e}")

        finally:
            elapsed = time.time() - t0
            metrics.time_dreaming_sec += elapsed
            self._dreaming.discard(soul_name)
            log.info(
                f"Dream [{soul_name}]: REM complete — "
                f"{cache.size} insights cached, "
                f"{elapsed:.1f}s dreaming"
            )

    def _generate_scenarios(
        self,
        soul_name: str,
        memory: dict[str, Any],
        config: DreamConfig,
    ) -> list[str]:
        scenarios: list[str] = []

        for key, value in memory.items():
            if isinstance(value, (int, float)) and value > 0:
                scenarios.append(
                    f"What happens when {key} reaches {value * 2}?"
                )
                scenarios.append(
                    f"What if {key} drops to zero?"
                )
            elif isinstance(value, str) and len(value) > 3:
                scenarios.append(
                    f"What are the implications of {key}={value}?"
                )
            elif isinstance(value, list):
                scenarios.append(
                    f"What patterns exist in {key} with {len(value)} items?"
                )

        if not scenarios:
            scenarios = [
                f"What is the most likely next input for {soul_name}?",
                f"What errors might {soul_name} encounter next?",
                f"What optimization could improve {soul_name} performance?",
            ]

        return scenarios[:config.speculation_depth * 2]

    async def _speculate(
        self,
        soul_name: str,
        scenario: str,
        memory: dict[str, Any],
        config: DreamConfig,
    ) -> Optional[dict[str, Any]]:
        mem_summary = ", ".join(
            f"{k}={v}" for k, v in list(memory.items())[:10]
        ) if memory else "empty"

        prompt = (
            f"You are a speculative reasoning engine for an AI agent named '{soul_name}'.\n"
            f"Current memory state: {mem_summary}\n\n"
            f"Scenario: {scenario}\n\n"
            f"Provide a brief pre-computed response that the agent could use "
            f"if this scenario occurs. Respond in JSON format:\n"
            f'{{"action": "...", "data": ..., "confidence": 0.0-1.0, "reasoning": "..."}}\n'
            f"Keep response under 100 words. Only output JSON."
        )

        response = await self._call_dream_llm(config, prompt)
        if not response:
            return None

        try:
            import json
            clean = response.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])
            result = json.loads(clean)
            if isinstance(result, dict):
                if "confidence" not in result:
                    result["confidence"] = 0.5
                return result
        except (json.JSONDecodeError, ValueError):
            return {
                "action": "raw_insight",
                "data": response[:200],
                "confidence": 0.3,
                "reasoning": "unparsed LLM response",
            }

        return None

    async def _call_dream_llm(
        self,
        config: DreamConfig,
        prompt: str,
    ) -> Optional[str]:
        tier = config.dream_mind_tier
        tier_config = TIER_CONFIGS.get(tier)

        if not tier_config:
            providers = [
                ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat", "openai"),
                ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest", "openai"),
            ]
        else:
            api_key = os.environ.get(tier_config["env"], "")
            if api_key:
                providers = [(tier_config["env"], tier_config["url"], config.dream_mind_model, tier_config["type"])]
            else:
                providers = [
                    ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat", "openai"),
                    ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest", "openai"),
                ]

        for env_key, url, model, api_type in providers:
            api_key = os.environ.get(env_key, "")
            if not api_key:
                continue
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    if api_type == "anthropic":
                        headers = {
                            "x-api-key": api_key,
                            "content-type": "application/json",
                            "anthropic-version": "2023-06-01",
                        }
                        payload = {
                            "model": model,
                            "max_tokens": 200,
                            "messages": [{"role": "user", "content": prompt}],
                        }
                        resp = await client.post(url, json=payload, headers=headers)
                        data = resp.json()
                        return data["content"][0]["text"]
                    else:
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }
                        payload = {
                            "model": model,
                            "max_tokens": 200,
                            "temperature": 0.7,
                            "messages": [{"role": "user", "content": prompt}],
                        }
                        resp = await client.post(url, json=payload, headers=headers)
                        data = resp.json()
                        return data["choices"][0]["message"]["content"]
            except Exception as e:
                log.warning(f"Dream LLM call failed ({env_key}): {e}")
                continue

        log.warning("Dream: no LLM provider available")
        return None

    def stop(self) -> None:
        self._alive = False

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {"souls": {}}
        for soul_name in self._configs:
            cache = self._caches[soul_name]
            metrics = self._metrics[soul_name]
            config = self._configs[soul_name]
            hit_rate = (
                f"{metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses) * 100:.0f}%"
                if (metrics.cache_hits + metrics.cache_misses) > 0
                else "N/A"
            )
            result["souls"][soul_name] = {
                "enabled": config.enabled,
                "dream_mind": f"{config.dream_mind_model}@{config.dream_mind_tier}",
                "cached_insights": cache.size,
                "total_dreams": metrics.total_dreams,
                "total_insights": metrics.total_insights,
                "cache_hits": metrics.cache_hits,
                "cache_misses": metrics.cache_misses,
                "hit_rate": hit_rate,
                "time_dreaming": f"{metrics.time_dreaming_sec:.1f}s",
                "insights": [
                    {
                        "scenario": i.scenario[:80],
                        "confidence": i.confidence,
                        "age": f"{i.age_seconds:.0f}s",
                        "hits": i.hits,
                    }
                    for i in cache.all_insights()
                ],
            }
        return result

    def print_status(self) -> str:
        lines: list[str] = []
        lines.append("")
        lines.append("  ═══ NOUS Dream System Status ═══")
        lines.append("")

        for soul_name in sorted(self._configs):
            config = self._configs[soul_name]
            cache = self._caches[soul_name]
            metrics = self._metrics[soul_name]
            is_dreaming = soul_name in self._dreaming

            state = "REM" if is_dreaming else "AWAKE"
            hit_rate = (
                f"{metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses) * 100:.0f}%"
                if (metrics.cache_hits + metrics.cache_misses) > 0
                else "N/A"
            )

            lines.append(f"  ── {soul_name} [{state}] ──")
            lines.append(f"  Dream mind:      {config.dream_mind_model}@{config.dream_mind_tier}")
            lines.append(f"  Idle trigger:    {config.trigger_idle_sec}s")
            lines.append(f"  Cached insights: {cache.size}/{config.max_cache}")
            lines.append(f"  Dreams:          {metrics.total_dreams}")
            lines.append(f"  Cache hit rate:  {hit_rate}")
            lines.append(f"  Time dreaming:   {metrics.time_dreaming_sec:.1f}s")

            for insight in cache.all_insights()[:3]:
                lines.append(
                    f"    💭 \"{insight.scenario[:50]}\" "
                    f"conf={insight.confidence:.2f} hits={insight.hits}"
                )
            lines.append("")

        lines.append("  ══════════════════════════════════════")
        return "\n".join(lines)
