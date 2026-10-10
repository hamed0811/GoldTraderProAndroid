"""Authenticated Oracle-hosted API for GoldTrader Pro. Never invents market data."""
from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from core.analyzer import analyze_market
from core.indicators import ema, last_valid
from core.signal_engine import build_signal

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger("goldtrader.cloud")
TF_SEC = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
MIN_BARS = {"M5": 60, "M15": 30, "H1": 30, "H4": 202, "D1": 52}
MAX_BAR_AGE = {"M5": 900, "M15": 2700, "H1": 10800, "H4": 36000, "D1": 172800}
SETTINGS = {
    "signal": {"min_confidence": 80, "pending_min_confidence": 75, "require_15m_alignment": True},
    "levels": {"stop_loss_dollars": 5.0, "take_profit_1_dollars": 5.0, "take_profit_2_dollars": 10.0},
}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def stamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def parse_stamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def db_file() -> Path:
    return Path(os.getenv("GOLDTRADER_DATA_DIR", "./data")) / "goldtrader.sqlite3"

def init_db() -> None:
    path = db_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""CREATE TABLE IF NOT EXISTS quotes(
            symbol TEXT PRIMARY KEY, bid REAL NOT NULL, ask REAL NOT NULL,
            spread REAL NOT NULL, quoted_at TEXT NOT NULL, received_at TEXT NOT NULL,
            source TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS candles(
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, candles_json TEXT NOT NULL,
            last_candle_at TEXT NOT NULL, received_at TEXT NOT NULL, source TEXT NOT NULL,
            PRIMARY KEY(symbol,timeframe))""")
        conn.commit()

@contextmanager
def db():
    conn = sqlite3.connect(db_file(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(title="GoldTrader Pro Cloud API", version="0.1.0",
              description="Authenticated market-data ingest and signal analysis; no trade execution.",
              docs_url=None, redoc_url=None, lifespan=lifespan)

class TickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9._-]+$")
    bid: float = Field(gt=0, le=10_000_000)
    ask: float = Field(gt=0, le=10_000_000)
    time: datetime
    source: str = Field(default="MT5", min_length=2, max_length=32)

    @field_validator("time")
    @classmethod
    def tz_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("time must include an ISO-8601 timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def ask_not_below_bid(self):
        if self.ask < self.bid:
            raise ValueError("ask cannot be below bid")
        return self

class CandleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: datetime
    open: float = Field(gt=0, le=10_000_000)
    high: float = Field(gt=0, le=10_000_000)
    low: float = Field(gt=0, le=10_000_000)
    close: float = Field(gt=0, le=10_000_000)
    tick_volume: float = Field(default=0, ge=0)
    real_volume: float = Field(default=0, ge=0)
    spread: float = Field(default=0, ge=0)

    @field_validator("time")
    @classmethod
    def tz_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("time must include an ISO-8601 timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("invalid OHLC geometry")
        return self

class CandleBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9._-]+$")
    source: str = Field(default="MT5", min_length=2, max_length=32)
    timeframes: dict[str, list[CandleIn]]

    @field_validator("timeframes")
    @classmethod
    def timeframe_keys(cls, value):
        if not value or set(value) - set(TF_SEC):
            raise ValueError("provide one or more supported timeframes: M5, M15, H1, H4, D1")
        if any(not rows or len(rows) > 1000 for rows in value.values()):
            raise ValueError("each timeframe must contain 1–1000 candles")
        return value

def authorize(authorization: str | None, key_name: str) -> None:
    expected = os.getenv(key_name, "").strip()
    if len(expected) < 32 or expected.lower().startswith("replace_"):
        raise HTTPException(503, detail=f"{key_name} is not configured")
    supplied = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, detail="Invalid bearer token")

def ingest_auth(authorization: str | None = Header(default=None)):
    authorize(authorization, "GOLDTRADER_INGEST_TOKEN")

def read_auth(authorization: str | None = Header(default=None)):
    authorize(authorization, "GOLDTRADER_READ_TOKEN")

def quote_for(symbol: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM quotes WHERE symbol=?", (symbol,)).fetchone()
    return dict(row) if row else None

def candles_for(symbol: str):
    with db() as conn:
        rows = conn.execute("SELECT * FROM candles WHERE symbol=?", (symbol,)).fetchall()
    result = {}
    for row in rows:
        item = dict(row)
        item["candles"] = json.loads(item.pop("candles_json"))
        result[item["timeframe"]] = item
    return result

def quote_fresh(quote: dict[str, Any] | None):
    if not quote:
        return False, "no_quote_received", None
    try:
        age = int((now_utc() - parse_stamp(quote["quoted_at"])).total_seconds())
        received_age = int((now_utc() - parse_stamp(quote["received_at"])).total_seconds())
    except (KeyError, TypeError, ValueError):
        return False, "invalid_quote_timestamp", None
    max_age = int(os.getenv("GOLDTRADER_MAX_QUOTE_AGE_SECONDS", "15"))
    if age < -5:
        return False, "quote_timestamp_in_future", age
    if age > max_age or received_age > max_age:
        return False, "quote_stale", age
    return True, None, max(0, age)

def no_data(reason: str, checks: dict[str, Any] | None = None):
    body = {"status": "NO_DATA", "reason": reason,
            "signal": {"action": "WAIT", "score": 0,
                       "reason": "داده واقعی و تازه کافی نیست؛ هیچ سیگنالی صادر نشد."}}
    if checks is not None:
        body["checks"] = checks
    return body

def mtf_alignment(frames: dict[str, pd.DataFrame], action: str):
    if action not in ("BUY", "SELL"):
        return {"passed": False, "reason": "engine_wait", "directions": {}}
    directions = {}
    for tf, fast, slow in (("M15", 9, 21), ("H4", 200, None), ("D1", 50, None)):
        close = frames[tf]["close"].astype(float).to_numpy()
        if len(close) < max(fast, slow or 0) + 2:
            directions[tf] = "NO DATA"
            continue
        a, last = last_valid(ema(close, fast)), float(close[-1])
        if slow:
            b = last_valid(ema(close, slow))
            direction = "BULLISH" if a is not None and b is not None and a > b else "BEARISH" if a is not None and b is not None and a < b else "NEUTRAL"
        else:
            direction = "BULLISH" if a is not None and last > a else "BEARISH" if a is not None and last < a else "NEUTRAL"
        directions[tf] = direction
    wanted = "BULLISH" if action == "BUY" else "BEARISH"
    passed = all(directions.get(tf) == wanted for tf in ("M15", "H4", "D1"))
    return {"passed": passed, "reason": "aligned" if passed else "multi_timeframe_not_aligned", "directions": directions}

@app.get("/health")
def health():
    # Liveness only; does not claim a market data feed is connected.
    return {"status": "ok", "service": "goldtrader-pro-cloud-api", "version": app.version}

@app.get("/ready")
def ready():
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        quote = quote_for("XAUUSD")
        ok, reason, age = quote_fresh(quote)
        return {"status": "ok", "database": "ok", "market_data": "OK" if ok else "NO_DATA",
                "quote_age_seconds": age, "market_reason": reason}
    except Exception:
        LOG.exception("Readiness check failed")
        raise HTTPException(503, detail="service not ready")

@app.post("/v1/market/tick", dependencies=[Depends(ingest_auth)])
def ingest_tick(payload: TickIn):
    now = now_utc()
    age = (now - payload.time).total_seconds()
    max_age = int(os.getenv("GOLDTRADER_MAX_QUOTE_AGE_SECONDS", "15"))
    if age < -5:
        raise HTTPException(422, detail="quote timestamp is in the future")
    if age > max_age:
        raise HTTPException(422, detail="quote is stale; server rejected it")
    received = stamp(now)
    with db() as conn:
        conn.execute("""INSERT INTO quotes(symbol,bid,ask,spread,quoted_at,received_at,source)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET
          bid=excluded.bid,ask=excluded.ask,spread=excluded.spread,
          quoted_at=excluded.quoted_at,received_at=excluded.received_at,source=excluded.source""",
          (payload.symbol, payload.bid, payload.ask, round(payload.ask-payload.bid, 8),
           stamp(payload.time), received, payload.source))
    return {"status": "accepted", "symbol": payload.symbol, "quoted_at": stamp(payload.time), "received_at": received}

@app.post("/v1/market/candles", dependencies=[Depends(ingest_auth)])
def ingest_candles(payload: CandleBatchIn):
    now, received = now_utc(), stamp(now)
    accepted = {}
    for tf, rows in payload.timeframes.items():
        times = [row.time for row in rows]
        if any((t-now).total_seconds() > 60 for t in times):
            raise HTTPException(422, detail=f"{tf} contains a future candle")
        if len(set(times)) != len(times) or times != sorted(times):
            raise HTTPException(422, detail=f"{tf} candles must be unique and sorted oldest-first")
        serialized = [row.model_dump(mode="json") for row in rows]
        with db() as conn:
            conn.execute("""INSERT INTO candles(symbol,timeframe,candles_json,last_candle_at,received_at,source)
              VALUES(?,?,?,?,?,?) ON CONFLICT(symbol,timeframe) DO UPDATE SET
              candles_json=excluded.candles_json,last_candle_at=excluded.last_candle_at,
              received_at=excluded.received_at,source=excluded.source""",
              (payload.symbol, tf, json.dumps(serialized, separators=(",", ":")),
               stamp(rows[-1].time), received, payload.source))
        accepted[tf] = {"count": len(rows), "last_candle_at": stamp(rows[-1].time)}
    return {"status": "accepted", "symbol": payload.symbol, "received_at": received, "timeframes": accepted}

@app.get("/v1/market/latest", dependencies=[Depends(read_auth)])
def market_latest(symbol: str = "XAUUSD"):
    quote = quote_for(symbol)
    ok, reason, age = quote_fresh(quote)
    if not ok:
        return {"status": "NO_DATA", "reason": reason, "symbol": symbol, "quote": None}
    return {"status": "OK", "symbol": symbol, "source": quote["source"],
            "quoted_at": quote["quoted_at"], "age_seconds": age,
            "quote": {"bid": quote["bid"], "ask": quote["ask"], "spread": quote["spread"]}}

@app.get("/v1/status", dependencies=[Depends(read_auth)])
def status(symbol: str = "XAUUSD"):
    quote = quote_for(symbol)
    qok, qreason, qage = quote_fresh(quote)
    saved = candles_for(symbol)
    check = {}
    for tf in TF_SEC:
        item = saved.get(tf)
        if not item:
            check[tf] = {"status": "NO DATA", "count": 0}
            continue
        try:
            received_age = int((now_utc()-parse_stamp(item["received_at"])).total_seconds())
            candle_age = int((now_utc()-parse_stamp(item["last_candle_at"])).total_seconds())
            check[tf] = {"status": "OK" if received_age <= 180 else "STALE",
                         "count": len(item["candles"]), "last_candle_at": item["last_candle_at"],
                         "last_candle_open_age_seconds": candle_age, "received_age_seconds": received_age}
        except (ValueError, TypeError, KeyError):
            check[tf] = {"status": "INVALID", "count": len(item.get("candles", []))}
    return {"status": "OK" if qok else "NO_DATA", "symbol": symbol,
            "quote_status": "OK" if qok else "NO DATA", "quote_reason": qreason,
            "quote_age_seconds": qage, "timeframes": check}

@app.get("/v1/signal/latest", dependencies=[Depends(read_auth)])
def latest_signal(symbol: str = "XAUUSD"):
    quote = quote_for(symbol)
    ok, reason, qage = quote_fresh(quote)
    if not ok:
        return no_data(reason or "no_fresh_quote")
    saved, frames, missing = candles_for(symbol), {}, {}
    now = now_utc()
    for tf, minimum in MIN_BARS.items():
        item = saved.get(tf)
        if not item:
            missing[tf] = "not_received"
            continue
        rows = item["candles"]
        if len(rows) < minimum:
            missing[tf] = f"need_at_least_{minimum}_candles"
            continue
        try:
            last_open = parse_stamp(item["last_candle_at"])
            receive_age = (now-parse_stamp(item["received_at"])).total_seconds()
            bar_age = (now-(last_open+timedelta(seconds=TF_SEC[tf]))).total_seconds()
            if receive_age > 180:
                missing[tf] = "candle_snapshot_stale"
                continue
            if bar_age < -60 or bar_age > MAX_BAR_AGE[tf]:
                missing[tf] = "last_closed_candle_stale_or_future"
                continue
            frame = pd.DataFrame(rows)
            frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
            for col in ("open", "high", "low", "close", "tick_volume", "real_volume", "spread"):
                if col not in frame:
                    frame[col] = 0.0
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
            frame = frame.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
            if len(frame) < minimum:
                missing[tf] = "not_enough_valid_candles"
            else:
                frames[tf] = frame
        except (ValueError, TypeError, KeyError):
            missing[tf] = "invalid_candle_payload"
    if missing:
        return no_data("missing_or_stale_timeframes", missing)

    tick = {"bid": quote["bid"], "ask": quote["ask"], "last": (quote["bid"]+quote["ask"])/2,
            "spread": quote["spread"], "time": quote["quoted_at"]}
    try:
        analysis = analyze_market(frames["M5"], frames["M15"], frames["H1"], frames["H4"], frames["D1"], price=quote["bid"])
        signal = build_signal(analysis, tick, SETTINGS)
    except Exception:
        LOG.exception("Signal analysis failed for %s", symbol)
        raise HTTPException(503, detail="signal analysis failed; inspect server logs")

    alignment = {"passed": False, "reason": "engine_wait", "directions": {}}
    if signal.get("action") in ("BUY", "SELL"):
        alignment = mtf_alignment(frames, signal["action"])
        if not alignment["passed"]:
            signal["action"], signal["reason"] = "WAIT", "فیلتر محافظه‌کارانه M15/H4/D1 تأیید نشد."
            signal["reasons"] = list(signal.get("reasons", [])) + ["روند تایم‌فریم‌های لازم همسو نیست."]
            for key in ("entry", "sl", "tp1", "tp2"):
                signal.pop(key, None)
        else:
            entry, stop, target = float(signal.get("entry", 0)), float(signal.get("sl", 0)), float(signal.get("tp2", 0))
            risk = abs(entry-stop)
            rr = abs(target-entry)/risk if risk > 0 else 0
            if rr < 1.5:
                signal["action"], signal["reason"] = "WAIT", "نسبت پاداش به ریسک حداقل 1.5 تأیید نشد."
                for key in ("entry", "sl", "tp1", "tp2"):
                    signal.pop(key, None)
            else:
                signal["risk_reward_tp2"] = round(rr, 2)

    return {"status": "OK", "symbol": symbol, "source": quote["source"],
            "market": {"bid": quote["bid"], "ask": quote["ask"], "spread": quote["spread"],
                       "quoted_at": quote["quoted_at"], "age_seconds": qage},
            "timeframes": {tf: {"count": len(frames[tf]), "last_candle_at": saved[tf]["last_candle_at"]} for tf in TF_SEC},
            "analysis": {"ready": bool(analysis.get("ready")), "buy_score": analysis.get("buy_score", 0),
                         "sell_score": analysis.get("sell_score", 0), "layers": analysis.get("layers", {}),
                         "reasons": analysis.get("reasons", [])},
            "mtf_alignment": alignment, "signal": signal, "issued_at": stamp(now_utc()),
            "execution": "SIGNAL_ONLY_NO_ORDERS"}
