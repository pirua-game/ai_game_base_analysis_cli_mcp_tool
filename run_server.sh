#!/bin/bash
# gdep - 백엔드만 실행 (macOS/Linux) — CLI / MCP 용도

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/gdep-cli"
VENV="$CLI/.venv"
PYTHON="$VENV/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "[ERROR] 설치가 필요합니다. 먼저 ./install.sh 를 실행하세요."
    exit 1
fi

echo "[GDEP Backend] uvicorn 시작 중 (포트 8000)..."
cd "$CLI/backend"
exec "$PYTHON" -m uvicorn main:app --port 8000
