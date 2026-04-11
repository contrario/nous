"""
NOUS Tool — check_balance
Reads paper trading portfolio balance.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("nous.tool.check_balance")

PORTFOLIO_PATH = Path("/opt/aetherlang_agents/nous/paper_portfolio.json")


async def execute(**kwargs: Any) -> dict[str, Any]:
    if not PORTFOLIO_PATH.exists():
        return {
            "success": True,
            "balance": 10000.0,
            "total_trades": 0,
            "total_pnl": 0.0,
            "open_positions": 0,
        }

    try:
        portfolio = json.loads(PORTFOLIO_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"success": False, "error": str(e)}

    open_count = len([p for p in portfolio.get("positions", []) if p.get("status") == "open"])

    return {
        "success": True,
        "balance": portfolio.get("balance", 0.0),
        "total_trades": portfolio.get("total_trades", 0),
        "total_pnl": round(portfolio.get("total_pnl", 0.0), 2),
        "open_positions": open_count,
    }
