"""
MT5 AI Signal Backend (Multi-Symbol)
=====================================
FastAPI server that receives market data from an MT5 EA,
sends it to OpenAI for analysis, and returns a structured
trading signal using Structured Outputs (JSON schema enforcement).
Supports any symbol: XAUUSD, EURUSD, US30, BTCUSD, etc.
"""

import asyncio
import os
import sys
import time
import logging
import traceback
import socket
import threading
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

try:
    from telegram_notifier import start as start_telegram, send_signal as send_telegram_signal
except Exception:
    start_telegram = lambda: False
    send_telegram_signal = lambda signal: 0

# ---------------------------------------------------------------------------
# Force unbuffered stdout so prints appear immediately in PowerShell
# ---------------------------------------------------------------------------
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
else:
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

# ---------------------------------------------------------------------------
# Configure logging (console + file)
# ---------------------------------------------------------------------------
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "goldmind.log")

log_format = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)

# File handler with auto-flush
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    delay=True,  # Don't open file until first write (avoids lock conflict on reload)
)
file_handler.setFormatter(log_format)
# Set up root logger with force=True (works reliably under uvicorn reload)
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler],
    force=True,
)
# Use the root logger directly — avoids all named-logger propagation issues
logger = logging.getLogger()

# Startup test — verify file logging works
logger.info("=" * 60)
logger.info("GoldMind AI logger initialized — file logging active")
logger.info(f"Log file: {LOG_FILE}")
logger.info("=" * 60)

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-5")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()


def _get_ai_config():
    """Choose a configured provider without exposing its credential."""
    if AI_PROVIDER == "gemini" or (AI_PROVIDER == "auto" and GEMINI_API_KEY):
        if not GEMINI_API_KEY:
            return None, "gemini", []
        return AsyncOpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=60.0,
        ), "gemini", [GEMINI_MODEL]
    if AI_PROVIDER == "openai" or (AI_PROVIDER == "auto" and OPENAI_API_KEY):
        if not OPENAI_API_KEY:
            return None, "openai", []
        models = [OPENAI_MODEL]
        if FALLBACK_MODEL and FALLBACK_MODEL != OPENAI_MODEL:
            models.append(FALLBACK_MODEL)
        return AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0), "openai", models
    return None, AI_PROVIDER, []

app = FastAPI(title="GoldMind AI Signal Backend", version="1.0.0")


# ---------------------------------------------------------------------------
# Android/LAN mobile state + UDP discovery
# ---------------------------------------------------------------------------
MOBILE_DISCOVERY_PORT = 8766
_latest_mobile_state = {
    "price": "",
    "symbol": "XAUUSD",
    "signal": None,
    "protection": {"mode": "OFF"},
}
_discovery_thread_started = False


