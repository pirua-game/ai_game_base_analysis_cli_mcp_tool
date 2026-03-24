"""
/api/flow
메서드 호출 흐름 분석
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.detector import detect, ProjectKind
from gdep import runner

router = APIRouter()


class FlowRequest(BaseModel):
    path:          str
    class_name:    str
    method_name:   str
    depth:         int       = 3
    focus_classes: list[str] = []


@router.post("/analyze")
def analyze_flow(req: FlowRequest):
    """메서드 호출 흐름 분석 → JSON 반환"""
    try:
        profile = detect(req.path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── UE5 전용 flow 분석 ──────────────────────────────────────
    if profile.kind == ProjectKind.UNREAL:
        try:
            from gdep.ue5_flow import flow_to_json
            src = str(profile.source_dirs[0]) if profile.source_dirs else req.path
            data = flow_to_json(
                src,
                req.class_name,
                req.method_name,
                max_depth=req.depth,
                focus_classes=req.focus_classes or None,
            )
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── C# / C++ 기존 flow 분석 ───────────────────────────────
    result = runner.flow(
        profile,
        class_name=req.class_name,
        method_name=req.method_name,
        depth=req.depth,
        focus_classes=req.focus_classes or None,
        fmt="json",
    )

    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)

    if result.data:
        return result.data

    stdout = result.stdout
    j = stdout.find("{")
    if j == -1:
        raise HTTPException(status_code=500, detail="JSON 출력을 파싱할 수 없어요.")
    try:
        s = stdout[j:]
        return json.loads(s[:s.rfind("}") + 1])
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON 파싱 오류: {e}")