"""هشدار صوتی و اعلان ویندوز؛ فقط هنگام صدور سیگنال تازه."""
def alert(action,enabled=True,notifications=True):
    if not enabled:return
    try:
        import winsound
        pattern=(800,1000,1200) if action=="BUY" else (1200,1000,800) if action=="SELL" else ()
        for hz in pattern:winsound.Beep(hz,120)
    except Exception:pass
    if notifications:
        try:
            from plyer import notification
            label="خرید ▲" if action=="BUY" else "فروش ▼"
            notification.notify(title="GoldTrader Pro",message=f"سیگنال تازه: {label}",app_name="GoldTrader Pro",timeout=5)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.MessageBeep(0x40)
            except Exception:pass
