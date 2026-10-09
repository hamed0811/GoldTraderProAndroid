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
        "source": "Binance USDⓈ-M Futures",
        "source_symbol": "XAUUSDT",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_status": "LIVE",
        "note": "Gold perpetual quote; may differ from broker XAUUSD",
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
    key_preview = OPENAI_API_KEY[:8] + "..." + OPENAI_API_KEY[-4:] if len(OPENAI_API_KEY) > 12 else "NOT SET"
    logger.info("")
    logger.info("=" * 60)
    logger.info("  GoldMind AI Signal Backend")
    logger.info("=" * 60)
    logger.info(f"  Model:    {OPENAI_MODEL} (fallback: {FALLBACK_MODEL})")
    logger.info(f"  API Key:  {key_preview}")
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
    """Compute Average True Range from candle list (defaults to H1 or M15)."""
    # Pick a timeframe to calculate ATR, prefer H1, else M15, else the first available
    tf_to_use = None
    if "H1" in candles and candles["H1"]:
        tf_to_use = "H1"
    elif "M15" in candles and candles["M15"]:
        tf_to_use = "M15"
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
   - R:R benchmark from settings: {req.constraints.min_rr} (reference only, NOT a hard rule)
   - Place TP at the level that makes the most sense technically (key S/R, Fib extensions, ATR targets, etc.)
   - You may use a HIGHER or LOWER R:R than {req.constraints.min_rr} if the chart structure supports it
   - The goal is the best risk-adjusted trade, not a fixed R:R ratio
5. expiry_minutes should normally be {req.constraints.expiry_minutes} minutes because the target is a short-horizon signal.
6. Provide a short comment (max 30 chars) describing the setup.
7. If spread ({req.spread_points} pts) > max allowed ({req.constraints.max_spread_points} pts),
   OR if no clear short-horizon setup exists, set order.type="none", veto=true,
   veto_reason explaining why.
8. All prices must be rounded to {req.digits} decimal places.
9. symbol = "{req.symbol}". timestamp_utc = current UTC time in ISO-8601.

═══ CONFIDENCE GUIDE ═══
- 0.80–1.00: Strong conviction — clear trend, key level breakout, good session, multiple confirming factors.
- 0.60–0.79: Moderate conviction — decent setup but some uncertainty. Still a viable trade.
- 0.40–0.59: Weak setup — acceptable if you want to test a level, but consider vetoing if conditions are extremely poor.
- Below 0.40: Veto. Do not trade.

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


def _fetch_binance_json(path: str, params: dict) -> object:
    """Fetch public Binance USDⓈ-M Futures market data; no API key is required."""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{BINANCE_FAPI_BASE}{path}?{query}",
        headers={"User-Agent": "GoldTraderPro/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _to_candles(rows: list, now_ms: int, limit: int) -> list[CandleData]:
    """Convert only closed candles; never analyze a still-forming candle."""
    closed = [row for row in rows if int(row[6]) < now_ms]
    result = []
    for row in closed[-limit:]:
        result.append(CandleData(
            time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).isoformat(),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        ))
    return result


