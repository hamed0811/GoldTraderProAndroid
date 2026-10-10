"""ساخت بسته قابل اجرای ویندوز؛ MT5 دسکتاپ باید جداگانه نصب باشد."""
import subprocess,sys
command=[sys.executable,"-m","PyInstaller","--noconfirm","--windowed","--name","GoldTraderPro","--add-data","config;config","--collect-all","pyqtgraph","--hidden-import","MetaTrader5","main.py"]
raise SystemExit(subprocess.call(command))
