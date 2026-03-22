@echo off
chcp 65001 > nul
title GDEP Runner

echo [GDEP] Starting backend server...
start "GDEP Backend" cmd /k "cd /d %~dp0gdep-cli\backend && %~dp0gdep-cli\.venv\Scripts\python.exe -m uvicorn main:app --port 8000"

echo [GDEP] Waiting for backend...
timeout /t 2 /nobreak > nul

echo [GDEP] Starting frontend...
start "GDEP Frontend" cmd /k "cd /d %~dp0gdep-cli\frontend && node_modules\.bin\vite.cmd"

echo.
echo [GDEP] Done!
echo   Backend  : http://localhost:8000
echo   Frontend : http://localhost:5173
echo.
pause > nul
