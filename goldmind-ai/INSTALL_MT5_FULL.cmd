@echo off
setlocal
title GoldMind AI - MT5 Installer

echo ==========================================
echo GoldMind AI - MT5 component installer
echo ==========================================
echo.
echo This script downloads the upstream compiled EA and installs
echo the JSON include file into the selected MT5 data folder.
echo It does NOT enable automatic trading.
echo.

set "ROOT=%~dp0"
set "EAURL=https://raw.githubusercontent.com/syarief02/goldmind-ai/master/mt5/Experts/GoldMind_AI.ex5"
set "INCURL=https://raw.githubusercontent.com/syarief02/goldmind-ai/master/mt5/Include/JASONNode.mqh"

where curl >nul 2>nul
if errorlevel 1 (
  echo ERROR: curl is not available on this Windows installation.
  pause
  exit /b 1
)

echo.
set /p "MT5DATA=Enter your MT5 Data Folder path: "
if "%MT5DATA%"=="" (
  echo ERROR: MT5 Data Folder was not entered.
  pause
  exit /b 1
)

if not exist "%MT5DATA%\MQL5\Experts" mkdir "%MT5DATA%\MQL5\Experts"
if not exist "%MT5DATA%\MQL5\Include" mkdir "%MT5DATA%\MQL5\Include"

echo.
echo Downloading GoldMind_AI.ex5...
curl -L --fail --retry 3 "%EAURL%" -o "%MT5DATA%\MQL5\Experts\GoldMind_AI.ex5"
if errorlevel 1 (
  echo ERROR: EA download failed.
  pause
  exit /b 1
)

echo Downloading JASONNode.mqh...
curl -L --fail --retry 3 "%INCURL%" -o "%MT5DATA%\MQL5\Include\JASONNode.mqh"
if errorlevel 1 (
  echo ERROR: include download failed.
  pause
  exit /b 1
)

echo.
echo INSTALLATION COMPLETE.
echo EA: %MT5DATA%\MQL5\Experts\GoldMind_AI.ex5
echo Include: %MT5DATA%\MQL5\Include\JASONNode.mqh
echo.
echo IMPORTANT: The upstream EA can place trades. Do NOT enable Algo Trading
echo until we convert it to SIGNAL-ONLY as planned.
echo.
pause
