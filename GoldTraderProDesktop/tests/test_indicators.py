import numpy as np
from core.indicators import sma,ema,rsi,macd,atr,bollinger,stochastic,adx,cross_above,cross_below,last_valid
def sample():
    c=np.linspace(2000,2020,300)+np.sin(np.arange(300)/5);return c,c+1,c-1
def test_ema_and_sma():
    c,_,_=sample();assert np.isfinite(ema(c,20)[-1]);assert abs(sma(c,20)[-1]-np.mean(c[-20:]))<1e-8
def test_rsi_bounds():
    c,_,_=sample();v=rsi(c);assert 0<=v[-1]<=100
def test_macd_shapes():
    c,_,_=sample();m,s,h=macd(c);assert len(m)==len(c)==len(s)==len(h)
def test_atr_and_bollinger():
    c,hi,lo=sample();assert atr(hi,lo,c)[-1]>0;up,mid,dn=bollinger(c);assert up[-1]>=mid[-1]>=dn[-1]
def test_stochastic_adx():
    c,hi,lo=sample();k,d=stochastic(hi,lo,c);a,p,m=adx(hi,lo,c);assert len(k)==len(c) and len(a)==len(c)
def test_cross_helpers():
    assert cross_above([1,2],[2,1]);assert cross_below([2,1],[1,2]);assert last_valid([np.nan,2])==2
