"""تولید سیگنال تحلیلی فقط؛ هیچ سفارش معاملاتی ارسال نمی‌شود."""
from datetime import datetime, timezone
def build_signal(analysis,tick,settings=None):
    settings=settings or {};levels=settings.get("levels",{});stamp=datetime.now(timezone.utc).isoformat()
    if not tick or not analysis.get("ready"):
        return {"action":"WAIT","score":0,"reason":"داده زنده یا تاریخچه کافی نیست؛ وضعیت NO DATA است.","reasons":analysis.get("reasons",[]),"issued_at":stamp}
    action=analysis.get("action","WAIT");score=int(analysis.get("score",0));minimum=int(settings.get("signal",{}).get("min_confidence",80))
    if action not in ("BUY","SELL") or score<minimum:
        return {"action":"WAIT","score":score,"buy_score":analysis.get("buy_score",0),"sell_score":analysis.get("sell_score",0),"reason":f"ورود تأیید نشد؛ امتیاز خرید {analysis.get('buy_score',0)}، امتیاز فروش {analysis.get('sell_score',0)}، حداقل لازم {minimum}.","reasons":analysis.get("reasons",[]),"layers":analysis.get("layers",{}),"issued_at":stamp}
    entry=float(tick["ask"] if action=="BUY" else tick["bid"]);sl=float(levels.get("stop_loss_dollars",5.0));tp1=float(levels.get("take_profit_1_dollars",5.0));tp2=float(levels.get("take_profit_2_dollars",10.0));sign=1 if action=="BUY" else -1
    return {"action":action,"score":score,"buy_score":analysis.get("buy_score",0),"sell_score":analysis.get("sell_score",0),"entry":entry,"sl":entry-sign*sl,"tp1":entry+sign*tp1,"tp2":entry+sign*tp2,"risk":"کم" if score>=92 else "متوسط" if score>=85 else "زیاد","reasons":analysis.get("reasons",[]),"layers":analysis.get("layers",{}),"issued_at":stamp,"status":"تحلیلی؛ بدون اجرای معامله"}
