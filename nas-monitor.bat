@echo off
chcp 65001 >nul
setlocal

set APP_DIR=%~dp0
set PORT=8900
set VENV_DIR=%APP_DIR%venv

echo === NAS Monitor ===

if "%1"=="stop" goto :stop
if "%1"=="restart" goto :stop_start
goto :start

:start
    echo [1/2] ...
    if not exist "%VENV_DIR%\Scripts\python.exe" (
        echo venv not found: python -m venv venv
        exit /b 1
    )

    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8900.*LISTENING" 2^>nul') do (
        echo Stopping old: PID=%%a...
        taskkill /F /PID %%a 2>nul
        timeout /t 1 >nul
    )

    echo [2/2] Starting on :%PORT%...
    cd /d "%APP_DIR%"
    "%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% > "%APP_DIR%nas-monitor.log" 2>&1 &

    echo OK: http://localhost:%PORT%
    echo Log: %APP_DIR%nas-monitor.log
    echo Stop: nas-monitor.bat stop
    goto :eof

:stop
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8900.*LISTENING" 2^>nul') do (
        taskkill /F /PID %%a 2>nul
    )
    echo Stopped
    goto :eof

:stop_start
    call :stop
    timeout /t 1 >nul
    call :start
    goto :eof
