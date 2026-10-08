@echo off
setlocal EnableExtensions EnableDelayedExpansion
title GoldMind AI - MT5 SIGNAL ONLY Installer
echo ============================================================
echo GoldMind AI - MT5 SIGNAL ONLY
echo No automatic order execution
echo ============================================================
echo.

set /p "MT5DATA=Paste your MT5 Data Folder path: "
if not defined MT5DATA (
  echo ERROR: No path entered.
  pause
  exit /b 1
)

if not exist "%MT5DATA%" (
  echo ERROR: Folder does not exist:
  echo %MT5DATA%
  pause
  exit /b 1
)

set "ROOT=%MT5DATA%\MQL5"
set "EXPERTS=%ROOT%\Experts"
if not exist "%EXPERTS%" mkdir "%EXPERTS%"

set "URL=https://raw.githubusercontent.com/hamed0811/GoldTraderProAndroid/main/goldmind-ai/mt5/Experts/GoldMind_AI_SIGNAL_ONLY.mq5"
set "OUT=%EXPERTS%\GoldMind_AI_SIGNAL_ONLY.mq5"

echo.
echo Downloading signal-only MT5 source...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%OUT%'"
if errorlevel 1 (
  echo ERROR: Download failed.
  pause
  exit /b 1
)

if not exist "%OUT%" (
  echo ERROR: Source file was not created.
  pause
  exit /b 1
)

echo.
echo Installed:
echo %OUT%
echo.
echo IMPORTANT:
echo 1. Open MetaEditor from MT5.
echo 2. Open GoldMind_AI_SIGNAL_ONLY.mq5.
echo 3. Press F7 and require 0 errors.
echo 4. Attach it only to your broker's XAUUSD/GOLD chart.
echo 5. Add http://127.0.0.1:8000 to MT5 WebRequest allowed URLs.
echo 6. This EA contains NO trade execution calls.
echo.
echo Do NOT enable an old GoldMind_AI.ex5 EA for this project.
echo ============================================================
pause
endlocal
