@echo off
setlocal EnableDelayedExpansion
title ClauseGuard

:: PROJECT_DIR = folder where start.bat lives
set "PROJECT_DIR=%~dp0"

cd /d "%PROJECT_DIR%"

echo.
echo  ----------------------------------------
echo    ClauseGuard - Starting up...
echo  ----------------------------------------
echo.

:: Check for .env in the ROOT folder
if not exist "%PROJECT_DIR%.env" (
    echo ERROR: .env file not found in:
    echo   %PROJECT_DIR%
    echo.
    pause
    exit /b 1
)

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    pause
    exit /b 1
)

:: Check Node
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found.
    pause
    exit /b 1
)

:: Check venv
if not exist "%PROJECT_DIR%.venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv "%PROJECT_DIR%.venv"
)

echo Upgrading pip...
"%PROJECT_DIR%.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo Installing Python dependencies...
"%PROJECT_DIR%.venv\Scripts\pip.exe" install -r "%PROJECT_DIR%requirements.txt"

echo Installing Node dependencies...
cd /d "%PROJECT_DIR%frontend"
call npm install --silent
cd /d "%PROJECT_DIR%"

echo.
echo  ----------------------------------------
echo    Backend  >  http://localhost:8000
echo    Frontend >  http://localhost:3000
echo  ----------------------------------------
echo.

:: Start backend (absolute venv path, no quotes inside)
start "Clauseguard Backend" /d "%PROJECT_DIR%" cmd /k call %PROJECT_DIR%.venv\Scripts\activate.bat ^&^& uvicorn backend.main:app --reload --port 8000

timeout /t 2 /nobreak >nul

:: Start frontend
start "Clauseguard Frontend" /d "%PROJECT_DIR%frontend" cmd /k npm run dev

echo Both servers are starting in separate windows.
pause
