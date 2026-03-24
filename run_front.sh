#!/bin/bash
# gdep - 프론트엔드 개발 서버 실행 (macOS/Linux)
# 백엔드는 별도 터미널에서 ./run.sh 로 먼저 실행하세요.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/gdep-cli"
VENV="$CLI/.venv"

# vite 설치 여부 확인
if [ ! -f "$CLI/frontend/node_modules/.bin/vite" ]; then
    echo "[ERROR] 프론트엔드 의존성이 없습니다. 먼저 ./install.sh 를 실행하세요."
    exit 1
fi

echo "[GDEP Frontend] Starting Vite dev server on port 5173..."
echo "  백엔드가 실행 중인지 확인하세요: http://localhost:8000"
echo ""

cd "$CLI/frontend"
exec node_modules/.bin/vite