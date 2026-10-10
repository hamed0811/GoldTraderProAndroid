"""تولید سیگنال تحلیلی فقط؛ هیچ سفارش معاملاتی ارسال نمی‌شود."""
from datetime import datetime, timezone

def build_signal(analysis,tick,settings=None):
    settings=settings or {}; levels=settings.get("levels",{})
    if not tick or not analysis.get("ready"):
        return {"action":"WAIT","reason":"داده زنده یا تاریخچه کافی نیست.","issued_at":datetime.now(timezone.utc).isoformat()}
    action=analysis.get("action","WAIT"); score=int(analysis.get("score",0))
    if action not in ("BUY","SELL") or score<int(settings.get("signal",{}).get("min_confidence",80)):
        return {"action":"WAIT","score":score,"reason":"امتیاز/هم‌جهتی برای ورود کافی نیست.","issued_at":datetime.now(timezone.utc).isoformat()}
    entry=float(tick["ask"] if action=="BUY" else tick["bid"])
    sl=float(levels.get("stop_loss_dollars",5.0)); tp1=float(levels.get("take_profit_1_dollars",5.0)); tp2=float(levels.get("take_profit_2_dollars",10.0))
    sign=1 if action=="BUY" else -1
    return {"action":action,"score":score,"entry":entry,"sl":entry-sign*sl,"tp1":entry+sign*tp1,"tp2":entry+sign*tp2,"risk":"کم" if score>=92 else "متوسط" if score>=85 else "زیاد","reasons":analysis.get("reasons",[]),"layers":analysis.get("layers",{}),"issued_at":datetime.now(timezone.utc).isoformat(),"status":"تحلیلی؛ بدون اجرای معامله"}
