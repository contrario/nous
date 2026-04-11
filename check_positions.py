"""
NOUS Tool — check_positions
Returns open paper trading positions.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("nous.tool.check_positions")

PORTFOLIO_PATH = Path("/opt/aetherlang_agents/nous/paper_portfolio.json")


async def execute(**kwargs: Any) -> dict[str, Any]:
    if not PORTFOLIO_PATH.exists():
        return {"success": True, "positions": [], "count": 0}

    try:
        portfolio = json.loads(PORTFOLIO_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"success": False, "error": str(e)}

    open_positions = [p for p in portfolio.get("positions", []) if p.get("status") == "open"]
    now = time.time()

    for pos in open_positions:
        age_hours = (now - pos.get("timestamp", now)) / 3600
        pos["age_hours"] = round(age_hours, 1)

    return {
        "success": True,
        "positions": open_positions,
        "count": len(open_positions),
        "total_invested": round(sum(p.get("size_usd", 0) for p in open_positions), 2),
    }
