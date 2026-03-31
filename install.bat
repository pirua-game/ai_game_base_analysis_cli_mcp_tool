@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
title GDEP Installer

echo.
echo  ===================================
echo         gdep  Installer
echo    Game Codebase Analysis Tool
echo  ===================================
echo.

set ROOT=%~dp0
set CLI=%ROOT%gdep-cli
set VENV=%CLI%\.venv

REM -- Short path conversion for paths with spaces (MCP config) --
for %%I in ("%VENV%\Scripts\python.exe") do set "VENV_PYTHON_SHORT=%%~sI"
for %%I in ("%ROOT%gdep-cli\gdep_mcp\server.py") do set "SERVER_SHORT=%%~sI"
for %%I in ("%CLI%") do set "CLI_SHORT=%%~sI"

REM -- 1. Python check --
echo [1/5] Checking Python...
py -3.11 --version > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.11 is not installed.
    echo          Please install it from https://python.org and run again.
    goto :fail
)
for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

REM -- 2. .NET Runtime check --
echo [2/5] Checking .NET Runtime...
dotnet --version > nul 2>&1
if errorlevel 1 (
    echo  [WARN] .NET 8.0+ not found. C# / Unity analysis will be limited.
    echo         Install from: https://dotnet.microsoft.com/download
) else (
    for /f %%v in ('dotnet --version 2^>^&1') do set DOTNETVER=%%v
    echo  [OK] .NET %DOTNETVER%
)

REM -- 3. Node.js check --
echo [3/5] Checking Node.js...
node --version > nul 2>&1
if errorlevel 1 (
    echo  [WARN] Node.js 18+ not found. Required for Web UI.
    echo         Install from: https://nodejs.org
    set NODE_OK=0
) else (
    for /f %%v in ('node --version 2^>^&1') do set NODEVER=%%v
    echo  [OK] Node.js %NODEVER%
    set NODE_OK=1
)

REM -- 4. Python venv + pip install --
echo [4/5] Installing Python packages...

if not exist "%VENV%" (
    echo  Creating virtual environment...
    py -3.11 -m venv "%VENV%"
    if errorlevel 1 ( echo  [ERROR] Failed to create venv & goto :fail )
)

echo  Installing gdep package...
"%VENV%\Scripts\pip.exe" install -e "%CLI%" --quiet
if errorlevel 1 ( echo  [ERROR] pip install failed & goto :fail )

echo  Installing additional dependencies...
"%VENV%\Scripts\pip.exe" install -r "%CLI%\requirements.txt" --quiet

echo  Installing MCP package...
"%VENV%\Scripts\pip.exe" install "mcp[cli]>=1.0" --quiet

echo  [OK] Python packages installed

REM -- 5. Node.js frontend dependencies --
echo [5/5] Installing frontend dependencies...
if not "%NODE_OK%"=="1" goto :skip_npm

pushd "%CLI%\web\frontend"
if exist "node_modules\vite" goto :npm_exists

echo  Running npm install (first time only)...
call npm install
if not errorlevel 1 goto :npm_done

echo  [WARN] npm install failed - retrying after killing node.exe...
taskkill /f /im node.exe > nul 2>&1
timeout /t 2 /nobreak > nul
call npm install
if errorlevel 1 echo  [WARN] npm install failed - safe to ignore if not using Web UI
goto :npm_done

:npm_exists
echo  [OK] node_modules already exists - skipping

:npm_done
popd
goto :install_done

:skip_npm
echo  [SKIP] Node.js not found - skipping Web UI install

:install_done

REM -- Done --
echo.
echo  ===================================
echo           Installation complete!
echo  ===================================
echo.
echo  To get started:
echo.
echo    run.bat          ^<-- Start backend + Web UI
echo    run_server.bat   ^<-- Start backend only (CLI / MCP)
echo.
echo  CLI examples:
echo    %VENV%\Scripts\gdep.exe detect D:\MyGame\Assets\Scripts
echo    %VENV%\Scripts\gdep.exe scan   D:\MyGame\Assets\Scripts
echo.
echo  Claude Desktop MCP config location:
echo    %%APPDATA%%\Claude\claude_desktop_config.json
echo.
echo  MCP config:
echo    {
echo      "mcpServers": {
echo        "gdep": {
echo          "command": "!VENV_PYTHON_SHORT:\=/!",
echo          "args": ["!SERVER_SHORT:\=/!"],
echo          "cwd": "!CLI_SHORT:\=/!"
echo        }
echo      }
echo    }
echo.
echo !ROOT! | findstr " " > nul
if not errorlevel 1 (
    echo  [INFO] Install path contains spaces. Using 8.3 short paths for MCP config.
    echo         If issues persist, move gdep to a path without spaces.
    echo.
)
pause
goto :eof

:fail
echo.
echo  [FAIL] Installation failed. See error messages above.
echo.
pause
exit /b 1
