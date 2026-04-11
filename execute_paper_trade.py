"""
NOUS Tool — execute_paper_trade
Executes paper trades with JSON-file portfolio state.
State file: /opt/aetherlang_agents/nous/paper_portfolio.json
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("nous.tool.execute_paper_trade")

PORTFOLIO_PATH = Path("/opt/aetherlang_agents/nous/paper_portfolio.json")
INITIAL_BALANCE = 10000.0


def _load_portfolio() -> dict[str, Any]:
    if PORTFOLIO_PATH.exists():
        try:
            return json.loads(PORTFOLIO_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "balance": INITIAL_BALANCE,
        "positions": [],
        "closed_trades": [],
        "total_trades": 0,
        "total_pnl": 0.0,
    }


def _save_portfolio(portfolio: dict[str, Any]) -> None:
    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_PATH.write_text(json.dumps(portfolio, indent=2, default=str))


async def execute(
    decision: Any = None,
    action: str = "BUY",
    pair: str = "",
    size: float = 0.0,
    price: float = 0.0,
    sl_pct: float = 8.0,
    tp_pct: float = 25.0,
    risk: float = 0.0,
    **kwargs: Any,
) -> dict[str, Any]:
    if isinstance(decision, dict):
        action = decision.get("action", action)
        size = float(decision.get("size", size))
        sl_pct = float(decision.get("sl_pct", sl_pct))
        tp_pct = float(decision.get("tp_pct", tp_pct))
        risk = float(decision.get("risk", risk))
        pair = decision.get("pair", pair)
    elif hasattr(decision, "action"):
        action = getattr(decision, "action", action)
        size = float(getattr(decision, "size", size))
        sl_pct = float(getattr(decision, "sl_pct", sl_pct))
        tp_pct = float(getattr(decision, "tp_pct", tp_pct))
        risk = float(getattr(decision, "risk", risk))

    portfolio = _load_portfolio()

    if action.upper() not in ("BUY", "SELL", "CLOSE"):
        return {"success": False, "error": f"Unknown action: {action}"}

    if action.upper() == "BUY":
        position_size = portfolio["balance"] * min(size, 1.0)
        if position_size <= 0 or position_size > portfolio["balance"]:
            return {"success": False, "error": f"Insufficient balance: ${portfolio['balance']:.2f}"}

        trade = {
            "id": portfolio["total_trades"] + 1,
            "pair": pair,
            "action": "BUY",
            "size_usd": round(position_size, 2),
            "entry_price": price,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "risk": risk,
            "timestamp": time.time(),
            "status": "open",
        }

        portfolio["balance"] -= position_size
        portfolio["positions"].append(trade)
        portfolio["total_trades"] += 1
        _save_portfolio(portfolio)

        log.info(f"PAPER BUY: {pair} ${position_size:.2f} (balance: ${portfolio['balance']:.2f})")
        return {
            "success": True,
            "trade": trade,
            "balance": portfolio["balance"],
        }

    elif action.upper() == "CLOSE":
        open_pos = [p for p in portfolio["positions"] if p.get("status") == "open"]
        if not open_pos:
            return {"success": False, "error": "No open positions"}

        pos = open_pos[-1]
        pos["status"] = "closed"
        pos["close_time"] = time.time()
        pos["close_price"] = price
        pnl = (price - pos["entry_price"]) / pos["entry_price"] * pos["size_usd"] if pos["entry_price"] else 0

        portfolio["balance"] += pos["size_usd"] + pnl
        portfolio["total_pnl"] += pnl
        portfolio["closed_trades"].append(pos)
        portfolio["positions"] = [p for p in portfolio["positions"] if p.get("status") == "open"]
        _save_portfolio(portfolio)

        log.info(f"PAPER CLOSE: {pos['pair']} PnL=${pnl:.2f}")
        return {"success": True, "pnl": round(pnl, 2), "balance": portfolio["balance"]}

    return {"success": False, "error": "Unhandled action"}
