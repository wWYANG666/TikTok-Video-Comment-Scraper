@echo off
setlocal
cd /d "%~dp0"

echo Setting up TikTok Collector...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
set "SETUP_EXIT=%ERRORLEVEL%"

if not "%~1"=="/quiet" pause
exit /b %SETUP_EXIT%
