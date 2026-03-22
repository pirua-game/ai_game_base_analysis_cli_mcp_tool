@echo off
chcp 65001 > nul
title GDEP Backend

echo [GDEP Backend] Starting uvicorn on port 8000...
cd /d %~dp0gdep-cli\backend
%~dp0gdep-cli\.venv\Scripts\python.exe -m uvicorn main:app --port 8000

pause
