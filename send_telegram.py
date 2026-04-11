"""
NOUS Tool — send_telegram
Sends messages via Telegram Bot API.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger("nous.tool.send_telegram")

TELEGRAM_API = "https://api.telegram.org"


async def execute(
    text: str = "",
    chat: str = "",
    parse_mode: str = "HTML",
    **kwargs: Any,
) -> dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set, logging message locally")
        log.info(f"[TELEGRAM] {text}")
        return {"success": True, "mode": "local_log", "message": text}

    if not chat_id:
        return {"success": False, "error": "No chat_id provided and TELEGRAM_CHAT_ID not set"}

    if not text:
        return {"success": False, "error": "Empty message"}

    start = time.monotonic()

    async with httpx.AsyncClient(timeout=10.0) as http:
        try:
            resp = await http.post(
                f"{TELEGRAM_API}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"Telegram send error: {e}")
            return {"success": False, "error": str(e)}

    elapsed = round((time.monotonic() - start) * 1000, 1)
    ok = data.get("ok", False)

    if ok:
        log.info(f"Telegram message sent to {chat_id} ({elapsed}ms)")
    else:
        log.warning(f"Telegram API returned ok=false: {data}")

    return {
        "success": ok,
        "message_id": data.get("result", {}).get("message_id"),
        "chat_id": chat_id,
        "latency_ms": elapsed,
    }
