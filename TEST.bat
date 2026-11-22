@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TouchInk Studio - Tests
if not exist ".venv\Scripts\python.exe" (
    echo Please run INSTALL.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m py_compile app.py ui_icons.py engine.py ink_edit.py notebook.py raw_touchpad.py cursor_follow.py navigation.py launcher.py
if errorlevel 1 goto :failed
echo.
echo All checks passed.
pause
exit /b 0
:failed
echo.
echo Some checks failed. Please review the output.
pause
exit /b 1
