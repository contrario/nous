"""
Noesis Oracle Bridge — Χρησμός (Chresmos)
==========================================
When Noesis doesn't know, she asks an oracle (external LLM).
She learns the answer. Next time, she answers alone.

Tiered strategy:
    Tier3 → Ollama local (free, fast, private)
    Tier2 → OpenRouter free (gemini-flash)
    Tier1 → OpenRouter paid (deepseek-r1)
    Tier0A → Anthropic (claude-haiku)

Each query costs less than the previous oracle call for the same topic.
Eventually: zero oracle calls.

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("nous.oracle")

_ENV_PATH = Path("/opt/aetherlang_agents/.env")


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env()


@dataclass
class OracleCall:
    tier: str
    model: str
    query: str
    response: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    elapsed_ms: float
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: str = ""


@dataclass
class OracleStats:
    total_calls: int = 0
    total_cost: float = 0.0
    calls_by_tier: dict[str, int] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    last_call: Optional[OracleCall] = None


SYSTEM_PROMPT: str = (
    "You are a knowledge oracle. Answer the question concisely and factually. "
    "Give direct information in 2-4 sentences. No preamble. No caveats. "
    "If you don't know, say 'I don't know.' "
    "Respond in the same language as the question."
)


class OracleTier:
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key_env: str,
        cost_per_1k_in: float = 0.0,
        cost_per_1k_out: float = 0.0,
        timeout: float = 15.0,
        headers_fn: Optional[callable] = None,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.model = model
        self.api_key_env = api_key_env
        self.cost_per_1k_in = cost_per_1k_in
        self.cost_per_1k_out = cost_per_1k_out
        self.timeout = timeout
        self.headers_fn = headers_fn

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def call(self, query: str) -> OracleCall:
        t0 = time.perf_counter()
        if not self.available:
            return OracleCall(
                tier=self.name, model=self.model, query=query, response="",
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                elapsed_ms=0.0, success=False, error=f"No API key: {self.api_key_env}",
            )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.headers_fn:
            headers = self.headers_fn(self.api_key)

        is_anthropic = "anthropic" in self.base_url

        if is_anthropic:
            body: dict[str, Any] = {
                "model": self.model,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": query},
                ],
            }
        else:
            body = {
                "model": self.model,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
            }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.base_url,
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            log.warning(f"Oracle {self.name} failed: {e}")
            return OracleCall(
                tier=self.name, model=self.model, query=query, response="",
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                elapsed_ms=elapsed, success=False, error=str(e),
            )

        elapsed = (time.perf_counter() - t0) * 1000
        response_text = self._extract_response(data)
        tokens_in = self._extract_tokens_in(data)
        tokens_out = self._extract_tokens_out(data)
        cost = (tokens_in / 1000 * self.cost_per_1k_in) + (tokens_out / 1000 * self.cost_per_1k_out)

        return OracleCall(
            tier=self.name, model=self.model, query=query, response=response_text,
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
            elapsed_ms=elapsed, success=True,
        )

    def _extract_response(self, data: dict[str, Any]) -> str:
        if "content" in data:
            blocks = data["content"]
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
        if "choices" in data:
            choices = data["choices"]
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                return msg.get("content", "")
        return ""

    def _extract_tokens_in(self, data: dict[str, Any]) -> int:
        usage = data.get("usage", {})
        return usage.get("input_tokens", usage.get("prompt_tokens", 0))

    def _extract_tokens_out(self, data: dict[str, Any]) -> int:
        usage = data.get("usage", {})
        return usage.get("output_tokens", usage.get("completion_tokens", 0))


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


TIERS: list[OracleTier] = [
    OracleTier(
        name="Tier2",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="google/gemini-2.0-flash-exp:free",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=15.0,
    ),
    OracleTier(
        name="Tier1",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="deepseek/deepseek-r1",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.00055,
        cost_per_1k_out=0.0022,
        timeout=20.0,
    ),
    OracleTier(
        name="Tier0A",
        base_url="https://api.anthropic.com/v1/messages",
        model="claude-3-haiku-20240307",
        api_key_env="ANTHROPIC_API_KEY",
        cost_per_1k_in=0.0008,
        cost_per_1k_out=0.004,
        timeout=15.0,
        headers_fn=_anthropic_headers,
    ),
]


class Oracle:
    def __init__(
        self,
        tiers: Optional[list[OracleTier]] = None,
        budget_per_query: float = 0.01,
        log_path: Optional[Path] = None,
    ) -> None:
        self.tiers = tiers or TIERS
        self.budget_per_query = budget_per_query
        self.log_path = log_path or Path("/opt/aetherlang_agents/nous/oracle_log.json")
        self.history: list[OracleCall] = []
        self._stats = OracleStats()

    def ask(self, query: str) -> str:
        for tier in self.tiers:
            if not tier.available:
                log.debug(f"Oracle {tier.name} skipped: no API key")
                continue

            result = tier.call(query)

            if result.success and result.response:
                self._record(result)
                log.info(
                    f"Oracle {tier.name} answered: "
                    f"{result.tokens_in}+{result.tokens_out} tokens, "
                    f"${result.cost_usd:.4f}, {result.elapsed_ms:.0f}ms"
                )
                return result.response

            log.warning(f"Oracle {tier.name} failed: {result.error}")

        log.error("All oracle tiers failed")
        return ""

    def _record(self, call: OracleCall) -> None:
        self.history.append(call)
        self._stats.total_calls += 1
        self._stats.total_cost += call.cost_usd
        tier_key = call.tier
        self._stats.calls_by_tier[tier_key] = self._stats.calls_by_tier.get(tier_key, 0) + 1
        latencies = [c.elapsed_ms for c in self.history if c.success]
        self._stats.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
        self._stats.last_call = call
        self._save_log()

    def _save_log(self) -> None:
        try:
            data = []
            for c in self.history[-100:]:
                data.append({
                    "tier": c.tier,
                    "model": c.model,
                    "query": c.query[:200],
                    "response": c.response[:300],
                    "tokens_in": c.tokens_in,
                    "tokens_out": c.tokens_out,
                    "cost_usd": round(c.cost_usd, 6),
                    "elapsed_ms": round(c.elapsed_ms, 1),
                    "timestamp": c.timestamp,
                    "success": c.success,
                    "error": c.error,
                })
            self.log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug(f"Failed to save oracle log: {e}")

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._stats.total_calls,
            "total_cost_usd": round(self._stats.total_cost, 6),
            "calls_by_tier": self._stats.calls_by_tier,
            "avg_latency_ms": round(self._stats.avg_latency_ms, 1),
            "available_tiers": [t.name for t in self.tiers if t.available],
        }


def create_oracle_fn(
    budget_per_query: float = 0.01,
    log_path: Optional[Path] = None,
) -> tuple[callable, Oracle]:
    oracle = Oracle(
        budget_per_query=budget_per_query,
        log_path=log_path,
    )
    return oracle.ask, oracle


def create_noesis_with_oracle(
    lattice_path: Optional[Path] = None,
    oracle_threshold: float = 0.3,
    budget_per_query: float = 0.01,
) -> tuple:
    from noesis_engine import NoesisEngine

    oracle_fn, oracle = create_oracle_fn(budget_per_query=budget_per_query)

    engine = NoesisEngine(
        oracle_fn=oracle_fn,
        oracle_threshold=oracle_threshold,
    )

    if lattice_path and lattice_path.exists():
        engine.load(lattice_path)

    return engine, oracle
