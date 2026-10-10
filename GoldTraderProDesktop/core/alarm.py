"""هشدار صوتی ویندوز؛ فقط هنگام صدور سیگنال تازه."""
def alert(action,enabled=True):
    if not enabled:return
    try:
        import winsound
        pattern=(800,1000,1200) if action=="BUY" else (1200,1000,800) if action=="SELL" else ()
        for hz in pattern:winsound.Beep(hz,120)
    except Exception:
        try:
            import sys
            if sys.platform=="win32":
                import ctypes;ctypes.windll.user32.MessageBeep(0x40)
        except Exception:pass
