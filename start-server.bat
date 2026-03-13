@echo off
setlocal EnableDelayedExpansion
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
    echo   [!] Python is not installed or not in PATH.
    echo.
    set /p "INSTALL_PY=  Would you like to install Python automatically? [Y/N]: "
    if /i "!INSTALL_PY!"=="Y" (
        call :install_python
        if errorlevel 1 (
            echo.
            echo   [ERROR] Python installation failed.
            echo   Please install manually from https://www.python.org/downloads/
            echo.
            pause
            exit /b 1
        )
    ) else (
        echo.
        echo   Please install Python from https://www.python.org/downloads/
        echo   During install, check "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )
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
exit /b 0

:install_python
echo.
echo   Downloading Python installer...
echo.
set "PY_INSTALLER=%TEMP%\python-installer.exe"
set "PY_URL=https://www.python.org/ftp/python/3.13.2/python-3.13.2-amd64.exe"

:: Use curl.exe (built into Windows 10+) to download
C:\Windows\System32\curl.exe -L -o "%PY_INSTALLER%" "%PY_URL%" 2>&1
if not exist "%PY_INSTALLER%" (
    echo   [ERROR] Download failed. Check your internet connection.
    exit /b 1
)

echo.
echo   Installing Python 3.13.2 (this may take a minute)...
echo   Adding to PATH automatically.
echo.

:: Install silently, add to PATH, include pip and pythonw
"%PY_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
if errorlevel 1 (
    echo   [ERROR] Installer returned an error.
    del "%PY_INSTALLER%" >nul 2>nul
    exit /b 1
)

:: Clean up installer
del "%PY_INSTALLER%" >nul 2>nul

:: Refresh PATH for this session
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
set "PATH=%USER_PATH%;%PATH%"

:: Verify Python is now available
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo   [!] Python installed but not yet in PATH for this session.
    echo   Please close this window and double-click start-server.bat again.
    echo.
    pause
    exit /b 1
)

echo.
echo   [OK] Python installed successfully!
echo.
exit /b 0
