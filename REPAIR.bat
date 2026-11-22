@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TouchInk Studio - Repair
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        echo Reinstalling TouchInk dependencies...
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade --force-reinstall -r requirements.txt
        if errorlevel 1 goto :failed
        echo [SUCCESS] Dependencies repaired.
        pause
        exit /b 0
    )
)
if exist ".venv" (
    echo Backing up a broken .venv as .venv.old before recreating it...
    if exist ".venv.old" (
        echo [ERROR] .venv.old already exists. Rename it first to preserve your previous backup.
        goto :failed
    )
    ren ".venv" ".venv.old"
    if errorlevel 1 goto :failed
)
call "%~dp0INSTALL.bat" --quiet
if errorlevel 1 goto :failed
echo [SUCCESS] TouchInk environment recreated.
pause
exit /b 0
:failed
echo [ERROR] Repair failed. No notebook data was modified.
pause
exit /b 1
