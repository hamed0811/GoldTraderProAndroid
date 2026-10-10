"""کنترل‌های ایمنی برای نمایش سیگنال؛ ماژول سفارش‌گذاری عمداً وجود ندارد."""
from datetime import datetime, timedelta, timezone
class RiskManager:
    def __init__(self,max_consecutive_losses=2,lock_minutes=30,daily_drawdown_percent=3.0):
        self.max_losses=max_consecutive_losses; self.lock_minutes=lock_minutes; self.daily_dd=daily_drawdown_percent
        self.consecutive_losses=0; self.lock_until=None; self.day=None; self.day_pnl=0.0; self.start_equity=None
    def record_result(self,pnl):
        self.consecutive_losses=self.consecutive_losses+1 if pnl<0 else 0
        self.day_pnl+=float(pnl)
        if self.consecutive_losses>=self.max_losses:self.lock_until=datetime.now(timezone.utc)+timedelta(minutes=self.lock_minutes)
    def is_locked(self):
        if self.lock_until and datetime.now(timezone.utc)<self.lock_until:return True
        if self.lock_until:self.lock_until=None
        return False
    def status(self):
        return {"locked":self.is_locked(),"lock_until":self.lock_until.isoformat() if self.lock_until else None,"daily_pnl":self.day_pnl,"consecutive_losses":self.consecutive_losses}
