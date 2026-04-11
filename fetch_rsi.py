"""
NOUS Tool — fetch_rsi
======================
Fetches real OHLCV candles via ccxt and computes RSI-14.
Falls back across exchanges if pair not found.

Usage in .nous:
    let rsi = sense fetch_rsi(token.pair)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import ccxt.async_support as ccxt_async

logger = logging.getLogger("nous.tools.fetch_rsi")

DEFAULT_EXCHANGE = os.environ.get("NOUS_RSI_EXCHANGE", "binance")
RSI_PERIOD = 14
OHLCV_LIMIT = RSI_PERIOD + 50
TIMEFRAME = "1h"

FALLBACK_EXCHANGES = ["binance", "bybit", "gate", "kucoin", "okx"]


def _compute_rsi(closes: list[float], period: int = RSI_PERIOD) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _normalize_pair(pair: str) -> str:
    pair = pair.strip().upper()
    if "/" in pair:
        return pair
    for quote in ("USDT", "USDC", "USD", "BUSD", "BTC", "ETH"):
        if pair.endswith(quote) and len(pair) > len(quote):
            base = pair[: -len(quote)]
            return f"{base}/{quote}"
    return f"{pair}/USDT"


async def _fetch_from_exchange(
    exchange_id: str,
    symbol: str,
    timeframe: str = TIMEFRAME,
    limit: int = OHLCV_LIMIT,
) -> Optional[list[float]]:
    exchange_class = getattr(ccxt_async, exchange_id, None)
    if exchange_class is None:
        return None
    exchange = exchange_class({"enableRateLimit": True})
    try:
        await exchange.load_markets()
        if symbol not in exchange.markets:
            alt = symbol.replace("/USDT", "/USDC")
            if alt in exchange.markets:
                symbol = alt
            else:
                return None
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < RSI_PERIOD + 1:
            return None
        closes = [candle[4] for candle in ohlcv]
        return closes
    except Exception as e:
        logger.debug("Exchange %s failed for %s: %s", exchange_id, symbol, e)
        return None
    finally:
        try:
            await exchange.close()
        except Exception:
            pass


async def fetch_rsi(
    pair: str = "",
    timeframe: str = TIMEFRAME,
    period: int = RSI_PERIOD,
    exchange: str = DEFAULT_EXCHANGE,
    **kwargs: Any,
) -> float:
    if not pair:
        pair = kwargs.get("_pos_0", "")
    if not pair:
        logger.warning("fetch_rsi called without pair argument")
        return 50.0

    symbol = _normalize_pair(str(pair))
    logger.info("fetch_rsi: %s on %s (tf=%s, period=%d)", symbol, exchange, timeframe, period)

    exchanges_to_try = [exchange] + [e for e in FALLBACK_EXCHANGES if e != exchange]
    for exch_id in exchanges_to_try:
        closes = await _fetch_from_exchange(exch_id, symbol, timeframe, OHLCV_LIMIT)
        if closes is not None:
            rsi = _compute_rsi(closes, period)
            logger.info("fetch_rsi: %s RSI=%0.2f (%d candles from %s)", symbol, rsi, len(closes), exch_id)
            return round(rsi, 2)

    logger.warning("fetch_rsi: %s not found on any exchange, returning 50.0", symbol)
    return 50.0


async def run(args: dict[str, Any] | None = None, **kwargs: Any) -> float:
    if args is None:
        args = kwargs
    return await fetch_rsi(**args)


if __name__ == "__main__":
    import sys

    pair = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    result = asyncio.run(fetch_rsi(pair=pair))
    print(f"RSI-{RSI_PERIOD} for {pair}: {result}")
