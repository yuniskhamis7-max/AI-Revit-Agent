@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  Revit AI Agent — Development Launcher
REM  
REM  Stops any existing backend/frontend processes, then launches both
REM  the FastAPI backend (port 8000) and Vite dev server (port 5173).
REM  
REM  Usage:  Double-click this file, or run from terminal:  run.bat
REM ─────────────────────────────────────────────────────────────────────────
title Revit AI Agent — Launcher
color 0A

echo.
echo ================================================================
echo   Revit AI Agent — Stopping existing processes...
echo ================================================================
echo.

REM Kill backend by port 8000
echo   Stopping backend (port 8000)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /F /FI "WINDOWTITLE eq Revit AI Backend*" >nul 2>&1

REM Kill frontend by port 5173
echo   Stopping frontend (port 5173)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /F /FI "WINDOWTITLE eq Revit AI Frontend*" >nul 2>&1

timeout /t 2 /nobreak >nul

echo.
echo ================================================================
echo   Revit AI Agent — Starting servers...
echo ================================================================
echo.

REM Get the directory where this script lives
set "SCRIPT_DIR=%~dp0"

REM Start the backend in a new window
echo   [1/2] Starting backend (port 8000)...
start "Revit AI Backend" cmd /k "cd /d %SCRIPT_DIR%backend && %SCRIPT_DIR%.venv\Scripts\python.exe main.py"

REM Wait for backend to initialize
echo   Waiting for backend to be ready...
timeout /t 5 /nobreak >nul

REM Start the frontend dev server in a new window
echo   [2/2] Starting frontend dev server (port 5173)...
start "Revit AI Frontend" cmd /k "cd /d %SCRIPT_DIR%frontend && npm run dev"

REM Wait for Vite to start
timeout /t 3 /nobreak >nul

echo.
echo ================================================================
echo   Revit AI Agent — All servers running!
echo ================================================================
echo.
echo   Backend:   http://localhost:8000
echo   Frontend:  http://localhost:5173  (open this in your browser)
echo.
echo   Close the Backend and Frontend windows to stop the servers.
echo   Or re-run this script to restart everything cleanly.
echo ================================================================
echo.

REM Open browser to the frontend
start http://localhost:5173

pause
