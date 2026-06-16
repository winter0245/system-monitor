@echo off
chcp 65001 >nul
setlocal

set APP_DIR=%~dp0
set PORT=8900

echo === NAS Monitor ===

:: stop: kill any process on the port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%.*LISTENING" 2^>nul') do (
    echo Stopping PID=%%a...
    taskkill /F /PID %%a 2>nul
    timeout /t 2 >nul
)

if "%1"=="stop" (
    echo Stopped.
    exit /b 0
)

if "%1"=="restart" (
    echo Waiting 2s before restart...
    timeout /t 2 >nul
)

echo Starting on :%PORT%...
cd /d "%APP_DIR%"
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