def _local_lan_ip() -> str:
    """Return the Windows host's LAN IP without requiring internet access."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        return probe.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        probe.close()


def _publish_mobile_state(req: "SignalRequest", signal: "SignalResponse") -> None:
    order = signal.order
    order_type = getattr(order.type, "value", str(order.type))
    if signal.veto or order_type == "none":
        state, side = "WAIT", "—"
    elif order_type == "buy_stop":
        state, side = "BUY", "BUY"
    elif order_type == "sell_stop":
        state, side = "SELL", "SELL"
    else:
        state, side = "WAIT", "—"

    _latest_mobile_state.clear()
    _latest_mobile_state.update({
        "price": str(req.bid),
        "symbol": req.symbol,
        "signal": {
            "state": state,
            "side": side,
            "entry": order.entry,
            "sl": order.sl,
            "tp1": order.tp,
            "confidence": signal.confidence,
            "reasons": signal.veto_reason or order.comment,
            "timestamp_utc": signal.timestamp_utc,
            "veto": signal.veto,
        },
        "protection": {"mode": "OFF"},
        "source": _ACTIVE_MARKET_SOURCE,
        "source_symbol": _ACTIVE_SOURCE_SYMBOL,
        "updated_at_utc": req.server_time_utc,
        "data_status": "LIVE",
        "note": _ACTIVE_SOURCE_NOTE,
    })


def _start_mobile_discovery() -> None:
    global _discovery_thread_started
    if _discovery_thread_started:
        return
    _discovery_thread_started = True

    def worker():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", MOBILE_DISCOVERY_PORT))
            logger.info(f"  Mobile discovery: UDP 0.0.0.0:{MOBILE_DISCOVERY_PORT}")
            while True:
                data, addr = sock.recvfrom(512)
                if data.strip() == b"GOLDTRADER_DISCOVER":
                    host = _local_lan_ip()
                    reply = f"GOLDTRADER_SERVER|{host}|8000".encode("utf-8")
                    sock.sendto(reply, addr)
                    logger.info(f"  Mobile discovery reply -> {addr[0]}:{addr[1]} ({host}:8000)")
        except Exception as exc:
            logger.error(f"  Mobile discovery stopped: {exc}")
        finally:
            sock.close()

    threading.Thread(target=worker, name="goldtrader-mobile-discovery", daemon=True).start()


# ---------------------------------------------------------------------------
# Middleware — log every incoming request and outgoing response
# ---------------------------------------------------------------------------
class RequestResponseLogger(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # --- Incoming request ---
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        body_size = request.headers.get("content-length", "?")
        logger.info("")
        logger.info("━" * 60)
        logger.info(f"📨 [{now}] INCOMING REQUEST")
        logger.info(f"   {request.method} {request.url.path}")
        logger.info(f"   From: {request.client.host}:{request.client.port}" if request.client else "   From: unknown")
        logger.info(f"   Content-Length: {body_size} bytes")
        sys.stdout.flush()

        # --- Process request ---
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start

        # --- Outgoing response ---
        status_emoji = "✅" if response.status_code < 400 else "⚠️" if response.status_code < 500 else "❌"
        logger.info(f"📤 [{now}] OUTGOING RESPONSE")
        logger.info(f"   {status_emoji} Status: {response.status_code}")
        logger.info(f"   ⏱️  Processed in: {elapsed:.2f}s")
        logger.info("━" * 60)
        sys.stdout.flush()

        return response

app.add_middleware(RequestResponseLogger)


# ---------------------------------------------------------------------------
# Startup event — show config banner
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_banner():
    _, configured_provider, configured_models = _get_ai_config()
    logger.info("")
    logger.info("=" * 60)
    logger.info("  GoldMind AI Signal Backend")
    logger.info("=" * 60)
    logger.info(f"  AI Provider: {configured_provider}; configured: {bool(configured_models)}")
    if configured_models:
        logger.info(f"  AI Model: {configured_models[0]}")
    logger.info(f"  Server:   http://127.0.0.1:8000")
    logger.info(f"  Health:   http://127.0.0.1:8000/health")
    logger.info(f"  Signal:   http://127.0.0.1:8000/signal  (POST)")
    logger.info("=" * 60)
    logger.info("  Waiting for signal requests from MT5 EA...")
    logger.info("=" * 60)
    _start_mobile_discovery()
    asyncio.create_task(_binance_gold_feed_loop())
    if start_telegram():
        logger.info("  Telegram signal notifier: ENABLED")
    else:
        logger.info("  Telegram signal notifier: disabled (token not configured)")
    logger.info("")

# ---------------------------------------------------------------------------
# Pydantic models — Request
# ---------------------------------------------------------------------------

class CandleData(BaseModel):
    time: str = Field(..., description="Candle open time ISO‑8601")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Constraints(BaseModel):
    max_spread_points: int = 50
    risk_percent: float = 1.0
    min_rr: float = 1.5
    expiry_minutes: int = 240


class SignalRequest(BaseModel):
    account_id: Optional[str] = None
    symbol: str = "XAUUSD"  # Default fallback; EA always sends _Symbol explicitly
    timeframe: str = "M15"
    server_time_utc: str = ""
    bid: float
    ask: float
    spread_points: int
    digits: int = 2
    point: float = 0.01
    candles: dict[str, list[CandleData]]
    atr: Optional[float] = None
    constraints: Constraints = Constraints()


# ---------------------------------------------------------------------------
# Pydantic models — Response  (also doubles as the JSON schema for OpenAI)
# ---------------------------------------------------------------------------

class BiasEnum(str, Enum):
    bullish = "bullish"
    bearish = "bearish"
    neutral = "neutral"


class OrderTypeEnum(str, Enum):
    buy_stop = "buy_stop"
    sell_stop = "sell_stop"
    none = "none"


class OrderResponse(BaseModel):
    type: OrderTypeEnum
    entry: float
    sl: float
    tp: float
    expiry_minutes: int
    comment: str


class SignalResponse(BaseModel):
    symbol: str
    timestamp_utc: str
    bias: BiasEnum
    order: OrderResponse
    confidence: float = Field(..., ge=0.0, le=1.0)
    veto: bool
    veto_reason: str


# ---------------------------------------------------------------------------
# Helper: compute ATR from candles
# ---------------------------------------------------------------------------

def compute_atr(candles: dict[str, list[CandleData]], period: int = 14) -> float:
    """Compute ATR using the short-horizon M5 series first, then M1/M15/H1."""
    # The primary use case is a signal for roughly the next 10 minutes.
    tf_to_use = None
    for preferred_tf in ("M5", "M1", "M15", "H1"):
        if preferred_tf in candles and candles[preferred_tf]:
            tf_to_use = preferred_tf
            break
    elif candles:
        tf_to_use = list(candles.keys())[0]
        
    if not tf_to_use or len(candles[tf_to_use]) < 2:
        return 0.0
        
    c_list = candles[tf_to_use]
    trs: list[float] = []
    for i in range(1, len(c_list)):
        high = c_list[i].high
        low = c_list[i].low
        prev_close = c_list[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    # Simple moving average of the last `period` true ranges
    p = min(period, len(trs))
    return sum(trs[-p:]) / p


# ---------------------------------------------------------------------------
# Helper: build veto response
# ---------------------------------------------------------------------------

def veto_response(symbol: str, reason: str) -> SignalResponse:
    return SignalResponse(
        symbol=symbol,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        bias=BiasEnum.neutral,
        order=OrderResponse(
            type=OrderTypeEnum.none,
            entry=0.0,
            sl=0.0,
            tp=0.0,
            expiry_minutes=0,
            comment="",
        ),
        confidence=0.0,
        veto=True,
        veto_reason=reason,
    )


def _publish_veto(req: "SignalRequest", reason: str) -> SignalResponse:
    """Publish a safe WAIT state to mobile for every rejected/failed signal request."""
    signal = veto_response(req.symbol, reason)
    _publish_mobile_state(req, signal)
    return signal


# ---------------------------------------------------------------------------
# Build the JSON schema dict for OpenAI Structured Outputs
# ---------------------------------------------------------------------------

SIGNAL_JSON_SCHEMA = {
    "name": "trading_signal",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "timestamp_utc": {"type": "string"},
            "bias": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
            "order": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["buy_stop", "sell_stop", "none"]},
                    "entry": {"type": "number"},
                    "sl": {"type": "number"},
                    "tp": {"type": "number"},
                    "expiry_minutes": {"type": "integer"},
                    "comment": {"type": "string"},
                },
                "required": ["type", "entry", "sl", "tp", "expiry_minutes", "comment"],
                "additionalProperties": False,
            },
            "confidence": {"type": "number"},
            "veto": {"type": "boolean"},
            "veto_reason": {"type": "string"},
        },
        "required": [
            "symbol",
            "timestamp_utc",
            "bias",
            "order",
            "confidence",
            "veto",
            "veto_reason",
        ],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------------
# Helper: classify instrument type from symbol name
# ---------------------------------------------------------------------------

def classify_instrument(symbol: str) -> dict:
    """Classify a trading instrument and return its display name, specialty, and
    session-specific liquidity descriptions.  Covers gold, silver, oil, indices,
    crypto, and forex (default)."""
    sym = symbol.upper().replace(".", "").replace("_", "").replace("-", "")

    # --- Gold ---
    if any(tag in sym for tag in ["XAUUSD", "GOLD"]):
        return {
            "type": "commodity", "name": "gold (XAUUSD)",
            "specialty": "breakout and momentum trading on gold",
            "sessions": {
                "overlap": "peak liquidity — highest volume and volatility for gold",
                "london":  "high liquidity — strong gold trading activity",
                "newyork": "good liquidity — active gold trading",
                "asian":   "lower liquidity — gold typically range-bound, breakouts less reliable",
            },
        }
    # --- Silver ---
    if any(tag in sym for tag in ["XAGUSD", "SILVER"]):
        return {
            "type": "commodity", "name": "silver (XAGUSD)",
            "specialty": "breakout and momentum trading on silver",
            "sessions": {
                "overlap": "peak liquidity — highest volume and volatility for silver",
                "london":  "high liquidity — strong silver trading activity",
                "newyork": "good liquidity — active silver trading",
                "asian":   "lower liquidity — silver typically range-bound, breakouts less reliable",
            },
        }
    # --- Oil ---
    if any(tag in sym for tag in ["USOIL", "UKOIL", "WTI", "BRENT", "XTIUSD", "XBRUSD", "CL", "CRUDE"]):
        return {
            "type": "commodity", "name": f"crude oil ({symbol})",
            "specialty": "breakout and momentum trading on oil",
            "sessions": {
                "overlap": "peak liquidity — London and NY energy markets overlap",
                "london":  "high liquidity — European energy session active",
                "newyork": "peak liquidity — US oil benchmarks most active",
                "asian":   "lower liquidity — oil typically quieter, breakouts less reliable",
            },
        }
    # --- Indices ---
    if any(tag in sym for tag in ["US30", "US500", "US100", "NAS", "SPX", "NDX", "DJI", "DAX", "FTSE", "NI225", "HSI", "UK100", "DE40", "JP225"]):
        return {
            "type": "index", "name": f"{symbol} index",
            "specialty": f"breakout and momentum trading on {symbol}",
            "sessions": {
                "overlap": "peak liquidity — London and New York equity sessions overlap",
                "london":  "high liquidity — European equity session active",
                "newyork": "peak liquidity — US equity session, highest index volume",
                "asian":   "moderate liquidity — index futures trade but with less volume",
            },
        }
    # --- Crypto ---
    if any(tag in sym for tag in ["BTC", "ETH", "XRP", "LTC", "SOL", "DOGE", "ADA", "BNB"]):
        return {
            "type": "crypto", "name": f"{symbol} crypto",
            "specialty": f"breakout and momentum trading on {symbol}",
            "sessions": {
                "overlap": "good liquidity — crypto trades 24/7 but volume follows traditional sessions",
                "london":  "good liquidity — European crypto activity picks up",
                "newyork": "peak liquidity — US crypto trading most active",
                "asian":   "good liquidity — Asian crypto markets active, often sets direction",
            },
        }
    # --- Forex (default) ---
    return {
        "type": "forex", "name": symbol,
        "specialty": f"breakout and momentum trading on {symbol}",
        "sessions": {
            "overlap": "peak liquidity — highest forex volume and tightest spreads",
            "london":  "high liquidity — strong forex trading activity",
            "newyork": "good liquidity — active forex trading",
            "asian":   "lower liquidity — pairs typically range-bound, breakouts less reliable",
        },
    }


# ---------------------------------------------------------------------------
# Helper: determine trading session and Malaysia time
# ---------------------------------------------------------------------------

def get_session_info(utc_time: datetime, symbol: str = "XAUUSD") -> dict:
    """Determine the current trading session with instrument-aware liquidity notes."""
    myt_time = utc_time + timedelta(hours=8)  # Malaysia is UTC+8
    hour_utc = utc_time.hour
    instrument = classify_instrument(symbol)

    # Trading sessions (approximate UTC ranges)
    # Asian/Sydney:  22:00 – 07:00 UTC
    # London:        07:00 – 16:00 UTC
    # New York:      13:00 – 22:00 UTC
    # Overlaps:      London-NY 13:00–16:00 UTC
    if 13 <= hour_utc < 16:
        session = "London-New York overlap"
        liquidity = instrument["sessions"]["overlap"]
    elif 7 <= hour_utc < 13:
        session = "London session"
        liquidity = instrument["sessions"]["london"]
    elif 16 <= hour_utc < 22:
        session = "New York session"
        liquidity = instrument["sessions"]["newyork"]
    else:
        session = "Asian/Sydney session"
        liquidity = instrument["sessions"]["asian"]

    return {
        "session": session,
        "liquidity": liquidity,
        "instrument": instrument,
        "myt_str": myt_time.strftime("%Y-%m-%d %H:%M MYT"),
        "utc_str": utc_time.strftime("%Y-%m-%d %H:%M UTC"),
    }


# ---------------------------------------------------------------------------
# Build system prompt for OpenAI
# ---------------------------------------------------------------------------

def _timeframe_alignment(candles: dict[str, list[CandleData]]) -> tuple[str, int, int, str]:
    """Return directional vote counts from M5/M15/H1/H4/D1 closed candles."""
    bullish = bearish = 0
    notes = []
    for tf in ("M5", "M15", "H1", "H4", "D1"):
        closes = [c.close for c in candles[tf]]
        if len(closes) < 21:
            return "neutral", 0, 0, f"{tf}_insufficient_history"
        prior_window = closes[-21:-1]
        previous_ema = sum(prior_window) / len(prior_window)
        alpha = 2.0 / 21.0
        latest_close = closes[-1]
        ema = alpha * latest_close + (1.0 - alpha) * previous_ema
        prior_close = closes[-2]
        if latest_close > ema and ema > previous_ema and latest_close > prior_close:
            bullish += 1
            notes.append(f"{tf}:bull")
        elif latest_close < ema and ema < previous_ema and latest_close < prior_close:
            bearish += 1
            notes.append(f"{tf}:bear")
        else:
            notes.append(f"{tf}:mixed")
    if bullish >= 4:
        direction = "bullish"
    elif bearish >= 4:
        direction = "bearish"
    else:
        direction = "neutral"
    return direction, bullish, bearish, ",".join(notes)


def build_system_prompt(req: SignalRequest, atr_value: float) -> str:
    now_utc = datetime.now(timezone.utc)
    session = get_session_info(now_utc, req.symbol)
    inst = session["instrument"]

    return f"""You are a professional {inst['name']} SIGNAL-ONLY trading analyst. You provide analysis for a human trader.
