@echo off
setlocal
cd /d "%~dp0"
set "APP_PORT=8000"
if defined TIKTOK_PORT set "APP_PORT=%TIKTOK_PORT%"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Project environment is missing. Starting setup...
    call "%~dp0setup.bat" /quiet
    if errorlevel 1 goto :failed
)

"%PYTHON_EXE%" -c "import sys, app.main, multipart, tzdata; from pathlib import Path; from playwright.sync_api import sync_playwright; assert sys.version_info[:2] == (3, 12); p = sync_playwright().start(); assert Path(p.chromium.executable_path).is_file(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo Project dependencies or Chromium are missing. Repairing installation...
    call "%~dp0setup.bat" /quiet
    if errorlevel 1 goto :failed
)

"%PYTHON_EXE%" -c "import socket, sys; s = socket.socket(); result = s.connect_ex(('127.0.0.1', int(sys.argv[1]))); s.close(); raise SystemExit(0 if result else 1)" "%APP_PORT%"
if errorlevel 1 (
    echo Port %APP_PORT% is unavailable. Close the existing server or app, then try again.
    goto :failed
)

echo TikTok Collector is starting...
echo Open http://127.0.0.1:%APP_PORT% in your browser.
echo Press Ctrl+C to stop the server.
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %APP_PORT%
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Startup failed. See the error above.
pause
exit /b 1
