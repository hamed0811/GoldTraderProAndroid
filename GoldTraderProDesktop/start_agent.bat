@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" run_agent.py
if errorlevel 1 goto error
exit /b 0
:error
echo ERROR: Engine stopped. Read the error above.
pause
