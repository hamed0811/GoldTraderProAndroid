"""پروکسی حجم کارگزار؛ این داده، ردیابی واقعی کیف‌پول یا نهنگ نیست."""
def analyze_volume(df):
    if df is None or len(df)<25:return {"bias":"NO DATA","score":0,"signals":[],"note":"تاریخچه حجم ناکافی"}
    vol=df.get("tick_volume",df.get("real_volume"))
    if vol is None:return {"bias":"NO DATA","score":0,"signals":[],"note":"کارگزار حجم ارائه نکرد"}
    v=vol.astype(float).to_numpy();o=df.open.astype(float).to_numpy();c=df.close.astype(float).to_numpy();h=df.high.astype(float).to_numpy();l=df.low.astype(float).to_numpy()
    avg=float(v[-21:-1].mean())
    if avg<=0:return {"bias":"NO DATA","score":0,"signals":[],"note":"میانگین حجم معتبر نیست"}
    signals=[];up=down=0
    if v[-1]>2*avg:
        signals.append("جهش tick-volume")
        if c[-1]>o[-1]:up+=1
        elif c[-1]<o[-1]:down+=1
    rng=max(h[-1]-l[-1],1e-9);body=abs(c[-1]-o[-1])
    if v[-1]>1.5*avg and body/rng<0.30:signals.append("حجم بالا با بدنه کوچک")
    if v[-1]>1.3*avg and (h[-1]-max(o[-1],c[-1]))/rng>0.60:signals.append("سایه بالایی بلند");down+=1
    if v[-1]>1.3*avg and (min(o[-1],c[-1])-l[-1])/rng>0.60:signals.append("سایه پایینی بلند");up+=1
    bias="BULLISH" if up>down else "BEARISH" if down>up else "NEUTRAL"
    return {"bias":bias,"score":min(15,3*len(signals)),"signals":signals,"note":"فقط tick-volume کارگزار؛ داده نهنگ/جریان سفارش تجمیعی نیست"}
