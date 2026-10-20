@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo Installez Python 3.11+ depuis https://www.python.org/downloads/
    echo Cochez "Add python.exe to PATH" pendant l'installation.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Premiere ouverture : creation de l'environnement...
    python -m venv .venv
    if errorlevel 1 goto fail
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto fail
    .venv\Scripts\python.exe -m playwright install chromium
    if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m src.ui
if errorlevel 1 goto fail
exit /b 0
:fail
echo Echec du lancement.
pause
exit /b 1
