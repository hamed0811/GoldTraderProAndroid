@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo GoldTrader Pro - MT5 Cloud Bridge (read-only)
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo First run: set the HTTPS URL and ingest token in .env.
  notepad ".env"
  echo Save Notepad, then return here and press any key.
  pause >nul
)
if not exist ".venv\Scripts\python.exe" (
  where py.exe >nul 2>&1
  if errorlevel 1 goto no_python
  py -3.11 -m venv .venv
  if errorlevel 1 goto error
)
echo Installing or checking bridge dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 (
  echo Mirror failed; retrying official PyPI...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" mt5_bridge.py
if errorlevel 1 goto error
exit /b 0
:no_python
echo ERROR: Python 3.11 x64 and py.exe are required. Install and log in to MT5.
pause
exit /b 2
:error
echo Bridge stopped; inspect the message above and .env.
pause
exit /b 1
