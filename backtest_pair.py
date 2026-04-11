"""
NOUS Tool — backtest_pair
Simple momentum backtest for pair evaluation.
Uses price change data from DexScreener as proxy for historical performance.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("nous.tool.backtest_pair")


async def execute(
    signal: Any = None,
    pair: str = "",
    chain: str = "solana",
    initial_capital: float = 1000.0,
    **kwargs: Any,
) -> dict[str, Any]:
    if isinstance(signal, dict):
        pair = signal.get("pair", pair)
        chain = signal.get("chain", chain)
    elif hasattr(signal, "pair"):
        pair = getattr(signal, "pair", pair)

    if not pair:
        return {"success": False, "error": "No pair provided"}

    start = time.monotonic()

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"
            resp = await http.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    pair_data = data.get("pair") or (data.get("pairs", [{}])[0] if data.get("pairs") else {})
    pc = pair_data.get("priceChange", {})

    changes = {
        "5m": float(pc.get("m5", 0) or 0),
        "1h": float(pc.get("h1", 0) or 0),
        "6h": float(pc.get("h6", 0) or 0),
        "24h": float(pc.get("h24", 0) or 0),
    }

    simulated_returns = [
        changes["24h"] / 5,
        changes["24h"] / 5,
        changes["6h"] / 3,
        changes["6h"] / 3,
        changes["1h"],
    ]

    capital = initial_capital
    trades = 0
    wins = 0
    max_drawdown = 0.0
    peak = capital

    for r in simulated_returns:
        pnl = capital * (r / 100)
        capital += pnl
        trades += 1
        if pnl > 0:
            wins += 1
        peak = max(peak, capital)
        dd = (peak - capital) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, dd)

    total_return = ((capital - initial_capital) / initial_capital) * 100
    win_rate = wins / trades if trades > 0 else 0
    sharpe = (total_return / max(max_drawdown * 100, 1)) if max_drawdown > 0 else total_return / 10
    elapsed = round((time.monotonic() - start) * 1000, 1)

    log.info(f"Backtest {pair[:12]}...: return={total_return:.1f}%, sharpe={sharpe:.2f}")
    return {
        "success": True,
        "pair": pair,
        "total_return_pct": round(total_return, 2),
        "win_rate": round(win_rate, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "final_capital": round(capital, 2),
        "trades": trades,
        "latency_ms": elapsed,
    }
