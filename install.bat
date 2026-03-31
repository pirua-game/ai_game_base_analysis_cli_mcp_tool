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
echo [1/5] Python 확인...
py -3.11 --version > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.11 이 설치되어 있지 않습니다.
    echo          https://python.org 에서 설치 후 다시 실행하세요.
    goto :fail
)
for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

REM -- 2. .NET Runtime check --
echo [2/5] .NET Runtime 확인...
dotnet --version > nul 2>&1
if errorlevel 1 (
    echo  [WARN] .NET 8.0+ 이 없습니다. C# / Unity 분석 기능이 제한됩니다.
    echo         https://dotnet.microsoft.com/download 에서 설치 권장
) else (
    for /f %%v in ('dotnet --version 2^>^&1') do set DOTNETVER=%%v
    echo  [OK] .NET %DOTNETVER%
)

REM -- 3. Node.js check --
echo [3/5] Node.js 확인...
node --version > nul 2>&1
if errorlevel 1 (
    echo  [WARN] Node.js 18+ 이 없습니다. Web UI 를 사용하려면 설치하세요.
    echo         https://nodejs.org 에서 설치 권장
    set NODE_OK=0
) else (
    for /f %%v in ('node --version 2^>^&1') do set NODEVER=%%v
    echo  [OK] Node.js %NODEVER%
    set NODE_OK=1
)

REM -- 4. Python venv + pip install --
echo [4/5] Python 패키지 설치...

if not exist "%VENV%" (
    echo  가상환경 생성 중...
    py -3.11 -m venv "%VENV%"
    if errorlevel 1 ( echo  [ERROR] venv 생성 실패 & goto :fail )
)

echo  gdep 패키지 설치 중...
"%VENV%\Scripts\pip.exe" install -e "%CLI%" --quiet
if errorlevel 1 ( echo  [ERROR] pip install 실패 & goto :fail )

echo  추가 의존성 설치 중...
"%VENV%\Scripts\pip.exe" install -r "%CLI%\requirements.txt" --quiet

echo  MCP 패키지 설치 중...
"%VENV%\Scripts\pip.exe" install "mcp[cli]>=1.0" --quiet

echo  [OK] Python 패키지 완료

REM -- 5. Node.js frontend dependencies --
echo [5/5] 프론트엔드 의존성 설치...
if not "%NODE_OK%"=="1" goto :skip_npm

pushd "%CLI%\web\frontend"
if exist "node_modules\vite" goto :npm_exists

echo  npm install 실행 중 (최초 1회)...
call npm install
if not errorlevel 1 goto :npm_done

echo  [WARN] npm install 실패 - node.exe 종료 후 재시도...
taskkill /f /im node.exe > nul 2>&1
timeout /t 2 /nobreak > nul
call npm install
if errorlevel 1 echo  [WARN] npm install 최종 실패 - Web UI 를 사용하지 않으면 무시 가능
goto :npm_done

:npm_exists
echo  [OK] node_modules 이미 존재 - 스킵

:npm_done
popd
goto :install_done

:skip_npm
echo  [SKIP] Node.js 없음 - Web UI 설치 생략

:install_done

REM -- Done --
echo.
echo  ===================================
echo           설치 완료!
echo  ===================================
echo.
echo  다음 명령어로 시작하세요:
echo.
echo    run.bat          ^<-- 백엔드 + Web UI 동시 실행
echo    run_server.bat   ^<-- 백엔드만 실행 (CLI / MCP 용도)
echo.
echo  CLI 사용 예시:
echo    %VENV%\Scripts\gdep.exe detect D:\MyGame\Assets\Scripts
echo    %VENV%\Scripts\gdep.exe scan   D:\MyGame\Assets\Scripts
echo.
echo  Claude Desktop MCP 설정 파일 위치:
echo    %%APPDATA%%\Claude\claude_desktop_config.json
echo.
echo  설정 내용:
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
    echo  [INFO] 설치 경로에 공백이 포함되어 있어 8.3 단축 경로를 사용합니다.
    echo         문제가 지속되면 공백 없는 경로로 이동하세요.
    echo.
)
pause
goto :eof

:fail
echo.
echo  [FAIL] 설치 중 오류가 발생했습니다. 위 오류 메시지를 확인하세요.
echo.
pause
exit /b 1
