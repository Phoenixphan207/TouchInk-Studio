@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TouchInk Studio - Setup
color 0F

echo.
echo  ========================================================
echo                TOUCHINK STUDIO - SETUP
echo  ========================================================
echo.

rem Reuse an existing working virtual environment first.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys,tkinter;sys.exit(0 if sys.version_info.major==3 and sys.version_info.minor>=10 else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo [1/3] Using the existing TouchInk virtual environment.
        ".venv\Scripts\python.exe" --version
        goto :install_packages
    )
    echo [ERROR] The existing .venv is not usable.
    echo To rebuild it, close the app and run REPAIR.bat.
    goto :failed
)

set "PYTHON_CMD="
rem Use a compatible Python from the Python Launcher, even if python.exe is not on PATH.
rem Prefer stable installed versions rather than assuming only 3.11/3.12 exist.
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
    if not defined PYTHON_CMD (
        py -%%V -c "import sys,tkinter,venv;sys.exit(0 if sys.version_info.major==3 and sys.version_info.minor>=10 and sys.maxsize>2**32 else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=py -%%V"
    )
)
rem Also allow a newer installed Python if its dependencies are supported.
if not defined PYTHON_CMD (
    py -3 -c "import sys,tkinter,venv;sys.exit(0 if sys.version_info.major==3 and sys.version_info.minor>=10 and sys.maxsize>2**32 else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    python -c "import sys,tkinter,venv;sys.exit(0 if sys.version_info.major==3 and sys.version_info.minor>=10 and sys.maxsize>2**32 else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    python3 -c "import sys,tkinter,venv;sys.exit(0 if sys.version_info.major==3 and sys.version_info.minor>=10 and sys.maxsize>2**32 else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python3"
)

if not defined PYTHON_CMD (
    echo [ERROR] No compatible 64-bit Python 3.10+ installation was detected.
    echo This does not necessarily mean Python is absent; it may be unavailable on PATH.
    echo.
    echo Checking installed Python launchers:
    py --list-paths 2>nul
    echo.
    echo Try these commands in a new Command Prompt:
    echo   py -0p
    echo   python --version
    echo.
    echo If you have Python installed, ensure the Python Launcher or Python is on PATH.
    goto :failed
)

echo [1/3] Detected Python:
%PYTHON_CMD% --version

echo [2/3] Creating a private environment for TouchInk...
%PYTHON_CMD% -m venv ".venv"
if errorlevel 1 goto :failed

:install_packages
if not exist ".venv\Scripts\python.exe" goto :failed
echo [3/3] Installing TouchInk dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] TouchInk Studio is ready.
echo Double-click QUICK_START.bat or START.bat to launch.
if /I "%~1"=="--quiet" exit /b 0
pause
exit /b 0

:failed
echo.
echo Setup could not finish. Read the message above.
if /I "%~1"=="--quiet" exit /b 1
pause
exit /b 1
