"""تشخیص ساده و قابل توضیح مفاهیم ساختار بازار."""
def analyze_smc(df, lookback=15):
    if df is None or len(df)<5:return {"bos":"NONE","choch":"NONE","sweep":"NONE","fvg":[],"range_high":None,"range_low":None}
    high=df["high"].astype(float).to_numpy(); low=df["low"].astype(float).to_numpy(); close=df["close"].astype(float).to_numpy()
    n=len(df); prev_hi=max(high[max(0,n-lookback-1):n-1]); prev_lo=min(low[max(0,n-lookback-1):n-1])
    sweep="NONE"
    if high[-1]>prev_hi and close[-1]<prev_hi:sweep="BEARISH"
    elif low[-1]<prev_lo and close[-1]>prev_lo:sweep="BULLISH"
    bos="NONE"
    if close[-1]>prev_hi:bos="BULLISH"
    elif close[-1]<prev_lo:bos="BEARISH"
    # Three-candle imbalance; only return gaps still unfilled by current close.
    fvg=[]
    for i in range(max(2,n-30),n):
        if low[i]>high[i-2]: fvg.append({"side":"BULLISH","low":float(high[i-2]),"high":float(low[i])})
        if high[i]<low[i-2]: fvg.append({"side":"BEARISH","low":float(high[i]),"high":float(low[i-2])})
    mid=(max(high[-50:])+min(low[-50:]))/2
    return {"bos":bos,"choch":bos,"sweep":sweep,"fvg":fvg[-5:],"range_high":float(max(high[-50:])),"range_low":float(min(low[-50:])),"premium_discount":"PREMIUM" if close[-1]>mid else "DISCOUNT"}
