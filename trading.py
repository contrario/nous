"""
NOUS Trading Guard
==================
Telegram approval, audit logging, kill switch, real exchange execution.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    import ccxt.async_support as ccxt_async
except ImportError:
    ccxt_async = None


TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
AUDIT_DIR = Path(os.getenv("NOUS_AUDIT_DIR", "/opt/aetherlang_agents/logs"))
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


class AuditLog:
    """Append-only JSON-lines trade audit log."""

    def __init__(self, world_name: str = "default") -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._path = AUDIT_DIR / f"trades_{world_name}_{date_str}.jsonl"

    def record(self, entry: dict[str, Any]) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    @property
    def path(self) -> Path:
        return self._path


class KillSwitch:
    """Telegram-based kill switch. Polls for /stop command."""

    def __init__(self) -> None:
        self._active = True
        self._last_update_id = 0
        self._poll_task: asyncio.Task[None] | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    def halt(self, reason: str = "manual") -> None:
        self._active = False
        print(f"\n  ⛔ KILL SWITCH ACTIVATED: {reason}")

    async def start_polling(self, interval: float = 5.0) -> None:
        self._poll_task = asyncio.create_task(self._poll_loop(interval))

    async def stop_polling(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self, interval: float) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            while self._active:
                try:
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                    params = {"offset": self._last_update_id + 1, "timeout": 5}
                    resp = await client.get(url, params=params)
                    data = resp.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            self._last_update_id = update["update_id"]
                            msg = update.get("message", {})
                            text = msg.get("text", "").strip()
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            if text == "/stop" and chat_id == TELEGRAM_CHAT:
                                self.halt("Telegram /stop command")
                                await client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                    json={"chat_id": TELEGRAM_CHAT, "text": "⛔ NOUS Trading HALTED. All trades blocked."}
                                )
                                return
                            elif text == "/status" and chat_id == TELEGRAM_CHAT:
                                await client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                    json={"chat_id": TELEGRAM_CHAT, "text": "✅ NOUS Trading active."}
                                )
                            elif text == "/resume" and chat_id == TELEGRAM_CHAT:
                                self._active = True
                                await client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                    json={"chat_id": TELEGRAM_CHAT, "text": "▶️ NOUS Trading resumed."}
                                )
                except Exception:
                    pass
                await asyncio.sleep(interval)


class TelegramApproval:
    """Sends trade proposal to Telegram, waits for Yes/No reply."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    async def request_approval(self, trade_info: dict[str, Any]) -> bool:
        action = trade_info.get("action", "TRADE")
        pair = trade_info.get("pair", "?")
        size = trade_info.get("size", 0)
        risk = trade_info.get("risk", 0)
        sl = trade_info.get("sl_pct", 0)
        tp = trade_info.get("tp_pct", 0)

        text = (
            f"🔔 *NOUS Trade Approval*\n\n"
            f"*Action:* {action}\n"
            f"*Pair:* {pair}\n"
            f"*Size:* ${size:.2f}\n"
            f"*Risk:* {risk:.1%}\n"
            f"*SL:* {sl}% | *TP:* {tp}%\n\n"
            f"Reply /yes to approve or /no to reject.\n"
            f"Auto-reject in {int(self._timeout)}s."
        )

        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT,
                    "text": text,
                    "parse_mode": "Markdown",
                }
            )

            start = time.monotonic()
            last_update_id = 0

            while time.monotonic() - start < self._timeout:
                try:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                        params={"offset": last_update_id + 1, "timeout": 5}
                    )
                    data = resp.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            last_update_id = update["update_id"]
                            msg = update.get("message", {})
                            reply = msg.get("text", "").strip().lower()
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            if chat_id != TELEGRAM_CHAT:
                                continue
                            if reply in ("/yes", "yes", "y"):
                                await client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                    json={"chat_id": TELEGRAM_CHAT, "text": f"✅ Trade APPROVED: {action} {pair}"}
                                )
                                return True
                            elif reply in ("/no", "no", "n"):
                                await client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                    json={"chat_id": TELEGRAM_CHAT, "text": f"❌ Trade REJECTED: {action} {pair}"}
                                )
                                return False
                except Exception:
                    pass
                await asyncio.sleep(2)

            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": f"⏰ Trade TIMEOUT (auto-reject): {action} {pair}"}
            )
            return False


