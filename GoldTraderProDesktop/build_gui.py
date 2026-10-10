"""ساخت exe رابط گرافیکی با PyInstaller."""
import subprocess,sys
raise SystemExit(subprocess.call([sys.executable,"-m","PyInstaller","--noconfirm","--windowed","--name","GoldTraderPro","main.py"]))
