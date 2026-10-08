@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo GoldMind AI - LAN Signal Server
echo ============================================================
echo.

REM Open the two LAN ports required by the Android signal client.
REM If this CMD is not elevated, the server will still start; the
REM existing firewall rules are left unchanged.
netsh advfirewall firewall add rule name="GoldTraderPro TCP 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
netsh advfirewall firewall add rule name="GoldTraderPro UDP 8766" dir=in action=allow protocol=UDP localport=8766 >nul 2>&1

echo LAN ports prepared: TCP 8000 / UDP 8766
echo Starting server on 0.0.0.0:8000 ...
echo Keep this window open while using the Android app.
echo.

python main.py
echo.
echo Server stopped. Press any key to close.
pause
