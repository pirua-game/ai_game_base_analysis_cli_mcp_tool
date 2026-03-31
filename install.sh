#!/bin/bash
# gdep installer for macOS/Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/gdep-cli"
VENV="$CLI/.venv"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         gdep  Installer              ║"
echo "  ║  Game Codebase Analysis Tool         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Python 확인 ──────────────────────────────────────────
echo "[1/5] Python 확인..."
if command -v python3 &>/dev/null; then
    PYVER=$(python3 --version 2>&1)
    echo "  [OK] $PYVER"
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYVER=$(python --version 2>&1)
    echo "  [OK] $PYVER"
    PYTHON=python
else
    echo "  [ERROR] Python 3.11+ 이 설치되어 있지 않습니다."
    echo "          https://python.org 또는 'brew install python' 으로 설치하세요."
    exit 1
fi

# ── 2. .NET Runtime 확인 ────────────────────────────────────
echo "[2/5] .NET Runtime 확인..."
if command -v dotnet &>/dev/null; then
    DOTNETVER=$(dotnet --version 2>&1)
    echo "  [OK] .NET $DOTNETVER"
else
    echo "  [WARN] .NET 8.0+ 이 없습니다. C# / Unity 분석 기능이 제한됩니다."
    echo "         https://dotnet.microsoft.com/download 에서 설치 권장"
fi

# ── 3. Node.js 확인 ─────────────────────────────────────────
echo "[3/5] Node.js 확인..."
if command -v node &>/dev/null; then
    NODEVER=$(node --version 2>&1)
    echo "  [OK] Node.js $NODEVER"
    NODE_OK=1
else
    echo "  [WARN] Node.js 18+ 이 없습니다. Web UI 를 사용하려면 설치하세요."
    echo "         https://nodejs.org 또는 'brew install node' 으로 설치"
    NODE_OK=0
fi

# ── 4. Python venv + pip install ────────────────────────────
echo "[4/5] Python 패키지 설치..."

if [ ! -d "$VENV" ]; then
    echo "  가상환경 생성 중..."
    $PYTHON -m venv "$VENV"
fi

echo "  gdep 패키지 설치 중..."
"$VENV/bin/pip" install -e "$CLI" --quiet

echo "  추가 의존성 설치 중..."
"$VENV/bin/pip" install -r "$CLI/requirements.txt" --quiet

echo "  MCP 패키지 설치 중..."
"$VENV/bin/pip" install "mcp[cli]>=1.0" --quiet

echo "  [OK] Python 패키지 완료"

# ── 5. Node.js 프론트엔드 의존성 ─────────────────────────────
echo "[5/5] 프론트엔드 의존성 설치..."
if [ "$NODE_OK" -eq 1 ]; then
    if [ ! -f "$CLI/web/frontend/node_modules/.bin/vite" ]; then
        echo "  npm install 실행 중 (최초 1회)..."
        NPM_CACHE=$(npm config get cache 2>/dev/null || echo "$HOME/.npm")
        if [ -d "$NPM_CACHE" ] && [ ! -w "$NPM_CACHE" ]; then
            echo "  npm 캐시 권한 수정 중... (sudo 필요)"
            sudo chown -R "$(whoami)" "$NPM_CACHE"
        fi
        cd "$CLI/web/frontend" && npm install --include=dev 2>&1 && cd "$SCRIPT_DIR"
        if [ $? -ne 0 ]; then
            echo "  [WARN] npm install 실패 - Web UI 를 사용하지 않으면 무시 가능"
        fi
    else
        echo "  [OK] node_modules 이미 존재 - 스킵"
    fi
else
    echo "  [SKIP] Node.js 없음 - Web UI 설치 생략"
fi

# ── 완료 ────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║          설치 완료!                  ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  다음 명령어로 시작하세요 (터미널 2개 필요):"
echo ""
echo "  터미널 1:  ./run.sh             <-- 백엔드 서버 (포트 8000)"
echo "  터미널 2:  ./run_frontend.sh    <-- 프론트엔드 (포트 5173)"
echo ""
echo "  또는 CLI / MCP 전용:"
echo "    ./run.sh (백엔드만 실행 후 MCP 사용)"
echo ""
echo "  CLI 사용 예시:"
echo "    $VENV/bin/gdep detect /path/to/MyGame/Assets/Scripts"
echo "    $VENV/bin/gdep scan   /path/to/MyGame/Assets/Scripts"
echo ""
echo "  Claude Desktop MCP 설정 파일 위치:"
echo "    ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "  설정 내용:"
echo "    {"
echo "      \"mcpServers\": {"
echo "        \"gdep\": {"
echo "          \"command\": \"$VENV/bin/python\","
echo "          \"args\": [\"$SCRIPT_DIR/gdep-cli/gdep_mcp/server.py\"],"
echo "          \"cwd\": \"$CLI\""
echo "        }"
echo "      }"
echo "    }"
echo ""
