@echo off
setlocal
:: Losshound - Run as Administrator
:: One-click launcher with elevated privileges

:: Require the project environment before requesting elevation.
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Losshound requires the project .venv. Complete setup in README.md first.
    pause
    exit /b 1
)

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

:: Run the source checkout with the reviewed project environment.
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m losshound %*
pause
