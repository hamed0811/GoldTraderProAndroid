from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main


TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}


def build_series(tf: str, count: int, now: datetime, direction: int = 1):
    step = TF_SECONDS[tf]
    last_age = step + 10
    result = []
    for i in range(count):
        close = 2400.0 + direction * i * 0.2
        result.append(main.CandleData(
            time=(now - timedelta(seconds=last_age + step * (count - 1 - i))).isoformat(),
            open=close - direction * 0.05,
            high=close + 0.2,
            low=close - 0.2,
            close=close,
            volume=100.0,
        ))
    return result


def valid_mtf(now=None, direction=1):
    now = now or datetime.now(timezone.utc)
    return {
        tf: build_series(tf, count, now, direction)
        for tf, count in main.REQUIRED_TIMEFRAMES.items()
    }


def test_accepts_fresh_complete_multi_timeframe_data():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now)
    main._validate_feed_candles(candles, now)


def test_rejects_missing_daily_timeframe():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now)
    del candles["D1"]
    with pytest.raises(ValueError, match="D1"):
        main._validate_feed_candles(candles, now)


def test_rejects_invalid_ohlc_geometry():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now)
    candles["M1"][-1].high = candles["M1"][-1].close - 1
    with pytest.raises(ValueError, match="invalid OHLC geometry"):
        main._validate_feed_candles(candles, now)


def test_rejects_stale_minute_data():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now)
    for candle in candles["M1"]:
        candle.time = (datetime.fromisoformat(candle.time) - timedelta(minutes=10)).isoformat()
    with pytest.raises(ValueError, match="M1 last closed candle is stale"):
        main._validate_feed_candles(candles, now)


def test_multi_timeframe_alignment_is_deterministic():
    now = datetime.now(timezone.utc)
    bullish = valid_mtf(now, direction=1)
    direction, bulls, bears, _ = main._timeframe_alignment(bullish)
    assert direction == "bullish"
    assert bulls == 5 and bears == 0

    bearish = valid_mtf(now, direction=-1)
    direction, bulls, bears, _ = main._timeframe_alignment(bearish)
    assert direction == "bearish"
    assert bears == 5 and bulls == 0


def make_request(candles, now):
    return main.SignalRequest(
        symbol="XAUUSD",
        timeframe="M5",
        server_time_utc=now.isoformat(),
        bid=2406.35,
        ask=2406.40,
        spread_points=5,
        digits=2,
        point=0.01,
        candles=candles,
        atr=main.compute_atr(candles),
        constraints=main.Constraints(max_spread_points=50, min_rr=1.5, expiry_minutes=10),
    )


def test_engine_only_emits_only_a_valid_aligned_breakout():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now, direction=1)
    prior_high = max(c.high for c in candles["M1"][-6:-1])
    last = candles["M1"][-1]
    last.close = prior_high + 0.5
    last.open = last.close - 0.1
    last.high = last.close + 0.1
    last.low = last.close - 0.2

    req = make_request(candles, now)
    signal = main._engine_only_signal(req, main.compute_atr(candles))
    assert signal is not None
    assert signal.order.type == main.OrderTypeEnum.buy_stop
    assert signal.order.entry > req.ask
    assert signal.order.sl < signal.order.entry < signal.order.tp
    assert abs(signal.order.tp - signal.order.entry) / abs(signal.order.entry - signal.order.sl) >= 1.5
    assert signal.confidence >= 0.8
    assert "ENGINE_ONLY" in signal.order.comment


def test_engine_only_returns_wait_without_a_breakout():
    now = datetime.now(timezone.utc)
    candles = valid_mtf(now, direction=1)
    req = make_request(candles, now)
    assert main._engine_only_signal(req, main.compute_atr(candles)) is None
