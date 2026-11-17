@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3,11), 'Can Python 3.11 tro len'"
if errorlevel 1 goto failed
if not exist ".env" copy ".env.example" ".env" >nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Da cai moi truong. Chay chay_etl.bat de tao PostgreSQL va nap du lieu.
pause
exit /b 0
:failed
echo Cai dat that bai. Kiem tra Python va ket noi Internet.
pause
exit /b 1
