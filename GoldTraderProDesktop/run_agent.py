import json,time
from pathlib import Path
from core.mt5_engine import MT5Engine
from core.confluence_engine import analyze
from core.signal_engine import build_signal
from core.signal_logger import SignalLogger
ROOT=Path(__file__).resolve().parent
def main():
    settings=json.loads((ROOT/"config"/"default.json").read_text(encoding="utf-8"))
    engine=MT5Engine(settings["mt5"]["symbol"]);logger=SignalLogger(ROOT);last=None
    try:
        while True:
            tick=engine.tick()
            if tick:
                df=engine.candles("M5",500);m15=engine.candles("M15",250)
                result=build_signal(analyze(df,m15),tick,settings)
                print(f"{result.get('issued_at')} | {result.get('action')} | score={result.get('score','—')} | {result.get('reason','')}",flush=True)
                if result.get("action") in ("BUY","SELL"):
                    key=(result["action"],round(result["entry"],2))
                    if key!=last:logger.append(result);last=key
            else:print("NO DATA:",engine.last_error,flush=True)
            time.sleep(2)
    except KeyboardInterrupt:pass
    finally:engine.shutdown()
if __name__=="__main__":main()
