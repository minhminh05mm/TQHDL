@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_windows.bat
if not exist ".venv\Scripts\python.exe" exit /b 1
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" db\local_postgres.py start
if errorlevel 1 goto failed
".venv\Scripts\python.exe" etl.py
if errorlevel 1 goto failed
echo ETL thanh cong. Chay chay_dashboard.bat de mo Streamlit.
pause
exit /b 0
:failed
echo ETL that bai. Xem thong bao va report/readme_chuyen_may.md.
pause
exit /b 1