You specialize in {inst['specialty']}. NEVER execute, place, modify, cancel, or manage any order. The returned order object is ONLY a hypothetical trade plan for display to the human trader.
The goal is to find a high-quality short-horizon opportunity, preferably suitable for the next 10 minutes, but return WAIT when the data is stale, contradictory, or insufficient.

═══ INSTRUMENT ═══
- Symbol: {req.symbol}
- Type: {inst['type']}

═══ CURRENT MARKET CONTEXT ═══
- Server time: {session['utc_str']} (Malaysia: {session['myt_str']})
- Trading session: {session['session']} — {session['liquidity']}
- Current price: Bid={req.bid}, Ask={req.ask}, Spread={req.spread_points} pts
- Primary Timeframe: {req.timeframe} (Multi-timeframe data provided below)
- ATR(14): {atr_value:.5f} (recent average volatility per candle)

═══ ANALYSIS FRAMEWORK ═══
Before making your decision, mentally perform these analysis steps:

1. TECHNICAL ANALYSIS:
   - Identify key support and resistance levels from the candle data
   - Determine the prevailing trend direction (bullish, bearish, or sideways)
   - Look for candlestick patterns (engulfing, pin bars, breakout candles)
   - Use ATR to gauge current volatility and set appropriate distances

2. MACRO / PRICE CONTEXT:
   - Where is price relative to its recent range? Near highs, lows, or mid-range?
   - Is there a clear trending structure (higher highs/lows or lower highs/lows)?
   - Is the market in a consolidation/squeeze that could lead to a breakout?

