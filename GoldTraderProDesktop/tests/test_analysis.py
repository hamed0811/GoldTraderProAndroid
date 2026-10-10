import numpy as np
import pandas as pd
from core.confluence_engine import analyze
from core.signal_engine import build_signal
from core.level_finder import find_levels
from core.smc import analyze_smc
def frame(n=320,trend=1.0):
    close=2000+np.arange(n)*trend*0.08+np.sin(np.arange(n)/4)
    return pd.DataFrame({"open":close-0.1,"high":close+0.8,"low":close-0.8,"close":close,"tick_volume":100+np.arange(n)%13,"time":pd.date_range("2026-01-01",periods=n,freq="min")})
def test_insufficient_market_data_is_wait():
    result=analyze(frame(20))
    assert result["action"]=="WAIT" and result["ready"] is False
def test_confluence_returns_explainable_decision():
    df=frame()
    result=analyze(df,df,df,df,df)
    assert result["action"] in ("BUY","SELL","WAIT")
    assert "layers" in result and "reasons" in result
def test_missing_tick_never_makes_up_prices():
    result=build_signal({"ready":True,"action":"BUY","score":99},None,{})
    assert result["action"]=="WAIT" and "NO DATA" in result["reason"]
def test_pending_levels_bounded_and_has_risk_levels():
    analysis={"ready":True,"action":"WAIT","score":0,"buy_score":60,"sell_score":50,"levels":{"support":[{"price":1988,"sources":["swing low","EMA50"]}],"resistance":[{"price":2012,"sources":["swing high","round number"]}]}}
    signal=build_signal(analysis,{"bid":2000,"ask":2000.2},{"signal":{"pending_min_confidence":75}})
    assert len(signal["pending"])<=2
    for item in signal["pending"]:
        assert item["action"] in ("BUY","SELL")
        assert item["sl"]!=item["level_price"] and item["tp1"]!=item["level_price"]
def test_level_finder_returns_supported_shape():
    result=find_levels(frame(),price=2025)
    assert set(result)=={"support","resistance"}
def test_smc_shape():
    result=analyze_smc(frame())
    assert "bos" in result and "sweep" in result and "fvg" in result
