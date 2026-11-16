@echo off
title NSE P/E Scanner
cd /d "%~dp0"

rem ---- 1. Find Python -------------------------------------------------------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (where py >nul 2>nul && set "PY=py")
if not defined PY (
    echo.
    echo  Python is not installed on this computer.
    echo  Install it from https://www.python.org/downloads/
    echo  and tick "Add python.exe to PATH" during setup. Then double-click START_HERE.bat again.
    echo.
    pause
    exit /b 1
)

rem ---- 2. Install the packages the scanner needs, if they are missing ----------
%PY% -c "import pandas, numpy" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  First run: installing the Python packages the scanner needs ^(pandas, numpy^).
    echo  This needs the internet and takes a minute or two...
    echo.
    %PY% -m pip install --user --disable-pip-version-check pandas numpy
    %PY% -c "import pandas, numpy" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  The packages could not be installed. Check your internet connection and try again.
        echo.
        pause
        exit /b 1
    )
)

rem ---- 3. Start the app: it opens its own window and stops when that window is closed
echo  Starting NSE P/E Scanner - its window will open in a moment.
start "NSE P/E Scanner" /min cmd /c "%PY% app.py || pause"