3. SESSION CONTEXT:
   - Current session: {session['session']}. {session['liquidity']}.
   - During Asian session, prefer wider stops and be cautious with breakouts.
   - During London/NY, breakouts are more reliable — look for momentum.
   - During London-NY overlap, expect the strongest moves.

4. STRATEGY DECISION:
   Based on the above, choose the best approach:
   - BREAKOUT: Propose a hypothetical pending-entry level beyond a key level for the human trader to consider.
   - WAIT: Prefer WAIT when evidence is weak, contradictory, stale, or the setup is not suitable for the next 10 minutes.
   - Never force a trade. Signal quality is more important than signal frequency.

═══ SIGNAL PLAN RULES — follow these exactly ═══
1. The order object is informational only. It is NEVER executed by this system.
2. buy_stop: entry ABOVE Ask + buffer (at least Ask + 1×ATR)
   sell_stop: entry BELOW Bid - buffer (at least Bid - 1×ATR)
3. SL must be on the opposite side of entry:
   - buy_stop: SL < entry (e.g. entry - 1.5×ATR)
   - sell_stop: SL > entry (e.g. entry + 1.5×ATR)
4. TP placement — use your best technical judgement:
   - Minimum risk/reward from settings: {req.constraints.min_rr}; this is enforced by the server and is a hard gate.
   - Place TP at a technical level that meets the minimum R:R (key S/R, ATR target, etc.).
   - If no realistic target meets the minimum R:R, return WAIT.
   - The goal is the best risk-adjusted trade, not a forced setup
5. expiry_minutes should normally be {req.constraints.expiry_minutes} minutes because the target is a short-horizon signal.
6. Provide a short comment (max 30 chars) describing the setup.
7. If spread ({req.spread_points} pts) > max allowed ({req.constraints.max_spread_points} pts),
   OR if no clear short-horizon setup exists, set order.type="none", veto=true,
   veto_reason explaining why.
8. All prices must be rounded to {req.digits} decimal places.
9. symbol = "{req.symbol}". timestamp_utc = current UTC time in ISO-8601.

═══ CONFIDENCE GUIDE ═══
- 0.75–1.00: Candidate only; server independently requires at least 4 of 5 M5/M15/H1/H4/D1 trends to align.
- Below 0.75: Veto. Do not propose an entry.
- Model confidence is not a measured win rate; final displayed score is calculated from timeframe confluence.

