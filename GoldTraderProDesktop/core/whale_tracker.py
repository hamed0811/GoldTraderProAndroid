"""تحلیل tick-volume کارگزار؛ این شاخص‌ها پروکسی هستند، نه مشاهده مستقیم نهنگ‌ها."""
def analyze_volume(df):
    if df is None or len(df)<25:return {"bias":"NO DATA","score":0,"signals":[],"smfi":None,"wyckoff":"NO DATA","note":"تاریخچه حجم ناکافی"}
    vol=df.get("tick_volume",df.get("real_volume"))
    if vol is None:return {"bias":"NO DATA","score":0,"signals":[],"smfi":None,"wyckoff":"NO DATA","note":"کارگزار حجم ارائه نکرد"}
    v=vol.astype(float).to_numpy();o=df.open.astype(float).to_numpy();c=df.close.astype(float).to_numpy();h=df.high.astype(float).to_numpy();l=df.low.astype(float).to_numpy()
    avg=float(v[-21:-1].mean())
    if avg<=0:return {"bias":"NO DATA","score":0,"signals":[],"smfi":None,"wyckoff":"NO DATA","note":"میانگین حجم معتبر نیست"}
    signals=[];votes=[];rng=max(h[-1]-l[-1],1e-9);body=abs(c[-1]-o[-1])
    if v[-1]>2*avg:
        signals.append("جهش tick-volume")
        if c[-1]>o[-1]:votes.append("BULLISH")
        elif c[-1]<o[-1]:votes.append("BEARISH")
    if v[-1]>1.5*avg and body/rng<0.30:
        signals.append("جذب/Absorption")
        if c[-1]>=o[-1]:votes.append("BULLISH")
        else:votes.append("BEARISH")
    upper_wick=h[-1]-max(o[-1],c[-1]);lower_wick=min(o[-1],c[-1])-l[-1]
    if v[-1]>1.3*avg and upper_wick>2*max(body,1e-9) and upper_wick/rng>0.60:
        signals.append("شکار نقدینگی بالای سقف");votes.append("BEARISH")
    if v[-1]>1.3*avg and lower_wick>2*max(body,1e-9) and lower_wick/rng>0.60:
        signals.append("شکار نقدینگی زیر کف");votes.append("BULLISH")
    recent_max=float(max(v[-5:]))
    if recent_max>3*avg:
        idx=len(v)-5+int(v[-5:].argmax())
        if idx>=0:
            if c[idx]>o[idx]:signals.append("اوج حجم خرید/Climax");votes.append("BEARISH")
            elif c[idx]<o[idx]:signals.append("اوج حجم فروش/Climax");votes.append("BULLISH")
    typical=(h+l+c)/3;money=typical*v;prev=np_prev(c)
    pos=float(money[1:][c[1:]>prev].sum());neg=float(money[1:][c[1:]<prev].sum());smfi=50.0 if pos+neg==0 else 100.0*pos/(pos+neg)
    if smfi>=65:signals.append(f"SMFI صعودی {smfi:.1f}");votes.append("BULLISH")
    elif smfi<=35:signals.append(f"SMFI نزولی {smfi:.1f}");votes.append("BEARISH")
    range_hi=float(max(h[-50:]));range_lo=float(min(l[-50:]));range_width=max(range_hi-range_lo,1e-9);location=(c[-1]-range_lo)/range_width
    wyckoff="RANGING"
    if v[-1]>1.5*avg and location<=0.25:wyckoff="ACCUMULATION";signals.append("Wyckoff: انباشت");votes.append("BULLISH")
    elif v[-1]>1.5*avg and location>=0.75:wyckoff="DISTRIBUTION";signals.append("Wyckoff: توزیع");votes.append("BEARISH")
    elif c[-1]>c[-10]:wyckoff="MARKUP"
    elif c[-1]<c[-10]:wyckoff="MARKDOWN"
    bull=votes.count("BULLISH");bear=votes.count("BEARISH");bias="BULLISH" if bull>bear else "BEARISH" if bear>bull else "NEUTRAL"
    return {"bias":bias,"score":min(15,3*len(signals)),"signals":signals,"smfi":round(smfi,2),"wyckoff":wyckoff,"note":"برآورد از tick-volume همین کارگزار؛ جریان سفارش جهانی یا کیف‌پول نهنگ‌ها نیست"}
def np_prev(values):
    return values[:-1]
