"""
Noesis Gemini Oracle — Phase 7
===============================
Adds Google Gemini as a free oracle tier.
Slots in as Tier 3.5 (after SiliconFlow, before Claude).

Uses Gemini REST API directly via httpx.
Env var: GEMINI_API_KEY
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger("noesis.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiOracle:

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = GEMINI_DEFAULT_MODEL,
        timeout: float = 30.0,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.calls: int = 0
        self.failures: int = 0
        self.total_latency: float = 0.0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def ask(
        self,
        query: str,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        if not self.available:
            logger.debug("Gemini: no API key")
            return None

        url = (
            f"{GEMINI_API_BASE}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

        contents: list[dict] = []

        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"[System instruction]: {system_prompt}"}],
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}],
            })

        contents.append({
            "role": "user",
            "parts": [{"text": query}],
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": 0.7,
            },
        }

        t0 = time.time()
        self.calls += 1

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            latency = time.time() - t0
            self.total_latency += latency

            if resp.status_code != 200:
                self.failures += 1
                error_text = resp.text[:200]
                logger.warning(
                    f"Gemini API error {resp.status_code}: {error_text}"
                )
                return None

            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                self.failures += 1
                logger.warning("Gemini: no candidates in response")
                return None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                self.failures += 1
                logger.warning("Gemini: no parts in response")
                return None

            text = parts[0].get("text", "").strip()
            if not text:
                self.failures += 1
                return None

            logger.info(f"Gemini response: {len(text)} chars, {latency:.2f}s")
            return text

        except httpx.TimeoutException:
            self.failures += 1
            logger.warning(f"Gemini timeout after {self.timeout}s")
            return None
        except Exception as e:
            self.failures += 1
            logger.error(f"Gemini error: {e}")
            return None

    def stats(self) -> dict[str, object]:
        avg_latency = (self.total_latency / self.calls) if self.calls > 0 else 0
        return {
            "provider": "gemini",
            "model": self.model,
            "available": self.available,
            "calls": self.calls,
            "failures": self.failures,
            "success_rate": (
                round((self.calls - self.failures) / self.calls * 100, 1)
                if self.calls > 0 else 0
            ),
            "avg_latency_s": round(avg_latency, 3),
        }


def install_gemini_tier(oracle: object) -> bool:
    gemini = GeminiOracle()
    if not gemini.available:
        logger.info("Gemini: no GEMINI_API_KEY, tier not installed")
        return False

    if not hasattr(oracle, "tiers") or not isinstance(oracle.tiers, list):
        logger.warning("Oracle has no tiers list, cannot install Gemini")
        return False

    claude_idx = -1
    for i, tier in enumerate(oracle.tiers):
        name = getattr(tier, "name", "")
        if "anthropic" in name.lower() or "claude" in name.lower():
            claude_idx = i
            break

    from dataclasses import dataclass

    @dataclass
    class GeminiTier:
        name: str = "gemini"
        base_url: str = GEMINI_API_BASE
        api_key_env: str = "GEMINI_API_KEY"
        model: str = GEMINI_DEFAULT_MODEL
        is_anthropic: bool = False
        is_gemini: bool = True

    tier = GeminiTier()

    if claude_idx >= 0:
        oracle.tiers.insert(claude_idx, tier)
        logger.info(f"Gemini tier installed at position {claude_idx} (before Claude)")
    else:
        oracle.tiers.append(tier)
        logger.info("Gemini tier installed at end")

    original_call = oracle._call_tier if hasattr(oracle, "_call_tier") else None

    _gemini_instance = gemini

    def _patched_call_tier(tier_obj: object, query: str, system: str = "") -> Optional[str]:
        if getattr(tier_obj, "is_gemini", False):
            return _gemini_instance.ask(query, system_prompt=system or None)
        if original_call:
            return original_call(tier_obj, query, system)
        return None

    oracle._call_tier = _patched_call_tier
    oracle._gemini = _gemini_instance

    return True
