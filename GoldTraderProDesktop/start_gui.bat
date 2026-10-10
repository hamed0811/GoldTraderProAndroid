@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating virtual environment...
  py -3.11 -m venv .venv
  if errorlevel 1 goto error
)
echo [2/2] Installing/checking requirements...
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo ERROR: The application did not start. Read the error above.
pause
exit /b 1
