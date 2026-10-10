@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0GoldTraderPro_AutoConsole.ps1" (
  echo ERROR: GoldTraderPro_AutoConsole.ps1 was not found beside this file.
  echo Keep the BAT and PS1 files in the same folder.
  pause
  exit /b 2
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell was not found.
  pause
  exit /b 3
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0GoldTraderPro_AutoConsole.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo Console completed successfully.
) else (
  echo Console stopped with exit code %RESULT%. Check the log shown above.
)
echo.
pause
exit /b %RESULT%
