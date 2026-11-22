@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    call "%~dp0INSTALL.bat" --quiet
    if errorlevel 1 (
        echo Setup failed. Run INSTALL.bat for details.
        pause
        exit /b 1
    )
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0launcher.py"
exit /b 0
