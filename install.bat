@echo off
chcp 65001 > nul
title GDEP Installer

echo.
echo  ╔══════════════════════════════════════╗
echo  ║         gdep  Installer              ║
echo  ║  Game Codebase Analysis Tool         ║
echo  ╚══════════════════════════════════════╝
echo.

set ROOT=%~dp0
set CLI=%ROOT%gdep-cli
set VENV=%CLI%\.venv

:: ── 1. Python 확인 ──────────────────────────────────────────
echo [1/5] Python 확인...
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.11+ 이 설치되어 있지 않습니다.
    echo          https://python.org 에서 설치 후 다시 실행하세요.
    goto :fail
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

:: ── 2. .NET Runtime 확인 ────────────────────────────────────
echo [2/5] .NET Runtime 확인...
dotnet --version > nul 2>&1
if errorlevel 1 (
    echo  [WARN] .NET 8.0+ 이 없습니다. C# / Unity 분석 기능이 제한됩니다.
    echo         https://dotnet.microsoft.com/download 에서 설치 권장
) else (
    for /f %%v in ('dotnet --version 2^>^&1') do set DOTNETVER=%%v
    echo  [OK] .NET %DOTNETVER%
)

:: ── 3. Node.js 확인 ─────────────────────────────────────────
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

:: ── 4. Python venv + pip install ────────────────────────────
echo [4/5] Python 패키지 설치...

if not exist "%VENV%" (
    echo  가상환경 생성 중...
    python -m venv "%VENV%"
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

:: ── 5. Node.js 프론트엔드 의존성 ─────────────────────────────
echo [5/5] 프론트엔드 의존성 설치...
if "%NODE_OK%"=="1" (
    if not exist "%CLI%\frontend\node_modules\.bin\vite.cmd" (
        echo  npm install 실행 중 (최초 1회)...
        pushd "%CLI%\frontend"
        call npm install --silent
        popd
        if errorlevel 1 ( echo  [WARN] npm install 실패 - Web UI 를 사용하지 않으면 무시 가능 )
    ) else (
        echo  [OK] node_modules 이미 존재 - 스킵
    )
) else (
    echo  [SKIP] Node.js 없음 - Web UI 설치 생략
)

:: ── 완료 ────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════╗
echo  ║          설치 완료!                  ║
echo  ╚══════════════════════════════════════╝
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
echo          "command": "%VENV:\=/%/Scripts/python.exe",
echo          "args": ["%ROOT:\=/%gdep-cli/gdep-mcp/server.py"],
echo          "cwd": "%CLI:\=/%"
echo        }
echo      }
echo    }
echo.
pause
goto :eof

:fail
echo.
echo  [FAIL] 설치 중 오류가 발생했습니다. 위 오류 메시지를 확인하세요.
echo.
pause
exit /b 1
