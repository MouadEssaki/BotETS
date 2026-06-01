@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creez d'abord le venv: python -m venv .venv
    exit /b 1
)
.venv\Scripts\python.exe -m src.main