async def _binance_gold_feed_loop() -> None:
    """Refresh app state from Binance gold perpetual data and analyze once per new minute."""
    last_analyzed_open = None
    logger.info("Binance gold feed starting for XAUUSDT (USDⓈ-M perpetual; not broker XAUUSD)")
    while True:
        try:
            book, m1_rows, m5_rows, m15_rows = await asyncio.gather(
                asyncio.to_thread(_fetch_binance_json, "/fapi/v1/ticker/bookTicker", {"symbol": BINANCE_GOLD_SYMBOL}),
                asyncio.to_thread(_fetch_binance_json, "/fapi/v1/klines", {"symbol": BINANCE_GOLD_SYMBOL, "interval": "1m", "limit": 120}),
                asyncio.to_thread(_fetch_binance_json, "/fapi/v1/klines", {"symbol": BINANCE_GOLD_SYMBOL, "interval": "5m", "limit": 80}),
                asyncio.to_thread(_fetch_binance_json, "/fapi/v1/klines", {"symbol": BINANCE_GOLD_SYMBOL, "interval": "15m", "limit": 80}),
            )
            now = datetime.now(timezone.utc)
            now_ms = int(now.timestamp() * 1000)
            bid = float(book["bidPrice"])
            ask = float(book["askPrice"])
            m1 = _to_candles(m1_rows, now_ms, 100)
            m5 = _to_candles(m5_rows, now_ms, 60)
            m15 = _to_candles(m15_rows, now_ms, 60)
            candles = {"M1": m1, "M5": m5, "M15": m15}

            if not m1 or not m5 or not m15 or bid <= 0 or ask < bid:
                raise ValueError("Binance returned incomplete or invalid gold market data")

            latest_closed_ms = int(datetime.fromisoformat(m1[-1].time).timestamp() * 1000)
            if now_ms - latest_closed_ms > 180_000:
                raise ValueError("Binance gold candles are stale; refusing to publish a signal")

            # Publish fresh market data immediately, before optional AI analysis.
            _latest_mobile_state.clear()
            _latest_mobile_state.update({
                "price": f"{bid:.2f}",
                "symbol": "XAUUSD",
                "signal": None,
                "protection": {"mode": "OFF"},
                "source": "Binance USDⓈ-M Futures",
                "source_symbol": BINANCE_GOLD_SYMBOL,
                "updated_at_utc": now.isoformat(),
                "data_status": "LIVE",
                "note": "Gold perpetual quote; may differ from broker XAUUSD",
            })

            latest_open = m1[-1].time
            if latest_open != last_analyzed_open:
                last_analyzed_open = latest_open
                spread_points = max(0, round((ask - bid) / BINANCE_POINT))
                req = SignalRequest(
                    symbol="XAUUSD",
                    timeframe="M1",
                    server_time_utc=now.isoformat(),
                    bid=bid,
                    ask=ask,
                    spread_points=spread_points,
                    digits=2,
                    point=BINANCE_POINT,
                    candles=candles,
                    atr=compute_atr(candles),
                    constraints=Constraints(),
                )
                logger.info(
                    "Binance gold data refreshed: bid=%.2f ask=%.2f candles M1=%d M5=%d M15=%d",
                    bid, ask, len(m1), len(m5), len(m15),
                )
                await generate_signal(req)

        except Exception as exc:
            logger.warning("Binance gold feed unavailable: %s", exc)
            _latest_mobile_state.clear()
            _latest_mobile_state.update({
                "price": "",
                "symbol": "XAUUSD",
                "signal": None,
                "protection": {"mode": "OFF"},
                "source": "Binance USDⓈ-M Futures",
                "source_symbol": BINANCE_GOLD_SYMBOL,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "data_status": "NO_DATA",
                "note": "Market data unavailable or stale; no signal",
            })
        await asyncio.sleep(15)


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
    if atr_value <= 0:
        logger.warning("   🚫 VETO: ATR unavailable")
        return _publish_veto(req, "atr_unavailable")

    # 3. Quick spread veto (server-side too, belt-and-suspenders)
    if req.spread_points > req.constraints.max_spread_points:
        logger.warning(f"   🚫 VETO: Spread {req.spread_points} > max {req.constraints.max_spread_points}")
        logger.info("─" * 60)
        return _publish_veto(req, f"spread {req.spread_points} > max {req.constraints.max_spread_points}")

    # 4. Call OpenAI with Structured Outputs (with fallback)
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not configured; returning safe WAIT state")
        return _publish_veto(req, "model_unavailable: OPENAI_API_KEY not configured")
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0)
    models_to_try = [OPENAI_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != OPENAI_MODEL:
        models_to_try.append(FALLBACK_MODEL)

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
                logger.info(f"   ⏳ Calling OpenAI ({model})...")
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

            # --- FIX Issue 3: Override timestamp with actual server time ---
            signal.timestamp_utc = datetime.now(timezone.utc).isoformat()

            # Hard server-side validation: AI output can never become an executable action.
            # Invalid geometry is converted to WAIT instead of being passed through.
            if signal.order.type.value == "buy_stop":
                valid = signal.order.entry > req.ask and signal.order.sl < signal.order.entry and signal.order.tp > signal.order.entry
            elif signal.order.type.value == "sell_stop":
                valid = signal.order.entry < req.bid and signal.order.sl > signal.order.entry and signal.order.tp < signal.order.entry
            else:
                valid = True
            if signal.veto:
                signal.order.type = OrderTypeEnum.none
                signal.order.entry = 0.0
                signal.order.sl = 0.0
                signal.order.tp = 0.0
                signal.order.expiry_minutes = 0
            elif not valid:
                logger.warning("   🚫 VETO: invalid signal geometry returned by model")
                return _publish_veto(req, "invalid_signal_geometry")

            # --- Log R:R for info (no auto-correction, use AI's original TP) ---
            if not signal.veto and signal.order.type.value != "none":
                entry = signal.order.entry
                sl = signal.order.sl
                tp = signal.order.tp
                sl_dist = abs(entry - sl)
                tp_dist = abs(tp - entry)
                rr = tp_dist / sl_dist if sl_dist > 0 else 0
                logger.info(f"   📐 R:R ratio: {rr:.2f} (using AI's original TP)")

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
            logger.error(f"   ❌ {model} failed: {e}")
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
