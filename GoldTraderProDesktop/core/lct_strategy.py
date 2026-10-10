"""LCT ساده: محدوده M15 و sweep با برگشت به داخل محدوده."""
from .indicators import atr,last_valid
def analyze_lct(df):
    if df is None or len(df)<30:return {"score":0,"bias":"NEUTRAL","reason":"داده ناکافی برای LCT"}
    h=df.high.astype(float).to_numpy();l=df.low.astype(float).to_numpy();c=df.close.astype(float).to_numpy()
    av=last_valid(atr(h,l,c,14))
    if av is None or av<=0:return {"score":0,"bias":"NEUTRAL","reason":"ATR در دسترس نیست"}
    hi=float(max(h[-20:-1]));lo=float(min(l[-20:-1]));width=hi-lo
    if not 1.5*av<=width<=8*av:return {"score":0,"bias":"NEUTRAL","reason":"محدوده معتبر LCT شناسایی نشد"}
    if l[-1]<lo and c[-1]>lo:return {"score":10,"bias":"BULLISH","reason":"Sweep زیر کف محدوده و برگشت"}
    if h[-1]>hi and c[-1]<hi:return {"score":10,"bias":"BEARISH","reason":"Sweep بالای سقف محدوده و برگشت"}
    return {"score":0,"bias":"NEUTRAL","reason":"Sweep معتبر دیده نشد"}
