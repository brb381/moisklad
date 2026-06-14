@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
set PYTHONDONTWRITEBYTECODE=1
".venv\Scripts\python.exe" -m pytest -q
