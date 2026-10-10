"""اندیکاتورهای تکنیکال با NumPy؛ بدون وابستگی به TA-Lib."""
from __future__ import annotations
import numpy as np

def _arr(values):
    return np.asarray(values, dtype=float)

def sma(values, period):
    x = _arr(values); out = np.full(x.shape, np.nan)
    if period < 1: raise ValueError("period must be positive")
    if len(x) >= period:
        sums = np.convolve(np.nan_to_num(x, nan=0.0), np.ones(period), "valid")
        counts = np.convolve(np.isfinite(x).astype(float), np.ones(period), "valid")
        out[period-1:] = np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts == period)
    return out

def ema(values, period):
    x = _arr(values); out = np.full(x.shape, np.nan)
    if period < 1: raise ValueError("period must be positive")
    valid = np.flatnonzero(np.isfinite(x))
    if len(valid) < period: return out
    start = valid[0]
    seed_idx = start + period - 1
    if seed_idx >= len(x) or not np.all(np.isfinite(x[start:seed_idx+1])): 
        # Seed at first contiguous valid segment of sufficient length.
        for i in range(len(x)-period+1):
            if np.all(np.isfinite(x[i:i+period])):
                start=i; seed_idx=i+period-1; break
        else: return out
    out[seed_idx] = np.mean(x[start:seed_idx+1]); alpha=2.0/(period+1)
    for i in range(seed_idx+1,len(x)):
        if np.isfinite(x[i]) and np.isfinite(out[i-1]): out[i]=alpha*x[i]+(1-alpha)*out[i-1]
    return out

def dema(values, period):
    e1=ema(values,period); e2=ema(e1,period); return 2*e1-e2

def rsi(close, period=14):
    x=_arr(close); out=np.full(x.shape,np.nan)
    if len(x)<=period: return out
    d=np.diff(x); gain=np.maximum(d,0); loss=np.maximum(-d,0)
    ag=np.full(len(x),np.nan); al=np.full(len(x),np.nan)
    ag[period]=np.mean(gain[:period]); al[period]=np.mean(loss[:period])
    for i in range(period+1,len(x)):
        ag[i]=(ag[i-1]*(period-1)+gain[i-1])/period
        al[i]=(al[i-1]*(period-1)+loss[i-1])/period
    rs=np.divide(ag,al,out=np.full_like(ag,np.inf),where=al!=0)
    out=100-100/(1+rs); out[(al==0)&(ag==0)]=50; out[(al==0)&(ag>0)]=100
    return out

def macd(close, fast=12, slow=26, signal=9):
    line=ema(close,fast)-ema(close,slow); sig=ema(line,signal)
    return line,sig,line-sig

def atr(high,low,close,period=14):
    h,l,c=map(_arr,(high,low,close))
    if len(c)==0:return np.array([])
    prev=np.r_[np.nan,c[:-1]]
    tr=np.nanmax(np.vstack((h-l,np.abs(h-prev),np.abs(l-prev))),axis=0)
    return ema(tr,period)

def bollinger(close,period=20,mult=2.0):
    x=_arr(close); mid=sma(x,period); variance=sma((x-mid)**2,period)
    sd=np.sqrt(variance)
    return mid+mult*sd,mid,mid-mult*sd

def stochastic(high,low,close,k_period=14,d_period=3,smooth=3):
    h,l,c=map(_arr,(high,low,close)); k=np.full(c.shape,np.nan)
    for i in range(k_period-1,len(c)):
        hh=np.nanmax(h[i-k_period+1:i+1]); ll=np.nanmin(l[i-k_period+1:i+1])
        k[i]=50 if hh==ll else 100*(c[i]-ll)/(hh-ll)
    sk=sma(k,smooth); d=sma(sk,d_period); return sk,d

def adx(high,low,close,period=14):
    h,l,c=map(_arr,(high,low,close)); n=len(c)
    if n==0:return np.array([]),np.array([]),np.array([])
    up=np.r_[np.nan,np.diff(h)]; down=np.r_[np.nan,-np.diff(l)]
    plus=np.where((up>down)&(up>0),up,0.0); minus=np.where((down>up)&(down>0),down,0.0)
    a=atr(h,l,c,period); pdi=100*np.divide(ema(plus,period),a,out=np.full(n,np.nan),where=a!=0)
    mdi=100*np.divide(ema(minus,period),a,out=np.full(n,np.nan),where=a!=0)
    dx=100*np.divide(np.abs(pdi-mdi),pdi+mdi,out=np.full(n,np.nan),where=(pdi+mdi)!=0)
    return ema(dx,period),pdi,mdi

def last_valid(values, default=None):
    x=_arr(values); idx=np.flatnonzero(np.isfinite(x))
    return float(x[idx[-1]]) if len(idx) else default

def cross_above(a,b):
    a,b=_arr(a),_arr(b)
    return bool(len(a)>1 and np.isfinite(a[-2]) and np.isfinite(b[-2]) and np.isfinite(a[-1]) and np.isfinite(b[-1]) and a[-2]<=b[-2] and a[-1]>b[-1])

def cross_below(a,b):
    a,b=_arr(a),_arr(b)
    return bool(len(a)>1 and np.isfinite(a[-2]) and np.isfinite(b[-2]) and np.isfinite(a[-1]) and np.isfinite(b[-1]) and a[-2]>=b[-2] and a[-1]<b[-1])
