"""Read-only Windows MetaTrader 5 feeder for GoldTrader Pro Cloud."""
from __future__ import annotations
import os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5
import requests

ROOT = Path(__file__).resolve().parent

def read_env(path: Path):
    if not path.exists(): return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def utc_stamp(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat().replace("+00:00", "Z")

def main():
    read_env(ROOT / ".env")
    endpoint = os.getenv("GOLDTRADER_API_URL", "").strip().rstrip("/")
    token = os.getenv("GOLDTRADER_INGEST_TOKEN", "").strip()
    symbol = os.getenv("MT5_SYMBOL", "XAUUSD").strip()
    if not endpoint.startswith("https://"):
        print("CONFIG ERROR: GOLDTRADER_API_URL must be an HTTPS URL."); return 2
    if len(token) < 32 or token.lower().startswith("replace_"):
        print("CONFIG ERROR: set GOLDTRADER_INGEST_TOKEN in bridge/.env."); return 2
    interval = max(2.5, float(os.getenv("POLL_INTERVAL_SECONDS", "3")))
    candle_interval = max(30, float(os.getenv("CANDLE_INTERVAL_SECONDS", "60")))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "GoldTraderPro-MT5-Bridge/0.1"}
    frames = {"M5": (mt5.TIMEFRAME_M5, 200), "M15": (mt5.TIMEFRAME_M15, 300),
              "H1": (mt5.TIMEFRAME_H1, 100), "H4": (mt5.TIMEFRAME_H4, 260), "D1": (mt5.TIMEFRAME_D1, 100)}
    print("GoldTrader Pro | MT5 -> Cloud API | read-only")
    print(f"API: {endpoint}; symbol: {symbol}; quote interval: {interval:g}s")
    print("Keep this console and MT5 running while using this price source.")
    session, next_candles, reconnect_at = requests.Session(), 0.0, 0.0
    try:
        while True:
            now = time.monotonic()
            terminal, info = mt5.terminal_info(), mt5.symbol_info(symbol)
            if terminal is None or info is None:
                if now >= reconnect_at:
                    reconnect_at = now + 10
                    mt5.shutdown()
                    if not mt5.initialize():
                        print(f"NO DATA: MT5 initialization failed: {mt5.last_error()}")
                        time.sleep(interval); continue
                    info = mt5.symbol_info(symbol)
                    if info is None:
                        print(f"NO DATA: broker does not have symbol {symbol}; set exact MT5_SYMBOL.")
                        time.sleep(interval); continue
                    if not info.visible and not mt5.symbol_select(symbol, True):
                        print(f"NO DATA: cannot select {symbol}: {mt5.last_error()}")
                        time.sleep(interval); continue
            tick = mt5.symbol_info_tick(symbol)
            if tick is None or float(tick.bid) <= 0 or float(tick.ask) < float(tick.bid):
                print("NO DATA: broker tick missing or invalid."); time.sleep(interval); continue
            try:
                response = session.post(endpoint + "/v1/market/tick",
                    json={"symbol": symbol, "bid": float(tick.bid), "ask": float(tick.ask),
                          "time": utc_stamp(tick.time), "source": "MT5"}, headers=headers, timeout=8)
                if response.status_code >= 400:
                    print(f"QUOTE REJECTED: HTTP {response.status_code}; {response.text[:180]}")
            except requests.RequestException as exc:
                print(f"NETWORK ERROR: {type(exc).__name__}; retrying.")
            if time.monotonic() >= next_candles:
                next_candles = time.monotonic() + candle_interval
                batch = {}
                for tf, (mt5_tf, count) in frames.items():
                    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 1, count)  # position 1 excludes live candle
                    if rates is None or len(rates) == 0:
                        print(f"CANDLE WARNING: no closed candles for {tf}: {mt5.last_error()}"); continue
                    batch[tf] = sorted([{
                        "time": utc_stamp(row["time"]), "open": float(row["open"]), "high": float(row["high"]),
                        "low": float(row["low"]), "close": float(row["close"]), "tick_volume": float(row["tick_volume"]),
                        "real_volume": float(row["real_volume"]), "spread": float(row["spread"])
                    } for row in rates], key=lambda item: item["time"])
                if batch:
                    try:
                        response = session.post(endpoint + "/v1/market/candles",
                            json={"symbol": symbol, "source": "MT5", "timeframes": batch},
                            headers=headers, timeout=20)
                        if response.status_code >= 400:
                            print(f"CANDLES REJECTED: HTTP {response.status_code}; {response.text[:240]}")
                        else:
                            details = response.json().get("timeframes", {})
                            print("Closed candles accepted: " + ", ".join(f"{k}:{v.get('count', 0)}" for k,v in details.items()))
                    except requests.RequestException as exc:
                        print(f"CANDLE UPLOAD ERROR: {type(exc).__name__}; will retry.")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Bridge stopped by user.")
    finally:
        session.close(); mt5.shutdown()
    return 0

if __name__ == "__main__":
    sys.exit(main())
