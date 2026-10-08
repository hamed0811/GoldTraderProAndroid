"""Telegram signal notifier for GoldMind AI.

Signal-only integration:
- Registers private chats when a user sends /start.
- Sends BUY/SELL signals only by default.
- Never places, modifies, or cancels trading orders.
- Token is read only from TELEGRAM_BOT_TOKEN environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SEND_WAIT = os.getenv("TELEGRAM_SEND_WAIT", "false").strip().lower() in {"1", "true", "yes", "on"}
POLL_SECONDS = max(1, int(os.getenv("TELEGRAM_POLL_SECONDS", "2")))

_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
_chat_ids: set[str] = set()
_chat_lock = threading.Lock()
_last_update_id = 0
_started = False


def _api(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    payload = urllib.parse.urlencode(params or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{_API_BASE}/{method}",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _send(chat_id: str, text: str) -> bool:
    try:
        result = _api("sendMessage", {"chat_id": chat_id, "text": text})
        return bool(result.get("ok"))
    except Exception as exc:
        logger.error("Telegram send failed for chat %s: %s", chat_id, exc)
        return False


def _register_chat(chat_id: str) -> None:
    with _chat_lock:
        _chat_ids.add(str(chat_id))


def _poll_updates() -> None:
    global _last_update_id
    logger.info("Telegram signal bot polling started")
    while True:
        try:
            result = _api(
                "getUpdates",
                {
                    "offset": _last_update_id + 1,
                    "timeout": 20,
                    "allowed_updates": json.dumps(["message"]),
                },
            )
            for update in result.get("result", []):
                _last_update_id = max(_last_update_id, int(update.get("update_id", 0)))
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = str(message.get("text", "")).strip()
                if chat_id is None:
                    continue
                if text.startswith("/start"):
                    _register_chat(str(chat_id))
                    _send(
                        str(chat_id),
                        "🟡 Gold Trader Pro Signal\n\n"
                        "ربات سیگنال XAUUSD فعال شد.\n"
                        "سیگنال‌های معتبر BUY/SELL را از سیستم تحلیل دریافت خواهید کرد.\n"
                        "⚠️ این ربات هیچ معامله‌ای باز یا بسته نمی‌کند.",
                    )
                elif text.startswith("/status"):
                    _register_chat(str(chat_id))
                    _send(
                        str(chat_id),
                        "🟢 Telegram Signal Service فعال است.\n"
                        "حالت: فقط سیگنال، بدون اجرای معامله.",
                    )
        except Exception as exc:
            logger.warning("Telegram polling error: %s", exc)
            time.sleep(max(POLL_SECONDS, 5))


def start() -> bool:
    global _started
    if _started:
        return bool(BOT_TOKEN)
    _started = True
    if not BOT_TOKEN:
        logger.info("Telegram notifier disabled: TELEGRAM_BOT_TOKEN is not set")
        return False
    threading.Thread(
        target=_poll_updates,
        name="goldmind-telegram-poll",
        daemon=True,
    ).start()
    return True


def send_signal(signal: Any) -> int:
    """Send one validated signal to all registered chats.

    Returns the number of chats that accepted the message.
    """
    if not BOT_TOKEN:
        return 0

    order = signal.order
    order_type = getattr(order.type, "value", str(order.type))
    if signal.veto or order_type == "none":
        if not SEND_WAIT:
            return 0
        direction = "WAIT"
    elif order_type == "buy_stop":
        direction = "BUY"
    elif order_type == "sell_stop":
        direction = "SELL"
    else:
        return 0

    emoji = "🟢" if direction == "BUY" else "🔴" if direction == "SELL" else "🟡"
    if direction == "WAIT":
        body = (
            f"{emoji} XAUUSD SIGNAL\n\n"
            f"تصمیم: WAIT\n"
            f"دلیل: {signal.veto_reason or 'شرایط ورود تأیید نشد'}\n"
            f"زمان: {signal.timestamp_utc}"
        )
    else:
        body = (
            f"{emoji} XAUUSD SIGNAL\n\n"
            f"تصمیم: {direction}\n"
            f"Entry: {order.entry}\n"
            f"SL: {order.sl}\n"
            f"TP: {order.tp}\n"
            f"Confidence: {signal.confidence:.0%}\n"
            f"اعتبار سیگنال: حدود {order.expiry_minutes} دقیقه\n"
            f"Setup: {order.comment}\n\n"
            "⚠️ فقط سیگنال است؛ هیچ معامله‌ای خودکار اجرا نمی‌شود."
        )

    with _chat_lock:
        chats = list(_chat_ids)

    sent = 0
    for chat_id in chats:
        if _send(chat_id, body):
            sent += 1
    return sent
