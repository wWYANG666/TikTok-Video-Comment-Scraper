@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0make-share-package.ps1"
if errorlevel 1 (
    echo Package creation failed. See the error above.
    pause
    exit /b 1
)
pause
