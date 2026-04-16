"""
NOUS Runtime v2 — Ψυχή (Psyche)
=================================
Executes .nous programs with real LLM calls, Noesis integration,
and hard budget controls.

Modes:
  dry-run  — logs what would happen, $0 cost
  live     — real API calls with budget guard

Author: Hlias Staurou + Claude | NOUS Project | April 2026
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

log = logging.getLogger("nous.runtime")

ENV_PATH = Path("/opt/aetherlang_agents/.env")


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
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
class BudgetGuard:
    daily_limit: float = 0.33
    monthly_limit: float = 10.0
    _today_spend: float = 0.0
    _month_spend: float = 0.0
    _today_date: str = ""
    _month_str: str = ""
    _log_path: Path = field(default_factory=lambda: Path("/opt/aetherlang_agents/nous/runtime_budget.json"))

    def __post_init__(self) -> None:
        self._today_date = time.strftime("%Y-%m-%d")
        self._month_str = time.strftime("%Y-%m")
        self._load()

    def _load(self) -> None:
        if self._log_path.exists():
            try:
                data = json.loads(self._log_path.read_text())
                if data.get("date") == self._today_date:
                    self._today_spend = data.get("today_spend", 0.0)
                if data.get("month") == self._month_str:
                    self._month_spend = data.get("month_spend", 0.0)
            except Exception:
                pass

    def _save(self) -> None:
        try:
            self._log_path.write_text(json.dumps({
                "date": self._today_date,
                "today_spend": round(self._today_spend, 6),
                "month": self._month_str,
                "month_spend": round(self._month_spend, 6),
            }))
        except Exception:
            pass

    def can_spend(self, amount: float) -> bool:
        today = time.strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_spend = 0.0
        month = time.strftime("%Y-%m")
        if month != self._month_str:
            self._month_str = month
            self._month_spend = 0.0
        if self._today_spend + amount > self.daily_limit:
            log.warning(f"BUDGET: daily limit ${self.daily_limit} reached (${self._today_spend:.4f} spent)")
            return False
        if self._month_spend + amount > self.monthly_limit:
            log.warning(f"BUDGET: monthly limit ${self.monthly_limit} reached (${self._month_spend:.4f} spent)")
            return False
        return True

    def record(self, amount: float) -> None:
        self._today_spend += amount
        self._month_spend += amount
        self._save()

    @property
    def status(self) -> dict[str, Any]:
        return {
            "today_spend": round(self._today_spend, 6),
            "daily_limit": self.daily_limit,
            "daily_remaining": round(self.daily_limit - self._today_spend, 6),
            "month_spend": round(self._month_spend, 6),
            "monthly_limit": self.monthly_limit,
            "monthly_remaining": round(self.monthly_limit - self._month_spend, 6),
        }


@dataclass
class RuntimeTier:
    name: str
    base_url: str
    model: str
    api_key_env: str
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0
    timeout: float = 15.0
    headers_fn: Optional[Callable] = None

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def is_free(self) -> bool:
        return self.cost_per_1k_in == 0.0 and self.cost_per_1k_out == 0.0

    async def call(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.available:
            return {"success": False, "error": f"No key: {self.api_key_env}"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.headers_fn:
            headers = self.headers_fn(self.api_key)

        is_anthropic = "anthropic" in self.base_url
        if is_anthropic:
            body = {
                "model": self.model,
                "max_tokens": 300,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        else:
            body = {
                "model": self.model,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.base_url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            return {"success": False, "error": str(e), "elapsed_ms": ms}

        ms = (time.perf_counter() - t0) * 1000

        if is_anthropic:
            blocks = data.get("content", [])
            text = ""
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "text":
                    text = b.get("text", "")
                    break
        else:
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""

        usage = data.get("usage", {})
        tok_in = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        tok_out = usage.get("output_tokens", usage.get("completion_tokens", 0))
        cost = (tok_in / 1000 * self.cost_per_1k_in) + (tok_out / 1000 * self.cost_per_1k_out)

        return {
            "success": True,
            "text": text,
            "tokens_in": tok_in,
            "tokens_out": tok_out,
            "cost": cost,
            "elapsed_ms": ms,
            "tier": self.name,
            "model": self.model,
        }


    async def stream_call(self, system_prompt: str, user_prompt: str):
        """Async generator yielding (event_type, data) for SSE streaming.
        event_type: 'token' | 'done' | 'error'
        """
        if not self.available:
            yield ("error", {"error": f"No key: {self.api_key_env}"})
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.headers_fn:
            headers = self.headers_fn(self.api_key)

        is_anthropic = "anthropic" in self.base_url
        if is_anthropic:
            body = {
                "model": self.model,
                "max_tokens": 300,
                "stream": True,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        else:
            body = {
                "model": self.model,
                "max_tokens": 300,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

        t0 = time.perf_counter()
        full_text = ""
        tok_in = 0
        tok_out = 0

        try:
            stream_timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=stream_timeout) as client:
                async with client.stream("POST", self.base_url, headers=headers, json=body) as resp:
                    resp.raise_for_status()
                    current_event = ""
                    async for raw_line in resp.aiter_lines():
                        line = raw_line.strip()
                        if not line:
                            current_event = ""
                            continue
                        if line.startswith("event: "):
                            current_event = line[7:]
                            continue
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        if is_anthropic:
                            evt_type = chunk.get("type", current_event)
                            if evt_type == "content_block_delta":
                                token = chunk.get("delta", {}).get("text", "")
                                if token:
                                    full_text += token
                                    yield ("token", token)
                            elif evt_type == "message_start":
                                usage = chunk.get("message", {}).get("usage", {})
                                tok_in = usage.get("input_tokens", 0)
                            elif evt_type == "message_delta":
                                usage = chunk.get("usage", {})
                                tok_out = usage.get("output_tokens", 0)
                        else:
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    full_text += token
                                    yield ("token", token)
                            usage = chunk.get("usage")
                            if usage:
                                tok_in = usage.get("prompt_tokens", tok_in)
                                tok_out = usage.get("completion_tokens", tok_out)

        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            yield ("error", {"error": str(e), "elapsed_ms": ms})
            return

        ms = (time.perf_counter() - t0) * 1000
        cost = (tok_in / 1000 * self.cost_per_1k_in) + (tok_out / 1000 * self.cost_per_1k_out)

        yield ("done", {
            "text": full_text,
            "tokens_in": tok_in,
            "tokens_out": tok_out,
            "cost": cost,
            "elapsed_ms": ms,
            "tier": self.name,
            "model": self.model,
        })


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


RUNTIME_TIERS: list[RuntimeTier] = [
    RuntimeTier(
        name="Hermes-405B",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="nousresearch/hermes-3-llama-3.1-405b:free",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=30.0,
    ),
    RuntimeTier(
        name="Nemotron-120B",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=25.0,
    ),
    RuntimeTier(
        name="Elephant",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="openrouter/elephant-alpha",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=25.0,
    ),
    RuntimeTier(
        name="GPT-OSS-120B",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="openai/gpt-oss-120b:free",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=25.0,
    ),
    RuntimeTier(
        name="Gemma4-31B",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="google/gemma-4-31b-it:free",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_in=0.0,
        cost_per_1k_out=0.0,
        timeout=20.0,
    ),
    RuntimeTier(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1/chat/completions",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        cost_per_1k_in=0.00014,
        cost_per_1k_out=0.00028,
        timeout=20.0,
    ),
    RuntimeTier(
        name="Claude",
        base_url="https://api.anthropic.com/v1/messages",
        model="claude-3-haiku-20240307",
        api_key_env="ANTHROPIC_API_KEY",
        cost_per_1k_in=0.00025,
        cost_per_1k_out=0.00125,
        timeout=15.0,
        headers_fn=_anthropic_headers,
    ),
]


@dataclass
class SoulRuntime:
    name: str
    model_hint: str
    tier_hint: str
    senses: list[str]
    memory: dict[str, Any] = field(default_factory=dict)
    cycle_count: int = 0
    total_cost: float = 0.0
    _alive: bool = True


@dataclass
class RuntimeLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, entry: dict[str, Any]) -> None:
        entry["timestamp"] = time.time()
        entry["time"] = time.strftime("%H:%M:%S")
        self.entries.append(entry)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8")

    def summary(self) -> dict[str, Any]:
        total_calls = len([e for e in self.entries if e.get("type") == "llm_call"])
        total_cost = sum(e.get("cost", 0) for e in self.entries)
        by_soul: dict[str, float] = {}
        by_tier: dict[str, int] = {}
        for e in self.entries:
            if e.get("type") == "llm_call":
                soul = e.get("soul", "?")
                tier = e.get("tier", "?")
                by_soul[soul] = by_soul.get(soul, 0) + e.get("cost", 0)
                by_tier[tier] = by_tier.get(tier, 0) + 1
        return {
            "total_calls": total_calls,
            "total_cost": round(total_cost, 6),
            "by_soul": {k: round(v, 6) for k, v in by_soul.items()},
            "by_tier": by_tier,
            "entries": len(self.entries),
        }


class NousRuntime:
    def __init__(
        self,
        mode: str = "dry-run",
        daily_budget: float = 0.33,
        monthly_budget: float = 10.0,
        heartbeat_seconds: int = 300,
        max_cycles: int = 3,
    ) -> None:
        self.mode = mode
        self.budget = BudgetGuard(daily_limit=daily_budget, monthly_limit=monthly_budget)
        self.tiers = RUNTIME_TIERS
        self.heartbeat = heartbeat_seconds
        self.max_cycles = max_cycles
        self.souls: dict[str, SoulRuntime] = {}
        self.channels: dict[str, asyncio.Queue] = {}
        self.rlog = RuntimeLog()
        self._noesis_engine = None

    def _get_noesis(self) -> Any:
        if self._noesis_engine is None:
            try:
                from noesis_engine import NoesisEngine
                from noesis_oracle import create_oracle_fn
                oracle_fn, _ = create_oracle_fn()
                self._noesis_engine = NoesisEngine(oracle_fn=oracle_fn, oracle_threshold=0.55)
                lattice = Path("/opt/aetherlang_agents/nous/noesis_lattice.json")
                if lattice.exists():
                    self._noesis_engine.load(lattice)
                    log.info(f"Noesis loaded: {self._noesis_engine.lattice.size} atoms")
            except Exception as e:
                log.warning(f"Noesis not available: {e}")
        return self._noesis_engine

    def register_soul(self, name: str, model: str, tier: str, senses: list[str], memory: dict[str, Any] | None = None) -> None:
        self.souls[name] = SoulRuntime(
            name=name,
            model_hint=model,
            tier_hint=tier,
            senses=senses,
            memory=memory or {},
        )
        self.rlog.add({"type": "soul_registered", "soul": name, "model": model, "tier": tier})

    async def think(self, soul_name: str, query: str, system_prompt: str = "") -> str:
        soul = self.souls.get(soul_name)
        if not soul:
            log.error(f"Unknown soul: {soul_name}")
            return ""

        if not system_prompt:
            system_prompt = f"You are {soul_name}, an AI agent. Answer concisely in 2-4 sentences."

        noesis = self._get_noesis()
        if noesis:
            result = noesis.think(query, use_oracle=False)
            if hasattr(result, 'score') and result.score > 0.6:
                answer = result.response if hasattr(result, 'response') else str(result)
                self.rlog.add({
                    "type": "noesis_hit",
                    "soul": soul_name,
                    "query": query[:100],
                    "score": round(result.score, 4) if hasattr(result, 'score') else 0,
                    "cost": 0.0,
                })
                log.info(f"[{soul_name}] Noesis hit (score={result.score:.3f}): {query[:60]}")
                return answer

        if self.mode == "dry-run":
            self.rlog.add({
                "type": "llm_call",
                "mode": "dry-run",
                "soul": soul_name,
                "query": query[:100],
                "tier": "would-use-first-available",
                "cost": 0.0,
            })
            log.info(f"[DRY-RUN] [{soul_name}] Would call LLM: {query[:60]}")
            return f"[DRY-RUN] {soul_name} would answer: {query[:60]}"

        if not self.budget.can_spend(0.001):
            self.rlog.add({"type": "budget_blocked", "soul": soul_name, "query": query[:100]})
            log.warning(f"[{soul_name}] Budget exhausted, skipping")
            return ""

        for tier in self.tiers:
            if not tier.available:
                continue

            if not tier.is_free and not self.budget.can_spend(0.01):
                log.debug(f"[{soul_name}] Skipping paid tier {tier.name}")
                continue

            result = await tier.call(system_prompt, query)

            if result.get("success"):
                cost = result.get("cost", 0.0)
                self.budget.record(cost)
                soul.total_cost += cost
                soul.cycle_count += 1

                self.rlog.add({
                    "type": "llm_call",
                    "mode": "live",
                    "soul": soul_name,
                    "query": query[:100],
                    "response": result.get("text", "")[:200],
                    "tier": tier.name,
                    "model": tier.model,
                    "tokens_in": result.get("tokens_in", 0),
                    "tokens_out": result.get("tokens_out", 0),
                    "cost": cost,
                    "elapsed_ms": round(result.get("elapsed_ms", 0), 1),
                })

                text = result.get("text", "")
                if noesis and text:
                    noesis.learn(text, source=f"runtime/{soul_name}")

                log.info(f"[{soul_name}] {tier.name}: {result.get('tokens_in',0)}+{result.get('tokens_out',0)} tok, ${cost:.4f}, {result.get('elapsed_ms',0):.0f}ms")
                return text

            log.warning(f"[{soul_name}] {tier.name} failed: {result.get('error','')}")

        log.error(f"[{soul_name}] All tiers failed")
        return ""

    async def speak(self, from_soul: str, channel: str, message: Any) -> None:
        if channel not in self.channels:
            self.channels[channel] = asyncio.Queue()
        await self.channels[channel].put(message)
        self.rlog.add({"type": "speak", "soul": from_soul, "channel": channel, "message": str(message)[:100]})
        log.info(f"[{from_soul}] → {channel}: {str(message)[:60]}")

    async def listen(self, soul_name: str, channel: str, timeout: float = 30.0) -> Any:
        if channel not in self.channels:
            self.channels[channel] = asyncio.Queue()
        try:
            msg = await asyncio.wait_for(self.channels[channel].get(), timeout=timeout)
            self.rlog.add({"type": "listen", "soul": soul_name, "channel": channel, "message": str(msg)[:100]})
            return msg
        except asyncio.TimeoutError:
            self.rlog.add({"type": "listen_timeout", "soul": soul_name, "channel": channel})
            return None

    def report(self) -> str:
        s = self.rlog.summary()
        b = self.budget.status
        lines = [
            f"═══ NOUS Runtime Report ═══",
            f"Mode:          {self.mode}",
            f"Total calls:   {s['total_calls']}",
            f"Total cost:    ${s['total_cost']:.4f}",
            f"Budget today:  ${b['today_spend']:.4f} / ${b['daily_limit']}",
            f"Budget month:  ${b['month_spend']:.4f} / ${b['monthly_limit']}",
            f"",
        ]
        if s["by_soul"]:
            lines.append("Per soul:")
            for soul, cost in sorted(s["by_soul"].items(), key=lambda x: -x[1]):
                lines.append(f"  {soul:15s} ${cost:.4f}")
        if s["by_tier"]:
            lines.append("Per tier:")
            for tier, count in sorted(s["by_tier"].items(), key=lambda x: -x[1]):
                lines.append(f"  {tier:15s} {count} calls")
        return "\n".join(lines)


async def demo_dry_run() -> None:
    """Demo: run GateAlpha in dry-run mode for 3 cycles"""
    rt = NousRuntime(mode="dry-run", max_cycles=3)

    rt.register_soul("Scout", "deepseek-r1", "Tier1", ["gate_alpha_scan", "fetch_rsi"])
    rt.register_soul("Quant", "qwen2.5-7b", "Free", ["calculate_kelly"])
    rt.register_soul("Hunter", "deepseek-r1", "Tier1", ["execute_paper_trade"])
    rt.register_soul("Monitor", "qwen2.5-7b", "Free", ["send_telegram"])

    for cycle in range(rt.max_cycles):
        log.info(f"\n═══ Cycle {cycle + 1}/{rt.max_cycles} ═══")

        signal = await rt.think("Scout", "Scan top crypto pairs by volume and RSI. Which pairs show buying opportunity?")
        await rt.speak("Scout", "Scout_Signal", {"pair": "BTC/USDT", "score": 0.85, "rsi": 42})

        sig = await rt.listen("Quant", "Scout_Signal", timeout=5)
        if sig:
            decision = await rt.think("Quant", f"Analyze signal: {sig}. Calculate Kelly criterion and risk.")
            await rt.speak("Quant", "Quant_Decision", {"action": "BUY", "size": 0.1, "risk": 0.3})

        dec = await rt.listen("Hunter", "Quant_Decision", timeout=5)
        if dec:
            await rt.think("Hunter", f"Execute paper trade: {dec}")

        await rt.think("Monitor", f"Log cycle {cycle + 1} signal: {signal[:80] if isinstance(signal, str) else signal}")

        await asyncio.sleep(1)

    print("\n" + rt.report())
    rt.rlog.save(Path("/opt/aetherlang_agents/nous/runtime_dry_run.json"))
    print(f"\nLog saved to runtime_dry_run.json")


async def demo_live() -> None:
    """Demo: run GateAlpha in live mode for 1 cycle"""
    rt = NousRuntime(mode="live", max_cycles=1, daily_budget=0.33, monthly_budget=10.0)

    rt.register_soul("Scout", "qwen2.5-7b", "Free", ["gate_alpha_scan", "fetch_rsi"])
    rt.register_soul("Quant", "qwen2.5-7b", "Free", ["calculate_kelly"])
    rt.register_soul("Hunter", "qwen2.5-7b", "Free", ["execute_paper_trade"])
    rt.register_soul("Monitor", "qwen2.5-7b", "Free", ["send_telegram"])

    log.info("═══ Live Cycle 1 ═══")

    signal = await rt.think("Scout",
        "You are a crypto trading scout. Analyze BTC/USDT current conditions. "
        "What is the RSI trend and volume pattern? 2-3 sentences.")

    if signal:
        await rt.speak("Scout", "Scout_Signal", signal)

        decision = await rt.think("Quant",
            f"You are a quantitative analyst. Given this signal: {signal[:200]}. "
            f"Should we BUY, HOLD, or SELL? What position size (0.01-1.0)? 2-3 sentences.")

        if decision:
            await rt.speak("Quant", "Quant_Decision", decision)

    print("\n" + rt.report())
    rt.rlog.save(Path("/opt/aetherlang_agents/nous/runtime_live.json"))
    print(f"\nLog saved to runtime_live.json")
    print(f"Budget: {json.dumps(rt.budget.status, indent=2)}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")

    mode = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    if mode == "live":
        asyncio.run(demo_live())
    else:
        asyncio.run(demo_dry_run())
