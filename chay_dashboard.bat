@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_windows.bat
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" db\local_postgres.py start
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m streamlit run bi\dashboard.py --server.port 8502 --browser.gatherUsageStats false
pause
exit /b 0
:failed
echo Khong khoi dong duoc PostgreSQL. Kiem tra .env.
pause
exit /b 1
