@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TouchInk Studio - Debug Launcher
if not exist ".venv\Scripts\python.exe" (
    echo TouchInk is not installed yet. Starting setup...
    call "%~dp0INSTALL.bat" --quiet
    if errorlevel 1 goto :failed
)
echo Starting TouchInk Studio...
echo Tab toggles Ink / Navigate. Arrow keys move the writing window in 2D.
echo.
".venv\Scripts\python.exe" "%~dp0launcher.py"
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo [ERROR] TouchInk Studio did not start successfully.
echo Check logs\launch.log or run INSTALL.bat again.
pause
exit /b 1