class RealExchange:
    """Binance Futures integration via ccxt."""

    def __init__(self, exchange_id: str = "binance") -> None:
        if ccxt_async is None:
            raise ImportError("ccxt not installed: pip install ccxt")
        self._exchange_id = exchange_id
        self._exchange: Any = None

    async def _get_exchange(self) -> Any:
        if self._exchange is None:
            cls = getattr(ccxt_async, self._exchange_id)
            self._exchange = cls({
                "apiKey": os.getenv("BINANCE_API_KEY", ""),
                "secret": os.getenv("BINANCE_SECRET", ""),
                "options": {"defaultType": "future"},
                "enableRateLimit": True,
            })
        return self._exchange

    async def execute_trade(self, action: str, pair: str, size_usd: float,
                            sl_pct: float = 0, tp_pct: float = 0) -> dict[str, Any]:
        ex = await self._get_exchange()
        try:
            ticker = await ex.fetch_ticker(pair)
            price = ticker["last"]
            amount = size_usd / price

            side = "buy" if action.upper() == "BUY" else "sell"
            order = await ex.create_market_order(pair, side, amount)

            result = {
                "order_id": order.get("id"),
                "pair": pair,
                "side": side,
                "amount": amount,
                "price": price,
                "cost": size_usd,
                "status": order.get("status", "filled"),
            }

            if sl_pct > 0:
                sl_price = price * (1 - sl_pct / 100) if side == "buy" else price * (1 + sl_pct / 100)
                sl_side = "sell" if side == "buy" else "buy"
                try:
                    await ex.create_order(pair, "stop_market", sl_side, amount,
                                          params={"stopPrice": sl_price})
                    result["sl_price"] = sl_price
                except Exception as e:
                    result["sl_error"] = str(e)

            if tp_pct > 0:
                tp_price = price * (1 + tp_pct / 100) if side == "buy" else price * (1 - tp_pct / 100)
                tp_side = "sell" if side == "buy" else "buy"
                try:
                    await ex.create_order(pair, "take_profit_market", tp_side, amount,
                                          params={"stopPrice": tp_price})
                    result["tp_price"] = tp_price
                except Exception as e:
                    result["tp_error"] = str(e)

            return result
        except Exception as e:
            return {"error": str(e), "pair": pair, "action": action}

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None


class TradeGuard:
    """Unified trading guard: approval + audit + kill switch + exchange."""

    def __init__(self, world_name: str = "default",
                 require_approval: bool = False,
                 no_live_trading: bool = True,
                 max_position: float = 0,
                 max_daily_loss: float = 0,
                 approval_timeout: float = 120.0) -> None:
        self.audit = AuditLog(world_name)
        self.kill_switch = KillSwitch()
        self.approval = TelegramApproval(approval_timeout) if require_approval else None
        self.exchange = RealExchange() if not no_live_trading else None
        self._require_approval = require_approval
        self._no_live = no_live_trading
        self._max_position = max_position
        self._max_daily_loss = max_daily_loss
        self._daily_pnl = 0.0
        self._daily_trades = 0

    async def start(self) -> None:
        await self.kill_switch.start_polling()

    async def stop(self) -> None:
        await self.kill_switch.stop_polling()
        if self.exchange:
            await self.exchange.close()

    async def execute_trade(self, trade_info: dict[str, Any]) -> dict[str, Any]:
        entry = {"type": "trade_attempt", **trade_info}

        if not self.kill_switch.is_active:
            entry["result"] = "BLOCKED"
            entry["reason"] = "kill_switch_active"
            self.audit.record(entry)
            return {"status": "blocked", "reason": "Kill switch active"}

        size = trade_info.get("size", 0)
        if self._max_position > 0 and size > self._max_position:
            entry["result"] = "BLOCKED"
            entry["reason"] = f"exceeds_max_position_{self._max_position}"
            self.audit.record(entry)
            return {"status": "blocked", "reason": f"Exceeds MaxPositionSize ${self._max_position}"}

        if self._max_daily_loss > 0 and abs(self._daily_pnl) >= self._max_daily_loss:
            entry["result"] = "BLOCKED"
            entry["reason"] = "daily_loss_limit"
            self.audit.record(entry)
            return {"status": "blocked", "reason": f"Daily loss limit ${self._max_daily_loss} reached"}

        if self._require_approval and self.approval:
            approved = await self.approval.request_approval(trade_info)
            entry["approval"] = "approved" if approved else "rejected"
            if not approved:
                entry["result"] = "REJECTED"
                self.audit.record(entry)
                return {"status": "rejected", "reason": "User rejected via Telegram"}

        if self._no_live:
            entry["result"] = "PAPER"
            entry["reason"] = "NoLiveTrading=true"
            self.audit.record(entry)
            return {"status": "paper", "reason": "Paper trade (NoLiveTrading)"}

        if self.exchange:
            result = await self.exchange.execute_trade(
                action=trade_info.get("action", "BUY"),
                pair=trade_info.get("pair", ""),
                size_usd=size,
                sl_pct=trade_info.get("sl_pct", 0),
                tp_pct=trade_info.get("tp_pct", 0),
            )
            entry["result"] = "EXECUTED" if "error" not in result else "FAILED"
            entry["exchange_result"] = result
            self.audit.record(entry)
            self._daily_trades += 1
            return result

        entry["result"] = "NO_EXCHANGE"
        self.audit.record(entry)
        return {"status": "error", "reason": "No exchange configured"}

    def record_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl
        self.audit.record({
            "type": "pnl_update",
            "pnl": pnl,
            "daily_total": self._daily_pnl,
        })

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self.audit.record({"type": "daily_reset"})
