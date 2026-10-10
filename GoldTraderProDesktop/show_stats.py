from core.signal_logger import SignalLogger
def main():
    rows=SignalLogger().all()
    print("کل سیگنال‌های ثبت‌شده:",len(rows))
    for action in ("BUY","SELL","WAIT"):print(action,sum(r.get("action")==action for r in rows))
    print("نتایج برد/باخت تا وقتی نتیجه واقعی ثبت نشده، محاسبه نمی‌شود.")
if __name__=="__main__":main()
