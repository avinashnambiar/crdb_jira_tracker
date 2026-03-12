@echo off
title CRDB Status Tracker Server
echo ============================================
echo   CRDB Status Tracker
echo ============================================
echo.

:: Change to the script's directory first
cd /d "%~dp0"

:: Check if Python is installed
where python >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Python is not installed or not in PATH.
    echo.
    echo   Please install Python from https://www.python.org/downloads/
    echo   During install, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

:: Check if server.py exists
if not exist "server.py" (
    echo   [ERROR] server.py not found in this folder.
    echo   Make sure server.py is in the same folder as this bat file.
    echo.
    pause
    exit /b 1
)

:: Kill any existing process on port 8091
echo   Checking port 8091...
netstat -ano | findstr ":8091 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo   Port 8091 in use, attempting to free it...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8091 " ^| findstr "LISTENING"') do (
        taskkill /PID %%a /F >nul 2>nul
    )
    timeout /t 2 /nobreak >nul
)

:: Get local IP address
set IP=localhost
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "IP=%%a"
    goto :found
)
:found
set "IP=%IP: =%"

echo.
echo   Local:   http://localhost:8091/crdbtracker.html
echo   Network: http://%IP%:8091/crdbtracker.html
echo.
echo   Share the Network URL with your team!
echo   Press Ctrl+C to stop the server.
echo ============================================
echo.

:: Auto-open browser after a short delay
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8091/crdbtracker.html"

python server.py

echo.
echo   Server stopped.
echo.
pause
