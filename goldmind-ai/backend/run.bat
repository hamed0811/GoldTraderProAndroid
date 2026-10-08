@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo GoldMind AI - LAN Signal Server
echo ============================================================
echo.

REM This server must be reachable from Android on the LAN.
REM Elevate once so Windows Firewall rules are actually applied.
fltmc >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator permission for Windows Firewall...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall add rule name="GoldTraderPro TCP 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul
if errorlevel 1 echo [WARNING] TCP 8000 firewall rule could not be added.

netsh advfirewall firewall add rule name="GoldTraderPro UDP 8766" dir=in action=allow protocol=UDP localport=8766 profile=any >nul
if errorlevel 1 echo [WARNING] UDP 8766 firewall rule could not be added.

echo LAN firewall rules prepared: TCP 8000 / UDP 8766
echo Starting server on 0.0.0.0:8000 ...
echo Keep this window open while using the Android app.
echo.

python main.py

echo.
echo Server stopped.
pause
