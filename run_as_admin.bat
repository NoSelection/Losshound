@echo off
:: Losshound - Run as Administrator
:: One-click launcher with elevated privileges

:: Check if already running as admin
net session >nul 2>&1
if %errorlevel% == 0 (
    goto :run
)

:: Request admin elevation
echo Requesting administrator privileges...
powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
exit /b

:run
cd /d "%~dp0"
title Losshound (Administrator)

:: Activate venv if it exists, otherwise use system Python
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python -m losshound %*
pause
