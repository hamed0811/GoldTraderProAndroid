from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app

INGEST = "a" * 64
READ = "b" * 64

def configure(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLDTRADER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDTRADER_INGEST_TOKEN", INGEST)
    monkeypatch.setenv("GOLDTRADER_READ_TOKEN", READ)

def auth(token=INGEST):
    return {"Authorization": f"Bearer {token}"}

def tick(stamp=None):
    stamp = stamp or datetime.now(timezone.utc)
    return {"symbol": "XAUUSD", "bid": 2350.1, "ask": 2350.3,
            "time": stamp.isoformat().replace("+00:00", "Z"), "source": "MT5"}

def test_health_is_liveness_only(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

def test_ingest_requires_bearer(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.post("/v1/market/tick", json=tick())
    assert r.status_code == 401

def test_fresh_quote_and_read_auth(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.post("/v1/market/tick", json=tick(), headers=auth()).status_code == 200
        assert c.get("/v1/market/latest").status_code == 401
        r = c.get("/v1/market/latest", headers=auth(READ))
    assert r.status_code == 200 and r.json()["status"] == "OK"
    assert r.json()["quote"]["bid"] == 2350.1

def test_stale_quote_is_rejected(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    old = datetime.now(timezone.utc) - timedelta(minutes=2)
    with TestClient(app) as c:
        r = c.post("/v1/market/tick", json=tick(old), headers=auth())
    assert r.status_code == 422 and "stale" in r.json()["detail"]

def test_missing_candles_is_no_data_not_fake_signal(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with TestClient(app) as c:
        c.post("/v1/market/tick", json=tick(), headers=auth())
        r = c.get("/v1/signal/latest", headers=auth(READ))
    assert r.status_code == 200 and r.json()["status"] == "NO_DATA"
    assert r.json()["signal"]["action"] == "WAIT"
    assert "entry" not in r.json()["signal"]

def test_invalid_ohlc_is_rejected(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    row = {"time": (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat(),
           "open": 10, "high": 8, "low": 9, "close": 10, "tick_volume": 100}
    with TestClient(app) as c:
        r = c.post("/v1/market/candles", json={"symbol": "XAUUSD", "timeframes": {"M5": [row]}}, headers=auth())
    assert r.status_code == 422

def test_unknown_timeframe_is_rejected(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    row = {"time": (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat(),
           "open": 10, "high": 11, "low": 9, "close": 10.5}
    with TestClient(app) as c:
        r = c.post("/v1/market/candles", json={"symbol": "XAUUSD", "timeframes": {"M2": [row]}}, headers=auth())
    assert r.status_code == 422
