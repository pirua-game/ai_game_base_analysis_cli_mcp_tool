"""
/api/unity
Unity 프리팹/씬 역참조 분석
"""
from __future__ import annotations
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.unity_refs import build_ref_map, find_assets_root

router = APIRouter()


@router.get("/refs")
def get_refs(path: str = Query(..., description="Scripts 경로")):
    """전체 역참조 맵 반환"""
    assets_root = find_assets_root(path)
    if assets_root is None:
        raise HTTPException(status_code=404,
                            detail="Assets 폴더를 찾을 수 없어요. Unity 프로젝트인지 확인해주세요.")

    ref_map = build_ref_map(path)
    if ref_map is None:
        raise HTTPException(status_code=500, detail="역참조 맵 빌드 실패")

    result = {}
    for cls, ref in ref_map.class_to_ref.items():
        if ref.usages:
            result[cls] = {
                "guid":    ref.guid,
                "prefabs": ref.prefabs,
                "scenes":  ref.scenes,
                "total":   ref.total,
            }

    return {
        "assets_root": str(ref_map.assets_root),
        "total_classes": len(ref_map.guid_to_class),
        "used_classes":  len(result),
        "refs": result,
    }


@router.get("/refs/{class_name}")
def get_class_refs(class_name: str, path: str = Query(...)):
    """특정 클래스의 역참조만 반환"""
    ref_map = build_ref_map(path)
    if ref_map is None:
        raise HTTPException(status_code=500, detail="역참조 맵 빌드 실패")

    ref = ref_map.get(class_name)
    if ref is None:
        raise HTTPException(status_code=404,
                            detail=f"`{class_name}` 클래스의 GUID를 찾을 수 없어요.")

    return {
        "class_name": class_name,
        "guid":       ref.guid,
        "prefabs":    ref.prefabs,
        "scenes":     ref.scenes,
        "total":      ref.total,
    }
