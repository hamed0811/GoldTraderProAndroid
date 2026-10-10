@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist "%~dp0GoldTraderPro_AutoConsole.bat" (
  call "%~dp0GoldTraderPro_AutoConsole.bat"
  exit /b %ERRORLEVEL%
)

echo ERROR: GoldTraderPro_AutoConsole.bat was not found.
echo Restore the companion console files or use the project README.
pause
exit /b 2
