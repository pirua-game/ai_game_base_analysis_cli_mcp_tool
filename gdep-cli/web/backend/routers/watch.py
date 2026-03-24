"""
gdep WebSocket watch router — 실시간 파일 변경 감지 + 분석 스트리밍.

연결 흐름:
  1. 클라이언트 → {"action": "start", "path": "...", ...}
  2. 서버  → {"type": "connected", "engine": "...", ...}
  3. 파일 변경 시 → changed / impact / test_scope / lint / done 메시지 순차 전송
  4. 클라이언트 → {"action": "stop"}  또는 연결 해제
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time as _time
import datetime as _dt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Python 패키지 경로 보장
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.detector import detect
from gdep import runner

router = APIRouter()

_SRC_EXTS = {".cs", ".cpp", ".h", ".hpp"}


async def _send(ws: WebSocket, msg: dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))
    except Exception:
        pass


@router.websocket("/watch")
async def ws_watch(websocket: WebSocket):
    await websocket.accept()

    observer = None
    pending_timer: list[threading.Timer | None] = [None]
    loop = asyncio.get_event_loop()

    try:
        # ── 1. 시작 메시지 수신 ──────────────────────────────────
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        msg = json.loads(raw)

        if msg.get("action") != "start":
            await _send(websocket, {"type": "error", "message": "Expected {action: 'start'}"})
            return

        path         = msg.get("path", ".")
        target_class = msg.get("target_class") or None
        depth        = int(msg.get("depth", 3))
        debounce     = float(msg.get("debounce", 1.0))

        # ── 2. 프로젝트 감지 ─────────────────────────────────────
        try:
            profile = detect(path)
        except Exception as e:
            await _send(websocket, {"type": "error", "message": f"프로젝트 감지 실패: {e}"})
            return

        resolved = str(Path(path).resolve())

        await _send(websocket, {
            "type":         "connected",
            "path":         resolved,
            "engine":       profile.display,
            "debounce":     debounce,
            "depth":        depth,
            "target_class": target_class,
        })

        # ── 3. 분석 함수 (워커 스레드에서 실행) ──────────────────
        def _run_analysis(cls_name: str, changed_file: str) -> None:
            t0  = _time.time()
            now = _dt.datetime.now().strftime("%H:%M:%S")

            def _emit(payload: dict) -> None:
                asyncio.run_coroutine_threadsafe(_send(websocket, payload), loop)

            _emit({"type": "changed", "file": Path(changed_file).name,
                   "class": cls_name, "timestamp": now})

            # impact
            impact_result = runner.impact(profile, cls_name, depth=depth)
            affected_count = 0
            if impact_result.ok:
                affected_count = sum(
                    1 for ln in impact_result.stdout.splitlines()
                    if ln.strip().startswith(("├", "└", "│")) and ln.strip()
                )
            _emit({
                "type":    "impact",
                "class":   cls_name,
                "count":   affected_count,
                "ok":      impact_result.ok,
                "output":  impact_result.stdout[:1500] if impact_result.ok else impact_result.stderr,
            })

            # test_scope
            ts_result  = runner.test_scope(profile, cls_name, depth=depth, fmt="json")
            test_count = 0
            test_files: list[str] = []
            if ts_result.ok:
                try:
                    ts_data    = json.loads(ts_result.stdout)
                    test_count = ts_data.get("test_file_count", 0)
                    raw_files  = ts_data.get("test_files", [])
                    test_files = [
                        (f.get("file", str(f)) if isinstance(f, dict) else str(f))
                        for f in raw_files[:10]
                    ]
                except Exception:
                    pass
            _emit({"type": "test_scope", "count": test_count,
                   "files": test_files, "ok": ts_result.ok})

            # lint
            lint_result   = runner.lint(profile, fmt="json")
            lint_errors   = 0
            lint_warnings = 0
            lint_cycles   = 0
            first_error   = ""
            lint_items: list[dict] = []
            if lint_result.ok:
                issues = lint_result.data or []
                lint_cycles   = sum(1 for i in issues
                                    if isinstance(i, dict) and i.get("rule_id") == "GEN-ARCH-001")
                lint_errors   = sum(1 for i in issues
                                    if isinstance(i, dict) and i.get("severity") == "Error"
                                    and i.get("rule_id") != "GEN-ARCH-001")
                lint_warnings = sum(1 for i in issues
                                    if isinstance(i, dict) and i.get("severity") == "Warning")
                err_items = [i for i in issues
                             if isinstance(i, dict) and i.get("severity") == "Error"
                             and i.get("rule_id") != "GEN-ARCH-001"]
                first_error = err_items[0].get("rule_id", "") if err_items else ""
                # 상세 아이템 — 경고/오류 규칙 목록 (최대 20개, 순환참조 제외)
                lint_items = [
                    {
                        "rule_id":  i.get("rule_id", ""),
                        "severity": i.get("severity", ""),
                        "message":  (i.get("message") or "")[:150],
                        "class":    i.get("class_name") or i.get("class") or "",
                    }
                    for i in issues
                    if isinstance(i, dict) and i.get("rule_id") != "GEN-ARCH-001"
                ][:20]
            _emit({
                "type":             "lint",
                "errors":           lint_errors,
                "warnings":         lint_warnings,
                "cycles":           lint_cycles,
                "first_error_rule": first_error,
                "items":            lint_items,
                "ok":               lint_result.ok,
            })

            _emit({"type": "done", "elapsed": round(_time.time() - t0, 2)})

        def _schedule(cls_name: str, changed_file: str) -> None:
            if pending_timer[0] is not None:
                pending_timer[0].cancel()
            t = threading.Timer(debounce, _run_analysis, args=[cls_name, changed_file])
            pending_timer[0] = t
            t.start()

        # ── 4. watchdog 시작 ──────────────────────────────────────
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            await _send(websocket, {
                "type":    "error",
                "message": "watchdog 미설치. pip install watchdog 후 서버 재시작 필요.",
            })
            return

        class _ChangeHandler(FileSystemEventHandler):
            def _handle(self, event) -> None:
                if event.is_directory:
                    return
                p = Path(event.src_path)
                if p.suffix.lower() not in _SRC_EXTS:
                    return
                cls_name = p.stem.split("@")[0].split(".")[0]
                if not cls_name:
                    return
                if target_class and cls_name.lower() != target_class.lower():
                    return
                _schedule(cls_name, str(p))

            on_modified = _handle
            on_created  = _handle

        observer = Observer()
        observer.schedule(_ChangeHandler(), resolved, recursive=True)
        observer.start()

        # ── 5. 연결 유지 — stop 또는 disconnect 대기 ─────────────
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(raw)
                if data.get("action") == "stop":
                    break
            except asyncio.TimeoutError:
                await _send(websocket, {"type": "heartbeat"})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await _send(websocket, {"type": "error", "message": "연결 타임아웃"})
    except Exception as e:
        try:
            await _send(websocket, {"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if pending_timer[0] is not None:
            pending_timer[0].cancel()
        if observer is not None:
            observer.stop()
            observer.join()
