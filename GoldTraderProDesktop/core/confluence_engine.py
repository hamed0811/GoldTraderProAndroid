"""موتور امتیازدهی وزنی ۷ لایه مطابق مشخصات؛ بدون AI و بدون سفارش‌گذاری."""
from .indicators import ema,rsi,macd,atr,adx,stochastic,last_valid
from .smc import analyze_smc
from .lct_strategy import analyze_lct
from .whale_tracker import analyze_volume
WEIGHTS={"htf_bias":20,"structure":15,"smc_zones":15,"momentum":15,"environment":10,"lct":10,"volume_proxy":15}
def analyze(df_m5,df_m15=None,df_h1=None,df_h4=None,df_d1=None):
    if df_m5 is None or len(df_m5)<60:return {"action":"WAIT","score":0,"layers":{},"reasons":["برای تحلیل معتبر حداقل ۶۰ کندل تایم‌فریم انتخابی لازم است."],"ready":False}
    close=df_m5.close.astype(float).to_numpy();high=df_m5.high.astype(float).to_numpy();low=df_m5.low.astype(float).to_numpy()
    rv=last_valid(rsi(close,14));ml,ms,mh=macd(close);mline=last_valid(ml);msig=last_valid(ms);av,pdi,mdi=adx(high,low,close);adxv=last_valid(av);pdi=last_valid(pdi);mdi=last_valid(mdi);sk,sd=stochastic(high,low,close);kv=last_valid(sk);dv=last_valid(sd)
    smc=analyze_smc(df_m5);lct=analyze_lct(df_m15 if df_m15 is not None and len(df_m15)>=30 else df_m5);vol=analyze_volume(df_m5);buy=sell=0.0;layers={};reasons=[]
    directions=[]
    for frame,period in ((df_d1,50),(df_h4,200)):
        if frame is not None and len(frame)>=period+2:
            c=frame.close.astype(float).to_numpy();ev=last_valid(ema(c,period));directions.append("BULLISH" if ev is not None and c[-1]>ev else "BEARISH" if ev is not None and c[-1]<ev else "NEUTRAL")
        else:directions.append("NO DATA")
    if directions==["BULLISH","BULLISH"]:buy+=20;layers["روند تایم‌فریم بالا"]=20;reasons.append("روند D1 و H4 صعودی است.")
    elif directions==["BEARISH","BEARISH"]:sell+=20;layers["روند تایم‌فریم بالا"]=20;reasons.append("روند D1 و H4 نزولی است.")
    else:layers["روند تایم‌فریم بالا"]="داده ناکافی/ناهمسو"
    if smc["bos"]=="BULLISH":buy+=15;layers["ساختار بازار"]=15;reasons.append("BOS صعودی تشخیص داده شد.")
    elif smc["bos"]=="BEARISH":sell+=15;layers["ساختار بازار"]=15;reasons.append("BOS نزولی تشخیص داده شد.")
    else:layers["ساختار بازار"]=0
    sscore=0
    if smc["sweep"]=="BULLISH":buy+=3;sscore+=3;reasons.append("Sweep صعودی نقدینگی مشاهده شد.")
    elif smc["sweep"]=="BEARISH":sell+=3;sscore+=3;reasons.append("Sweep نزولی نقدینگی مشاهده شد.")
    for gap in smc.get("fvg",[]):
        if gap["side"]=="BULLISH" and close[-1]>=gap["low"]:buy+=4;sscore+=4;reasons.append("عدم‌تعادل صعودی FVG شناسایی شد.");break
        if gap["side"]=="BEARISH" and close[-1]<=gap["high"]:sell+=4;sscore+=4;reasons.append("عدم‌تعادل نزولی FVG شناسایی شد.");break
    for ob in smc.get("order_blocks",[]):
        if ob["side"]=="BULLISH" and close[-1]>=ob["low"]:buy+=5;sscore+=5;reasons.append("Order Block صعودی شناسایی شد.");break
        if ob["side"]=="BEARISH" and close[-1]<=ob["high"]:sell+=5;sscore+=5;reasons.append("Order Block نزولی شناسایی شد.");break
    if smc.get("premium_discount")=="DISCOUNT":buy+=min(3,15-sscore);sscore+=min(3,15-sscore)
    elif smc.get("premium_discount")=="PREMIUM":sell+=min(3,15-sscore);sscore+=min(3,15-sscore)
    layers["مناطق SMC"]=min(15,sscore)
    mscore=0
    if rv is not None and mline is not None and msig is not None and kv is not None and dv is not None:
        if rv>=52 and mline>msig and kv>=dv:buy+=15;mscore=15;reasons.append(f"مومنتوم صعودی؛ RSI={rv:.1f}.")
        elif rv<=48 and mline<msig and kv<=dv:sell+=15;mscore=15;reasons.append(f"مومنتوم نزولی؛ RSI={rv:.1f}.")
    layers["مومنتوم RSI/Stochastic/MACD"]=mscore
    escore=0
    if adxv is not None and adxv>=22 and pdi is not None and mdi is not None:
        if pdi>mdi:buy+=7;escore+=7
        elif mdi>pdi:sell+=7;escore+=7
    if vol["bias"]=="BULLISH":buy+=3;escore+=3
    elif vol["bias"]=="BEARISH":sell+=3;escore+=3
    layers["محیط/ADX/حجم"]=escore
    lscore=min(10,int(lct.get("score",0)))
    if lct["bias"]=="BULLISH":buy+=lscore;reasons.append(lct["reason"])
    elif lct["bias"]=="BEARISH":sell+=lscore;reasons.append(lct["reason"])
    layers["استراتژی LCT"]=lscore
    vscore=min(15,int(vol.get("score",0)))
    if vol["bias"]=="BULLISH":buy+=vscore
    elif vol["bias"]=="BEARISH":sell+=vscore
    layers["پروکسی حجم کارگزار"]=vscore if vol["bias"] not in ("NO DATA","NEUTRAL") else 0
    if vol.get("signals"):reasons.append("نشانه‌های حجم کارگزار: "+", ".join(vol["signals"]))
    buy=min(100,buy);sell=min(100,sell)
    if buy>=80 and buy>=sell+10:action,score="BUY",round(buy)
    elif sell>=80 and sell>=buy+10:action,score="SELL",round(sell)
    else:action,score="WAIT",round(max(buy,sell));reasons.append("هم‌جهتی/امتیاز لازم کامل نیست؛ تصمیم امن فعلی انتظار است.")
    return {"action":action,"score":score,"buy_score":round(buy),"sell_score":round(sell),"layers":layers,"reasons":reasons,"ready":True,"smc":smc,"lct":lct,"volume_proxy":vol,"rsi":rv,"adx":adxv,"atr":last_valid(atr(high,low,close))}
