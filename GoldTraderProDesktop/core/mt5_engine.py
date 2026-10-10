"""اتصال فقط-خواندنی به MetaTrader 5؛ هیچ سفارشی ارسال نمی‌شود."""
from __future__ import annotations
import sys, time
from datetime import datetime, timedelta, timezone
import pandas as pd

class MT5Engine:
    TF_NAMES={"M1":"TIMEFRAME_M1","M2":"TIMEFRAME_M2","M3":"TIMEFRAME_M3","M5":"TIMEFRAME_M5","M15":"TIMEFRAME_M15","M30":"TIMEFRAME_M30","H1":"TIMEFRAME_H1","H4":"TIMEFRAME_H4","D1":"TIMEFRAME_D1"}
    def __init__(self,symbol="XAUUSD"):
        self.symbol=symbol; self.mt5=None; self.connected=False; self.last_error=""
    def connect(self):
        if sys.platform!="win32":
            self.last_error="اتصال MetaTrader5 فقط روی ویندوز پشتیبانی می‌شود."
            return False
        try:
            import MetaTrader5 as mt5
            self.mt5=mt5
            if not mt5.initialize():
                self.last_error=f"راه‌اندازی MT5 ناموفق: {mt5.last_error()}"; self.connected=False; return False
            info=mt5.symbol_info(self.symbol)
            if info is None:
                self.last_error=f"نماد {self.symbol} در کارگزار موجود نیست؛ نام نماد را در تنظیمات بررسی کنید."
                self.connected=False; return False
            if not info.visible and not mt5.symbol_select(self.symbol,True):
                self.last_error=f"فعال‌سازی نماد ناموفق: {mt5.last_error()}"; return False
            self.connected=True; self.last_error=""; return True
        except Exception as exc:
            self.last_error=f"خطای اتصال MT5: {exc}"; self.connected=False; return False
    def shutdown(self):
        try:
            if self.mt5: self.mt5.shutdown()
        finally: self.connected=False
    def tick(self):
        if not self.connected and not self.connect(): return None
        t=self.mt5.symbol_info_tick(self.symbol)
        if t is None:
            self.last_error=f"دریافت Tick ناموفق: {self.mt5.last_error()}"; return None
        return {"bid":float(t.bid),"ask":float(t.ask),"last":float(t.last),"spread":float(t.ask-t.bid),"time":datetime.fromtimestamp(t.time,timezone.utc).isoformat()}
    def candles(self,timeframe="M5",count=300):
        if not self.connected and not self.connect(): return pd.DataFrame()
        tf=getattr(self.mt5,self.TF_NAMES.get(timeframe,"TIMEFRAME_M5"),None)
        if tf is None:return pd.DataFrame()
        rows=self.mt5.copy_rates_from_pos(self.symbol,tf,0,int(count))
        if rows is None or len(rows)==0:
            self.last_error=f"داده کندل در دسترس نیست: {self.mt5.last_error()}"; return pd.DataFrame()
        df=pd.DataFrame(rows); df["time"]=pd.to_datetime(df["time"],unit="s",utc=True)
        return df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    def history_days(self,timeframe="M5",days=365,batch=5000):
        if not self.connected and not self.connect(): return pd.DataFrame()
        tf=getattr(self.mt5,self.TF_NAMES.get(timeframe,"TIMEFRAME_M5"),None)
        if tf is None:return pd.DataFrame()
        end=datetime.now(timezone.utc); start=end-timedelta(days=int(days)); chunks=[]; pos=0
        # MT5 limits request size; paginate by position and stop at requested date.
        while True:
            part=self.mt5.copy_rates_from_pos(self.symbol,tf,pos,batch)
            if part is None or len(part)==0: break
            df=pd.DataFrame(part); chunks.append(df)
            oldest=int(df["time"].min())
            if oldest<=int(start.timestamp()) or len(part)<batch: break
            pos+=len(part); time.sleep(0.02)
        if not chunks:return pd.DataFrame()
        out=pd.concat(chunks,ignore_index=True).drop_duplicates("time")
        out=out[out["time"]>=int(start.timestamp())].sort_values("time")
        out["time"]=pd.to_datetime(out["time"],unit="s",utc=True)
        return out.reset_index(drop=True)
