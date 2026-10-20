@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Lancez launch.bat une premiere fois pour installer Python et les dependances.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m src.ui
