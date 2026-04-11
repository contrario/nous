"""
NOUS Tool — gate_alpha_scan
Scans DexScreener for high-volume token pairs on Solana/Base.
Returns scored candidates for the Scout soul.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("nous.tool.gate_alpha_scan")

DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"
DEXSCREENER_PAIRS = "https://api.dexscreener.com/latest/dex/pairs"
CHAINS = ["solana", "base"]
MIN_LIQUIDITY = 10000
MIN_VOLUME_24H = 50000
MAX_RESULTS = 20


def _score_pair(pair: dict[str, Any]) -> float:
    volume = float(pair.get("volume", {}).get("h24", 0) or 0)
    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
    price_change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
    txns = pair.get("txns", {}).get("h24", {})
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)

    vol_score = min(volume / 1_000_000, 1.0) * 30
    liq_score = min(liquidity / 500_000, 1.0) * 20
    momentum = max(min(price_change / 50, 1.0), -1.0) * 25
    buy_pressure = (buys / max(buys + sells, 1)) * 25

    return round(vol_score + liq_score + momentum + buy_pressure, 2)


async def execute(
    query: str = "SOL",
    chains: list[str] | None = None,
    min_volume: float = MIN_VOLUME_24H,
    min_liquidity: float = MIN_LIQUIDITY,
    max_results: int = MAX_RESULTS,
    **kwargs: Any,
) -> dict[str, Any]:
    target_chains = chains or CHAINS
    start = time.monotonic()
    candidates: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            resp = await http.get(DEXSCREENER_SEARCH, params={"q": query})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"DexScreener API error: {e}")
            return {"success": False, "error": str(e), "data": []}

        pairs = data.get("pairs", [])
        for pair in pairs:
            chain = pair.get("chainId", "")
            if chain not in target_chains:
                continue

            volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
            liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)

            if volume_24h < min_volume or liquidity_usd < min_liquidity:
                continue

            score = _score_pair(pair)
            candidates.append({
                "pair": pair.get("pairAddress", ""),
                "base_token": pair.get("baseToken", {}).get("symbol", ""),
                "quote_token": pair.get("quoteToken", {}).get("symbol", ""),
                "chain": chain,
                "dex": pair.get("dexId", ""),
                "price_usd": float(pair.get("priceUsd", 0) or 0),
                "volume_24h": volume_24h,
                "liquidity_usd": liquidity_usd,
                "price_change_24h": float(pair.get("priceChange", {}).get("h24", 0) or 0),
                "composite_score": score,
                "url": pair.get("url", ""),
            })

    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:max_results]
    elapsed = round((time.monotonic() - start) * 1000, 1)

    log.info(f"Scan complete: {len(candidates)} candidates in {elapsed}ms")
    return {
        "success": True,
        "data": candidates,
        "count": len(candidates),
        "latency_ms": elapsed,
    }
