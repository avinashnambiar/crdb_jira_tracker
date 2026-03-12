@echo off
title CRDB Status Tracker Server
echo ============================================
echo   CRDB Status Tracker
echo ============================================
echo.

:: Get machine hostname and IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo   Local:   http://localhost:8091
echo   Network: http://%IP%:8091
echo.
echo   Share the Network URL with your team!
echo   Press Ctrl+C to stop the server.
echo ============================================
echo.

:: Auto-open browser after a short delay
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8091/crdbtracker.html"

python server.py
pause
