"""تشخیص مفاهیم ساختار بازار: BOS/CHoCH proxy، sweep، FVG و order blocks."""
def analyze_smc(df,lookback=15):
    empty={"bos":"NONE","choch":"NONE","sweep":"NONE","fvg":[],"order_blocks":[],"range_high":None,"range_low":None}
    if df is None or len(df)<5:return empty
    high=df["high"].astype(float).to_numpy();low=df["low"].astype(float).to_numpy();close=df["close"].astype(float).to_numpy();op=df["open"].astype(float).to_numpy()
    n=len(df);prev_hi=max(high[max(0,n-lookback-1):n-1]);prev_lo=min(low[max(0,n-lookback-1):n-1]);sweep="NONE"
    if high[-1]>prev_hi and close[-1]<prev_hi:sweep="BEARISH"
    elif low[-1]<prev_lo and close[-1]>prev_lo:sweep="BULLISH"
    bos="NONE"
    if close[-1]>prev_hi:bos="BULLISH"
    elif close[-1]<prev_lo:bos="BEARISH"
    prior_mean=float(close[max(0,n-20):n-1].mean());prior_bias="BULLISH" if close[-2]>prior_mean else "BEARISH"
    choch="BULLISH" if bos=="BULLISH" and prior_bias=="BEARISH" else "BEARISH" if bos=="BEARISH" and prior_bias=="BULLISH" else "NONE"
    fvg=[]
    for i in range(max(2,n-30),n):
        if low[i]>high[i-2]:fvg.append({"side":"BULLISH","low":float(high[i-2]),"high":float(low[i])})
        if high[i]<low[i-2]:fvg.append({"side":"BEARISH","low":float(high[i]),"high":float(low[i-2])})
    bodies=abs(close-op);avg=float(bodies[max(0,n-25):n-1].mean()) if n>2 else 0;obs=[]
    if avg>0:
        for i in range(max(2,n-20),n):
            body=abs(close[i]-op[i])
            if body<1.8*avg:continue
            side="BULLISH" if close[i]>op[i] else "BEARISH"
            for j in range(i-1,max(0,i-6),-1):
                opposite=(close[j]<op[j]) if side=="BULLISH" else (close[j]>op[j])
                if opposite:
                    zone={"side":side,"low":float(low[j]),"high":float(high[j]),"strength":round(body/avg,2)}
                    if (side=="BULLISH" and close[-1]>=zone["low"]) or (side=="BEARISH" and close[-1]<=zone["high"]):obs.append(zone)
                    break
    mid=(max(high[-50:])+min(low[-50:]))/2
    return {"bos":bos,"choch":"NONE","sweep":sweep,"fvg":fvg[-5:],"order_blocks":obs[-3:],"range_high":float(max(high[-50:])),"range_low":float(min(low[-50:])),"premium_discount":"PREMIUM" if close[-1]>mid else "DISCOUNT"}
