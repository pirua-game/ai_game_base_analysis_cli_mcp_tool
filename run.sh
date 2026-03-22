#!/bin/bash
# gdep - 백엔드 서버 실행 (macOS/Linux)
# 프론트엔드는 별도 터미널에서 ./run_frontend.sh 로 실행하세요.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/gdep-cli"
VENV="$CLI/.venv"
PYTHON="$VENV/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "[ERROR] 설치가 필요합니다. 먼저 ./install.sh 를 실행하세요."
    exit 1
fi

echo "[GDEP Backend] Starting uvicorn on port 8000..."
echo "  프론트엔드는 별도 터미널에서: ./run_frontend.sh"
echo ""

cd "$CLI/backend"
exec "$PYTHON" -m uvicorn main:app --port 8000
