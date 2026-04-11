"""
NOUS Tool — calculate_kelly
Kelly criterion position sizing for the Quant soul.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("nous.tool.calculate_kelly")


async def execute(
    signal: Any = None,
    win_rate: float = 0.0,
    avg_win: float = 0.0,
    avg_loss: float = 0.0,
    score: float = 0.0,
    rsi: float = 50.0,
    **kwargs: Any,
) -> dict[str, Any]:
    if isinstance(signal, dict):
        score = float(signal.get("score", signal.get("composite_score", score)))
        rsi = float(signal.get("rsi", rsi))
    elif hasattr(signal, "score"):
        score = float(getattr(signal, "score", score))
        rsi = float(getattr(signal, "rsi", rsi))

    edge = 0.0

    if win_rate > 0 and avg_win > 0 and avg_loss > 0:
        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - p
        edge = (b * p - q) / b
        kelly = edge
    else:
        momentum = max(min(score / 100.0, 1.0), 0.0)
        rsi_factor = 1.0 - abs(rsi - 30) / 70.0
        rsi_factor = max(rsi_factor, 0.0)
        edge = momentum * 0.6 + rsi_factor * 0.4
        edge = round(edge, 4)
        kelly = edge * 0.5 if edge > 0 else 0.0

    kelly = max(0.0, min(kelly, 0.25))
    fraction = round(kelly, 4)

    log.info(f"Kelly: edge={edge}, fraction={fraction}, score={score}, rsi={rsi}")
    return {
        "success": True,
        "edge": round(edge, 4),
        "fraction": fraction,
        "half_kelly": round(fraction * 0.5, 4),
        "score": score,
        "rsi": rsi,
    }
