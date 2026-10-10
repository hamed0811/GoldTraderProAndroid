"""ساخت exe موتور تحلیل خط فرمان."""
import subprocess,sys
raise SystemExit(subprocess.call([sys.executable,"-m","PyInstaller","--noconfirm","--name","GoldTraderProEngine","run_agent.py"]))