Respond ONLY with valid JSON matching the required schema. No extra text."""


# ---------------------------------------------------------------------------
# Build user message with candle data
# ---------------------------------------------------------------------------

def build_user_message(req: SignalRequest) -> str:
    lines = []
    
    # Process each timeframe
    for tf, tf_candles in req.candles.items():
        if not tf_candles:
            continue
            
        candle_subset = tf_candles[-60:] # Limit to 60 candles per timeframe for context

        # Compute a quick market structure summary from the candles
        highs = [c.high for c in candle_subset]
        lows = [c.low for c in candle_subset]
        recent_high = max(highs)
        recent_low = min(lows)
        price_range = recent_high - recent_low
        mid_price = req.bid
        position_pct = ((mid_price - recent_low) / price_range * 100) if price_range > 0 else 50.0

        # Simple trend from first vs last candle
        first_close = candle_subset[0].close
        last_close = candle_subset[-1].close
        trend_change = last_close - first_close
        trend_dir = "bullish" if trend_change > 0 else "bearish" if trend_change < 0 else "flat"

        lines.extend([
            f"═══ {tf} MARKET STRUCTURE SUMMARY ═══",
            f"Recent 60-candle high: {recent_high}",
            f"Recent 60-candle low:  {recent_low}",
            f"Current price position: {position_pct:.0f}% of range (0%=at low, 100%=at high)",
            f"Short-term trend: {trend_dir} (moved {trend_change:+.{req.digits}f} over last 60 candles)",
            "",
            f"═══ {tf} CANDLE DATA (newest last) ═══",
        ])
        for c in candle_subset:
            lines.append(
                f"  {c.time} O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}"
            )
        lines.append("")

    lines.append(f"Bid={req.bid} Ask={req.ask} Spread={req.spread_points}pts")
    lines.append(f"Digits={req.digits} Point={req.point}")
    lines.append("\nAnalyze the market using the framework above and produce the trading signal.")
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Independent Binance gold market-data feed (no MT5 required)
# ---------------------------------------------------------------------------
BINANCE_FAPI_BASE = "https://fapi.binance.com"
BINANCE_GOLD_SYMBOL = "XAUUSDT"
BINANCE_POINT = 0.01
BIQUOTE_BASE = "https://biquote.io"
MAX_QUOTE_AGE_SECONDS = 15
REQUIRED_TIMEFRAMES = {"M1": 30, "M5": 30, "M15": 30, "M30": 30, "H1": 21, "H4": 21, "D1": 21}
TIMEFRAME_MAX_AGE_SECONDS = {"M1": 125, "M5": 615, "M15": 1815, "M30": 7215, "H1": 64815, "H4": 259215, "D1": 432015}
_ACTIVE_MARKET_SOURCE = "Binance USDⓈ-M Futures"
_ACTIVE_SOURCE_SYMBOL = BINANCE_GOLD_SYMBOL
_ACTIVE_SOURCE_NOTE = "Gold perpetual quote; may differ from broker XAUUSD"


def _fetch_json(base_url: str, path: str, params: dict) -> object:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{base_url}{path}?{query}",
        headers={"User-Agent": "GoldTraderPro/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_binance_json(path: str, params: dict) -> object:
    """Fetch public Binance USDⓈ-M Futures market data; no API key is required."""
    return _fetch_json(BINANCE_FAPI_BASE, path, params)


def _fetch_biquote_json(path: str, params: dict) -> object:
    """Fetch public broker-feed market data from BiQuote; no API key is required."""
    return _fetch_json(BIQUOTE_BASE, path, params)


def _to_candles(rows: list, now_ms: int, limit: int) -> list[CandleData]:
    """Convert only closed Binance candles; never analyze a still-forming candle."""
    closed = [row for row in rows if int(row[6]) < now_ms]
    return [CandleData(
        time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).isoformat(),
        open=float(row[1]), high=float(row[2]), low=float(row[3]),
        close=float(row[4]), volume=float(row[5]),
    ) for row in closed[-limit:]]


def _to_biquote_candles(payload: dict, limit: int) -> list[CandleData]:
    """Convert only closed BiQuote OHLC bars into validated candles."""
    bars = payload.get("bars", []) if isinstance(payload, dict) else []
    result = []
    for bar in bars:
        if bar.get("isOpen", False):
            continue
        opened = bar.get("openTime")
        if not opened:
            continue
        result.append(CandleData(
            time=datetime.fromisoformat(opened.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
            open=float(bar["open"]), high=float(bar["high"]), low=float(bar["low"]),
            close=float(bar["close"]), volume=float(bar.get("volume") or bar.get("tickVolume") or 0),
        ))
    result.sort(key=lambda candle: candle.time)
    return result[-limit:]


def _validate_feed_candles(candles: dict[str, list[CandleData]], now: datetime) -> None:
    """Reject incomplete, malformed, out-of-order, or stale closed-candle series."""
    for tf, minimum in REQUIRED_TIMEFRAMES.items():
        series = candles.get(tf, [])
        if len(series) < minimum:
            raise ValueError(f"{tf} has insufficient closed candles ({len(series)} < {minimum})")
        parsed_times = []
        for candle in series:
            values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"{tf} contains non-finite candle values")
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                raise ValueError(f"{tf} contains non-positive OHLC values")
            if candle.high < max(candle.open, candle.close, candle.low) or candle.low > min(candle.open, candle.close, candle.high):
                raise ValueError(f"{tf} contains invalid OHLC geometry")
            candle_time = datetime.fromisoformat(candle.time.replace("Z", "+00:00")).astimezone(timezone.utc)
            if candle_time > now + timedelta(seconds=5):
                raise ValueError(f"{tf} contains a future candle")
            parsed_times.append(candle_time)
        if parsed_times != sorted(parsed_times) or len(set(parsed_times)) != len(parsed_times):
            raise ValueError(f"{tf} candles are not strictly chronological")
        age = (now - parsed_times[-1]).total_seconds()
        if age < -5 or age > TIMEFRAME_MAX_AGE_SECONDS[tf]:
            raise ValueError(f"{tf} last closed candle is stale (age={age:.1f}s)")


async def _load_binance_market():
    """Load timestamped Binance gold data and closed candles across all required timeframes."""
    book, trades, *rows_by_tf = await asyncio.gather(
        asyncio.to_thread(_fetch_binance_json, "/fapi/v1/ticker/bookTicker", {"symbol": BINANCE_GOLD_SYMBOL}),
        asyncio.to_thread(_fetch_binance_json, "/fapi/v1/aggTrades", {"symbol": BINANCE_GOLD_SYMBOL, "limit": 1}),
        *[
            asyncio.to_thread(_fetch_binance_json, "/fapi/v1/klines", {"symbol": BINANCE_GOLD_SYMBOL, "interval": interval, "limit": limit})
            for interval, limit in (("1m", 120), ("5m", 80), ("15m", 80), ("30m", 80), ("1h", 80), ("4h", 80), ("1d", 80))
        ],
    )
    now = datetime.now(timezone.utc)
    if not isinstance(trades, list) or not trades:
        raise ValueError("Binance has no timestamped recent gold trade")
    trade_ms = int(trades[-1].get("T", 0))
    quote_time = datetime.fromtimestamp(trade_ms / 1000, tz=timezone.utc)
    quote_age = (now - quote_time).total_seconds()
    if quote_age < -5 or quote_age > MAX_QUOTE_AGE_SECONDS:
        raise ValueError(f"Binance last trade is stale or future-dated (age={quote_age:.1f}s)")
    bid, ask = float(book["bidPrice"]), float(book["askPrice"])
    intervals = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
    candles = {tf: _to_candles(rows, int(now.timestamp() * 1000), 60) for tf, rows in zip(intervals, rows_by_tf)}
    if not (bid > 0 and ask >= bid):
        raise ValueError("Binance returned invalid bid/ask")
    _validate_feed_candles(candles, now)
    return quote_time, bid, ask, candles, "Binance USDⓈ-M Futures", BINANCE_GOLD_SYMBOL, "Gold perpetual quote; may differ from broker XAUUSD"


async def _load_biquote_market():
    """Load a timestamped broker-style XAUUSD quote and closed MTF candles."""
    tick, *payloads = await asyncio.gather(
        asyncio.to_thread(_fetch_biquote_json, "/api/XAUUSD", {"allowStale": "false"}),
        *[
            asyncio.to_thread(_fetch_biquote_json, "/api/XAUUSD/ohlc", {"interval": interval, "limit": 80})
            for interval in ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
        ],
    )
    now = datetime.now(timezone.utc)
    bid, ask = float(tick["bid"]), float(tick["ask"])
    quote_time_raw = tick.get("timestamp") or tick.get("lastQuoteAt")
    if not quote_time_raw:
        raise ValueError("BiQuote tick has no timestamp")
    quote_time = datetime.fromisoformat(quote_time_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    quote_age = (now - quote_time).total_seconds()
    if quote_age < -5 or quote_age > MAX_QUOTE_AGE_SECONDS or tick.get("stale", True) or tick.get("marketState") != "open":
        raise ValueError(f"BiQuote quote is stale or market is not open (age={quote_age:.1f}s)")
    intervals = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
    candles = {tf: _to_biquote_candles(payload, 60) for tf, payload in zip(intervals, payloads)}
    if not (bid > 0 and ask >= bid):
        raise ValueError("BiQuote returned invalid bid/ask")
    _validate_feed_candles(candles, now)
    return quote_time, bid, ask, candles, "BiQuote broker XAUUSD feed", "XAUUSD", "Broker-feed spot quote; verify it matches your broker"


async def _binance_gold_feed_loop() -> None:
    """Prefer Binance gold perpetual; fall back to a fresh broker-style XAUUSD feed."""
    global _ACTIVE_MARKET_SOURCE, _ACTIVE_SOURCE_SYMBOL, _ACTIVE_SOURCE_NOTE
    last_analyzed_open = None
    logger.info("Gold market feed starting: Binance XAUUSDT, with BiQuote XAUUSD fallback")
    while True:
        try:
            try:
                market = await _load_binance_market()
            except Exception as primary_error:
                logger.warning("Binance gold feed unavailable; trying BiQuote fallback: %s", primary_error)
                market = await _load_biquote_market()

            now, bid, ask, candles, source, source_symbol, source_note = market
            _ACTIVE_MARKET_SOURCE = source
            _ACTIVE_SOURCE_SYMBOL = source_symbol
            _ACTIVE_SOURCE_NOTE = source_note
            latest_open = candles["M1"][-1].time
            is_new_candle = latest_open != last_analyzed_open

            # Preserve the last completed signal between feed polls within the same
            # one-minute candle. Previously every 15-second poll reset signal=None,
            # so Android almost always saw a price but no signal.
            previous_signal = _latest_mobile_state.get("signal")
            if is_new_candle:
                published_signal = None
            else:
                published_signal = previous_signal
                if published_signal:
                    try:
                        signal_time = datetime.fromisoformat(
                            published_signal.get("timestamp_utc", "").replace("Z", "+00:00")
                        ).astimezone(timezone.utc)
                        signal_age = (now - signal_time).total_seconds()
                        if signal_age > 120 or signal_age < -30:
                            published_signal = None
                    except (TypeError, ValueError):
                        published_signal = None

            _latest_mobile_state.clear()
            _latest_mobile_state.update({
                "price": f"{bid:.2f}", "symbol": "XAUUSD", "signal": published_signal,
                "protection": {"mode": "OFF"}, "source": source,
                "source_symbol": source_symbol, "updated_at_utc": now.isoformat(),
                "data_status": "LIVE", "note": source_note,
            })

            if is_new_candle:
                last_analyzed_open = latest_open
                spread_points = max(0, round((ask - bid) / BINANCE_POINT))
                req = SignalRequest(
                    symbol="XAUUSD", timeframe="M1", server_time_utc=now.isoformat(),
                    bid=bid, ask=ask, spread_points=spread_points, digits=2,
                    point=BINANCE_POINT, candles=candles, atr=compute_atr(candles),
                    constraints=Constraints(),
                )
                logger.info(
                    "%s gold data refreshed: bid=%.2f ask=%.2f candles M1=%d M5=%d M15=%d",
                    source, bid, ask, len(candles["M1"]), len(candles["M5"]), len(candles["M15"]),
                )
                await generate_signal(req)
        except Exception as exc:
            logger.warning("All gold market data feeds unavailable: %s", exc)
            _latest_mobile_state.clear()
            _latest_mobile_state.update({
                "price": "", "symbol": "XAUUSD", "signal": None,
                "protection": {"mode": "OFF"}, "source": "Unavailable",
                "source_symbol": None, "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "data_status": "NO_DATA", "note": "Live quote unavailable or stale; no signal",
            })
        await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/state")
async def mobile_state():
    """Read-only state endpoint used by the Android signal client."""
    return _latest_mobile_state


@app.get("/health")
async def health():
    logger.info("Health check requested")
    return {"status": "ok"}


@app.post("/signal", response_model=SignalResponse)
async def generate_signal(req: SignalRequest):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    logger.info("")
    logger.info("─" * 60)
    logger.info(f"📥 [{now}] Signal request received")
    if req.account_id:
        logger.info(f"   Account: {req.account_id}")
    logger.info(f"   Symbol: {req.symbol}  Timeframe: {req.timeframe}")
    logger.info(f"   Bid: {req.bid}  Ask: {req.ask}  Spread: {req.spread_points}pts")
    # Log per-timeframe candle counts
    tf_summary = ", ".join(f"{tf}={len(c)}" for tf, c in req.candles.items())
    total_candles = sum(len(c) for c in req.candles.values())
    logger.info(f"   Candles: {total_candles} total across {len(req.candles)} timeframes")
    logger.info(f"   Timeframes: {tf_summary}")
    logger.info(f"   ATR: {req.atr}")
    logger.info(f"   Model: {OPENAI_MODEL}")

    # 0. Hard data-quality gate: quote timestamp, price geometry, and required timeframes.
    try:
        quote_time = datetime.fromisoformat(req.server_time_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return _publish_veto(req, "invalid_or_missing_quote_timestamp")
    quote_age = (datetime.now(timezone.utc) - quote_time).total_seconds()
    if quote_age < -5 or quote_age > MAX_QUOTE_AGE_SECONDS:
        return _publish_veto(req, f"stale_market_quote:{quote_age:.1f}s")
    if not (math.isfinite(req.bid) and math.isfinite(req.ask) and math.isfinite(req.point) and req.bid > 0 and req.ask >= req.bid and req.point > 0 and req.spread_points >= 0):
        return _publish_veto(req, "invalid_bid_ask_or_point")
    try:
        _validate_feed_candles(req.candles, datetime.now(timezone.utc))
    except (ValueError, TypeError, OverflowError) as exc:
        return _publish_veto(req, f"invalid_market_candles:{str(exc)[:100]}")

    # 1. Compute ATR if not provided
    atr_value = req.atr if req.atr is not None else compute_atr(req.candles)

    # 2. Hard symbol/data gates. This build is intentionally XAUUSD signal-only.
    sym = req.symbol.upper().replace(".", "").replace("_", "").replace("-", "")
    if "XAUUSD" not in sym and "GOLD" not in sym:
        logger.warning(f"   🚫 VETO: unsupported symbol {req.symbol}; XAUUSD/GOLD only")
        return _publish_veto(req, "unsupported_symbol")
    if not req.candles or sum(len(v) for v in req.candles.values()) < 30:
        logger.warning("   🚫 VETO: insufficient market data")
        return _publish_veto(req, "insufficient_data")
    if not math.isfinite(atr_value) or atr_value <= 0:
        logger.warning("   🚫 VETO: ATR unavailable or invalid")
        return _publish_veto(req, "atr_unavailable")

    # 3. Quick spread veto (server-side too, belt-and-suspenders)
    if req.spread_points > req.constraints.max_spread_points:
        logger.warning(f"   🚫 VETO: Spread {req.spread_points} > max {req.constraints.max_spread_points}")
        logger.info("─" * 60)
        return _publish_veto(req, f"spread {req.spread_points} > max {req.constraints.max_spread_points}")

    # 4. Call the configured AI provider with structured JSON output.
    client, selected_provider, models_to_try = _get_ai_config()
    if not client or not models_to_try:
        logger.warning("No AI provider credential configured; returning safe WAIT state")
        return _publish_veto(req, "model_unavailable: configure a free Gemini API key or a supported provider")

    messages = [
        {"role": "system", "content": build_system_prompt(req, atr_value)},
        {"role": "user", "content": build_user_message(req)},
    ]

    last_error = None
    for model in models_to_try:
        try:
            is_fallback = model != OPENAI_MODEL
            if is_fallback:
                logger.warning(f"   🔄 Falling back to {model}...")
            else:
                logger.info(f"   ⏳ Calling {selected_provider} ({model})...")
            sys.stdout.flush()
            start_time = time.time()

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": SIGNAL_JSON_SCHEMA,
                    },
                ),
                timeout=90.0,  # Hard 90s deadline — force-cancel if OpenAI hangs
            )

            elapsed = time.time() - start_time

            # Token usage
            usage = response.usage
            if usage:
                logger.info(f"   📊 Tokens: {usage.prompt_tokens} in + {usage.completion_tokens} out = {usage.total_tokens} total")
            logger.info(f"   ⏱️  Response time: {elapsed:.1f}s")
            if is_fallback:
                logger.info(f"   ℹ️  Used fallback model: {model}")

            # Extract the text output from the response
            raw_json = response.choices[0].message.content

            # Parse into our Pydantic model for validation
            signal = SignalResponse.model_validate_json(raw_json)

            # The model may take long enough for the quote to become stale.
            # Never publish a signal based on a quote older than the hard freshness limit.
            request_quote_time = datetime.fromisoformat(req.server_time_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
            if (datetime.now(timezone.utc) - request_quote_time).total_seconds() > MAX_QUOTE_AGE_SECONDS:
                return _publish_veto(req, "market_data_became_stale_during_analysis")

            # Stamp the decision time only after confirming the source quote is still fresh.
            signal.timestamp_utc = datetime.now(timezone.utc).isoformat()

            # Hard server-side validation: AI output is informational only and never executed.
            side = signal.order.type.value
            if side == "buy_stop":
                valid = signal.order.entry > req.ask and signal.order.sl < signal.order.entry < signal.order.tp
                expected_bias = "bullish"
            elif side == "sell_stop":
                valid = signal.order.entry < req.bid and signal.order.sl > signal.order.entry > signal.order.tp
                expected_bias = "bearish"
            else:
                valid = True
                expected_bias = "neutral"
            levels = (signal.order.entry, signal.order.sl, signal.order.tp)
            if side != "none" and not all(math.isfinite(value) and value > 0 for value in levels):
                valid = False
            if signal.veto:
                signal.order.type = OrderTypeEnum.none
                signal.order.entry = 0.0
                signal.order.sl = 0.0
                signal.order.tp = 0.0
                signal.order.expiry_minutes = 0
            elif not valid:
                logger.warning("   🚫 VETO: invalid signal geometry returned by model")
                return _publish_veto(req, "invalid_signal_geometry")
            elif side != "none":
                if signal.confidence < 0.75:
                    return _publish_veto(req, f"model_confidence_below_75:{signal.confidence:.2f}")
                if signal.bias.value != expected_bias:
                    return _publish_veto(req, "ai_bias_order_side_disagreement")
                direction, bull_votes, bear_votes, alignment = _timeframe_alignment(req.candles)
                if direction != expected_bias:
                    return _publish_veto(req, f"multi_timeframe_disagreement:{alignment}")
                # Display a transparent five-timeframe confluence score, not a claimed win probability.
                signal.confidence = max(bull_votes, bear_votes) / 5.0
                signal.order.comment = f"{signal.order.comment[:15]} MTF {max(bull_votes, bear_votes)}/5"
                entry, sl, tp = levels
                sl_dist = abs(entry - sl)
                tp_dist = abs(tp - entry)
                rr = tp_dist / sl_dist if sl_dist > 0 else 0
                if sl_dist <= 0 or rr < req.constraints.min_rr:
                    return _publish_veto(req, f"risk_reward_below_minimum:{rr:.2f}")
                logger.info(f"   📐 R:R ratio: {rr:.2f}; MTF alignment: {alignment}")

            # No order is submitted; this remains a signal-only display payload.

            # Log the result
            if signal.veto:
                logger.warning(f"   🚫 VETO: {signal.veto_reason}")
            else:
                logger.info(f"   ✅ Signal: {signal.bias.value.upper()} (confidence: {signal.confidence:.0%})")
                logger.info(f"   📋 Order: {signal.order.type.value}")
                logger.info(f"      Entry: {signal.order.entry}  SL: {signal.order.sl}  TP: {signal.order.tp}")
                logger.info(f"      Comment: {signal.order.comment}")
            logger.info("─" * 60)

            _publish_mobile_state(req, signal)
            sent = send_telegram_signal(signal)
            if sent:
                logger.info(f"   📲 Telegram: signal sent to {sent} chat(s)")
            return signal

        except (openai.APITimeoutError, asyncio.TimeoutError) as e:
            last_error = e
            logger.error(f"   ⏰ {model} timed out after 90s: {e}")
            if not is_fallback and len(models_to_try) > 1:
                logger.info(f"   ↪ Will try fallback model...")
            continue

        except Exception as e:
            last_error = e
            logger.error(f"   ❌ {selected_provider} model {model} failed: {e}")
            if not is_fallback and len(models_to_try) > 1:
                logger.info(f"   ↪ Will try fallback model...")
            continue

    # All models failed
    logger.error(f"   ❌ All models failed. Last error: {last_error}")
    traceback.print_exc()
    logger.info("─" * 60)
    return _publish_veto(req, "model_unavailable")


# ---------------------------------------------------------------------------
# Run directly: python main.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disabled: reload subprocess breaks file logging
        log_level="info",
    )
