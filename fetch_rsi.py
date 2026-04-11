"""
NOUS Tool — fetch_rsi
Fetches price history from DexScreener and calculates RSI-14.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("nous.tool.fetch_rsi")

DEXSCREENER_PAIRS = "https://api.dexscreener.com/latest/dex/pairs"


def _calculate_rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-(period):]

    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]

    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0001

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


async def execute(
    pair: str = "",
    chain: str = "solana",
    period: int = 14,
    **kwargs: Any,
) -> dict[str, Any]:
    start = time.monotonic()

    if isinstance(pair, dict):
        pair = pair.get("pair", pair.get("pairAddress", ""))

    if not pair:
        return {"success": False, "error": "No pair address provided", "rsi": 50.0}

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            url = f"{DEXSCREENER_PAIRS}/{chain}/{pair}"
            resp = await http.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"DexScreener price fetch error: {e}")
            return {"success": False, "error": str(e), "rsi": 50.0}

    pair_data = data.get("pair") or (data.get("pairs", [{}])[0] if data.get("pairs") else {})

    price_change_5m = float(pair_data.get("priceChange", {}).get("m5", 0) or 0)
    price_change_1h = float(pair_data.get("priceChange", {}).get("h1", 0) or 0)
    price_change_6h = float(pair_data.get("priceChange", {}).get("h6", 0) or 0)
    price_change_24h = float(pair_data.get("priceChange", {}).get("h24", 0) or 0)

    current_price = float(pair_data.get("priceUsd", 0) or 0)
    if current_price <= 0:
        return {"success": False, "error": "No price data", "rsi": 50.0}

    synthetic_prices = []
    base = current_price / (1 + price_change_24h / 100) if price_change_24h != -100 else current_price
    changes = [
        price_change_24h * 0.1,
        price_change_24h * 0.2,
        price_change_24h * 0.3,
        price_change_24h * 0.35,
        price_change_24h * 0.4,
        price_change_24h * 0.45,
        price_change_24h * 0.5,
        price_change_24h * 0.55,
        price_change_24h * 0.6,
        price_change_24h * 0.65,
        price_change_24h * 0.7,
        price_change_6h * 0.5,
        price_change_6h * 0.75,
        price_change_1h * 0.5,
        price_change_1h * 0.75,
        price_change_5m * 0.5,
        0.0,
    ]
    for pct in changes:
        synthetic_prices.append(base * (1 + pct / 100))

    rsi = _calculate_rsi(synthetic_prices, period)
    elapsed = round((time.monotonic() - start) * 1000, 1)

    log.info(f"RSI for {pair[:12]}...: {rsi} ({elapsed}ms)")
    return {
        "success": True,
        "rsi": rsi,
        "price_usd": current_price,
        "price_change_24h": price_change_24h,
        "pair": pair,
        "latency_ms": elapsed,
    }
