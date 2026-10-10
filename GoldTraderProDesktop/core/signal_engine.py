"""سیگنال فوری و پیش‌بینی‌شده؛ فقط برای نمایش، بدون سفارش‌گذاری."""
from datetime import datetime,timezone
def _pending_levels(analysis,tick,settings):
    if not tick:return []
    price=float(tick.get("bid",0));cfg=settings.get("signal",{});minimum=int(cfg.get("pending_min_confidence",75));levels=analysis.get("levels",{})
    buy_score=int(analysis.get("buy_score",0));sell_score=int(analysis.get("sell_score",0));result=[]
    for action,items in (("BUY",levels.get("support",[])),("SELL",levels.get("resistance",[]))):
        candidates=[]
        for level in items:
            value=float(level.get("price",0));distance=abs(value-price);sources=level.get("sources",[])
            if not 6<=distance<=25 or len(set(sources))<2:continue
            confidence=52+min(len(set(sources)),18)
            if 6<=distance<=12:confidence+=8
            aligned=(action=="BUY" and buy_score>=sell_score) or (action=="SELL" and sell_score>=buy_score)
            confidence+=10 if aligned else -15;confidence=min(88,confidence)
            if confidence<minimum:continue
            sign=1 if action=="BUY" else -1
            candidates.append({"action":action,"level_price":round(value,2),"distance":round(distance,2),"confidence":confidence,"sl":round(value-sign*5,2),"tp1":round(value+sign*5,2),"tp2":round(value+sign*10,2),"sources":sources,"status":"پیش‌بینی؛ نیازمند تأیید قیمت"})
        if candidates:
            candidates.sort(key=lambda x:(-x["confidence"],x["distance"]));result.append(candidates[0])
    if len(result)==2 and abs(result[0]["level_price"]-result[1]["level_price"])<8:
        result=[max(result,key=lambda x:x["confidence"])]
    return result
def build_signal(analysis,tick,settings=None):
    settings=settings or {};levels_cfg=settings.get("levels",{});stamp=datetime.now(timezone.utc).isoformat()
    pending=_pending_levels(analysis,tick,settings)
    if not tick or not analysis.get("ready"):
        return {"action":"WAIT","score":0,"reason":"داده زنده یا تاریخچه کافی نیست؛ وضعیت NO DATA است.","reasons":analysis.get("reasons",[]),"pending":pending,"issued_at":stamp}
    action=analysis.get("action","WAIT");score=int(analysis.get("score",0));minimum=int(settings.get("signal",{}).get("min_confidence",80))
    if action not in ("BUY","SELL") or score<minimum:
        return {"action":"WAIT","score":score,"buy_score":analysis.get("buy_score",0),"sell_score":analysis.get("sell_score",0),"reason":f"ورود فوری تأیید نشد؛ امتیاز خرید {analysis.get('buy_score',0)}، فروش {analysis.get('sell_score',0)}، حداقل لازم {minimum}.","reasons":analysis.get("reasons",[]),"layers":analysis.get("layers",{}),"pending":pending,"issued_at":stamp}
    entry=float(tick["ask"] if action=="BUY" else tick["bid"]);sl=float(levels_cfg.get("stop_loss_dollars",5.0));tp1=float(levels_cfg.get("take_profit_1_dollars",5.0));tp2=float(levels_cfg.get("take_profit_2_dollars",10.0));sign=1 if action=="BUY" else -1
    return {"action":action,"score":score,"buy_score":analysis.get("buy_score",0),"sell_score":analysis.get("sell_score",0),"entry":entry,"sl":entry-sign*sl,"tp1":entry+sign*tp1,"tp2":entry+sign*tp2,"risk":"کم" if score>=92 else "متوسط" if score>=85 else "زیاد","reasons":analysis.get("reasons",[]),"layers":analysis.get("layers",{}),"pending":pending,"issued_at":stamp,"status":"تحلیلی؛ بدون اجرای معامله"}
