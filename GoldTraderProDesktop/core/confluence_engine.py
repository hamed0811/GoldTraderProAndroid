"""موتور امتیازدهی ۷ لایه؛ نبود داده معتبر به امتیاز جعلی تبدیل نمی‌شود."""
from .indicators import ema,rsi,macd,atr,adx,last_valid
from .smc import analyze_smc

def analyze(df_m5, df_m15=None, df_h1=None):
    if df_m5 is None or len(df_m5)<60:
        return {"action":"WAIT","score":0,"layers":{},"reasons":["برای تحلیل معتبر حداقل ۶۰ کندل M5 لازم است."],"ready":False}
    close=df_m5["close"].astype(float).to_numpy(); high=df_m5["high"].astype(float).to_numpy(); low=df_m5["low"].astype(float).to_numpy()
    e50=last_valid(ema(close,50)); e200=last_valid(ema(close,200)); rv=last_valid(rsi(close,14)); ml,ms,mh=macd(close); mline=last_valid(ml); msig=last_valid(ms); adxv,pdi,mdi=adx(high,low,close)
    adxv=last_valid(adxv); pdi=last_valid(pdi); mdi=last_valid(mdi); smc=analyze_smc(df_m5)
    score_buy=0.0; score_sell=0.0; layers={}; reasons=[]
    # Weights total 100; neutral or missing data earns no directional points.
    trend=20
    if e50 is not None and e200 is not None:
        if close[-1]>e50>e200: score_buy+=trend; layers["روند EMA"]=trend; reasons.append("قیمت بالای EMA50 و EMA200 است.")
        elif close[-1]<e50<e200: score_sell+=trend; layers["روند EMA"]=trend; reasons.append("قیمت زیر EMA50 و EMA200 است.")
        else: layers["روند EMA"]=0
    else: layers["روند EMA"]="داده ناکافی"
    structure=15
    if smc["bos"]=="BULLISH": score_buy+=structure; layers["ساختار بازار"]=structure; reasons.append("شکست ساختار صعودی (BOS) تشخیص داده شد.")
    elif smc["bos"]=="BEARISH": score_sell+=structure; layers["ساختار بازار"]=structure; reasons.append("شکست ساختار نزولی (BOS) تشخیص داده شد.")
    else: layers["ساختار بازار"]=0
    mom=15
    if rv is not None and rv>=52 and mline is not None and msig is not None and mline>msig: score_buy+=mom; layers["مومنتوم"]=mom; reasons.append(f"مومنتوم صعودی؛ RSI={rv:.1f}.")
    elif rv is not None and rv<=48 and mline is not None and msig is not None and mline<msig: score_sell+=mom; layers["مومنتوم"]=mom; reasons.append(f"مومنتوم نزولی؛ RSI={rv:.1f}.")
    else: layers["مومنتوم"]=0
    env=10
    if adxv is not None and adxv>=22 and pdi is not None and mdi is not None:
        if pdi>mdi: score_buy+=env; layers["قدرت روند"]=env; reasons.append(f"قدرت روند مناسب است؛ ADX={adxv:.1f}.")
        elif mdi>pdi: score_sell+=env; layers["قدرت روند"]=env; reasons.append(f"قدرت روند نزولی مناسب است؛ ADX={adxv:.1f}.")
        else: layers["قدرت روند"]=0
    else: layers["قدرت روند"]=0
    smc_score=15
    if smc["sweep"]=="BULLISH": score_buy+=smc_score; layers["نقدینگی/SMC"]=smc_score; reasons.append("جمع‌آوری نقدینگی در سمت کف مشاهده شد.")
    elif smc["sweep"]=="BEARISH": score_sell+=smc_score; layers["نقدینگی/SMC"]=smc_score; reasons.append("جمع‌آوری نقدینگی در سمت سقف مشاهده شد.")
    else: layers["نقدینگی/SMC"]=0
    # Higher timeframe agreement is scored only if its real candles are present.
    htf=20
    if df_m15 is not None and len(df_m15)>=50:
        c15=df_m15["close"].astype(float).to_numpy(); a=last_valid(ema(c15,50)); b=last_valid(ema(c15,200))
        if a and b and c15[-1]>a>b: score_buy+=htf; layers["تأیید M15"]=htf
        elif a and b and c15[-1]<a<b: score_sell+=htf; layers["تأیید M15"]=htf
        else: layers["تأیید M15"]=0
    else: layers["تأیید M15"]="داده ناکافی"
    # LCT proxy: only score a sweep that returns inside the recent range.
    lct=5
    if smc["sweep"]=="BULLISH":score_buy+=lct;layers["LCT"]=lct
    elif smc["sweep"]=="BEARISH":score_sell+=lct;layers["LCT"]=lct
    else:layers["LCT"]=0
    buy=min(100,score_buy); sell=min(100,score_sell)
    if buy>=80 and buy>=sell+10: action,score="BUY",round(buy)
    elif sell>=80 and sell>=buy+10: action,score="SELL",round(sell)
    else:
        action,score="WAIT",round(max(buy,sell))
        reasons.append("شرایط ورود کامل نیست؛ تا هم‌جهتی و امتیاز معتبر صبر کنید.")
    return {"action":action,"score":score,"buy_score":round(buy),"sell_score":round(sell),"layers":layers,"reasons":reasons,"ready":True,"smc":smc,"rsi":rv,"adx":adxv,"atr":last_valid(atr(high,low,close))}
