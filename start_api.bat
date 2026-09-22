@echo off
title ZeroAPI Server v2.4.0
chcp 65001 >nul
cd /d "%~dp0"

echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo Installing dependencies...
python -m pip install -r requirements.txt --quiet

echo.
echo Starting ZeroAPI with UI mode...
echo Config: zeroapi_config.json (edit to change port/key)
echo.
python zeroapi.py

pause
