@echo off
:: Losshound - Run as Administrator
:: One-click launcher with elevated privileges

:: Reliable admin check via PowerShell IsInRole.
:: NOTE: Do NOT use 'net session' here — it fails if the Server (LanmanServer)
:: service is disabled, which makes the elevated relaunch loop forever.
powershell -NoProfile -Command "if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if %errorlevel% == 0 goto :run

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
