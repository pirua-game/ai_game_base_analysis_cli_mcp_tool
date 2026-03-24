"""
/api/ue5
UE5 블루프린트 역참조 + Blueprint↔C++ 매핑 분석
"""
from __future__ import annotations
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

router = APIRouter()


@router.get("/blueprint_refs")
def get_blueprint_refs(path: str = Query(...)):
    """전체 블루프린트 역참조 맵 반환"""
    from gdep.ue5_blueprint_refs import build_ref_map, find_content_root, ref_map_to_dict

    content_root = find_content_root(path)
    if content_root is None:
        raise HTTPException(
            status_code=404,
            detail="Content 폴더를 찾을 수 없어요. UE5 프로젝트 경로인지 확인해주세요."
        )

    ref_map = build_ref_map(path)
    if ref_map is None:
        raise HTTPException(status_code=500, detail="블루프린트 역참조 맵 빌드 실패")

    result = ref_map_to_dict(ref_map)

    return {
        "content_root":  str(ref_map.content_root),
        "module_name":   ref_map.module_name,
        "total_classes": len(result),
        "refs":          result,
    }


@router.get("/blueprint_refs/{class_name}")
def get_class_blueprint_refs(class_name: str, path: str = Query(...)):
    """특정 클래스의 블루프린트 역참조 반환 (접두사 정규화 포함)"""
    from gdep.ue5_blueprint_refs import build_ref_map

    ref_map = build_ref_map(path)
    if ref_map is None:
        raise HTTPException(status_code=500, detail="역참조 맵 빌드 실패")

    # get()이 접두사 정규화 처리
    ref = ref_map.get(class_name)

    if ref is None or not ref.usages:
        return {
            "class_name":  class_name,
            "blueprints":  [],
            "maps":        [],
            "total":       0,
            "module_name": ref_map.module_name,
        }

    return {
        "class_name":  class_name,
        "blueprints":  ref.blueprints,
        "maps":        ref.maps,
        "total":       ref.total,
        "module_name": ref.module_name,
    }


@router.get("/blueprint_mapping")
def get_blueprint_mapping(
    path: str = Query(..., description="UE5 Source 경로"),
    cpp_class: str = Query(None, description="특정 C++ 클래스명 (없으면 전체)"),
):
    """C++ 클래스 → Blueprint 구현체 매핑 반환. LFS 포인터 프로젝트는 파일명 기반 목록 제공."""
    from gdep.ue5_blueprint_mapping import (
        build_bp_map, format_full_project_map, format_cpp_to_bps,
        _build_lfs_fallback,
    )

    try:
        bp_map = build_bp_map(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BP 매핑 빌드 실패: {e}")

    # LFS 포인터 전용 프로젝트 — 파일명 기반 fallback
    if not bp_map.blueprints:
        try:
            text = _build_lfs_fallback(path, cpp_class)
        except Exception:
            text = "Blueprint 구현체를 찾을 수 없습니다. Content 폴더의 .uasset이 Git LFS 포인터만 있거나 프로젝트 모듈 이름이 감지되지 않았습니다."
        return {"result": text, "total": 0, "lfs_mode": True}

    if cpp_class:
        # format_cpp_to_bps(cpp_class, bps) 시그니처
        candidates = [cpp_class]
        for prefix in ('A', 'U', 'F', 'I', 'E'):
            if cpp_class.startswith(prefix):
                candidates.append(cpp_class[1:])
            else:
                candidates.append(prefix + cpp_class)
        from gdep.ue5_blueprint_mapping import BlueprintMapping
        bps: list[BlueprintMapping] = []
        seen: set[str] = set()
        for c in candidates:
            for m in bp_map.cpp_to_bps.get(c, []):
                if m.bp_class not in seen:
                    seen.add(m.bp_class)
                    bps.append(m)
        text = format_cpp_to_bps(cpp_class, bps)
    else:
        text = format_full_project_map(bp_map)

    return {"result": text, "total": len(bp_map.blueprints)}