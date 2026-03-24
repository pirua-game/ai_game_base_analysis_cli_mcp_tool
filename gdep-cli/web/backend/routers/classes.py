"""
/api/classes
클래스 목록 파싱 (C# / C++ / UE5)
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.detector import detect, ProjectKind

router = APIRouter()


def _parse_cs(scripts_path: str) -> dict:
    result = {}
    root   = Path(scripts_path)
    if not root.exists(): return result

    type_pat = re.compile(
        r'(?:public|internal|private|protected)?\s*'
        r'(?:partial\s+)?(?:abstract\s+|sealed\s+|static\s+)?'
        r'(class|struct|interface)\s+(\w+)(?:\s*:\s*([^\{]+))?'
    )
    field_pat = re.compile(
        r'(public|private|protected|internal)\s+(?:static\s+|readonly\s+|const\s+)*'
        r'([\w<>\[\],\s\?]+?)\s+(\w+)\s*(?:=>|[;={])'
    )
    method_pat = re.compile(
        r'(public|private|protected|internal)\s+'
        r'((?:static\s+)?(?:virtual\s+)?(?:override\s+)?(?:async\s+)?)'
        r'([\w<>\[\],\s\?\.]+?)\s+(\w+)\s*\(([^)]*)\)'
    )

    for f in list(root.rglob("*.cs"))[:800]:
        if "_PROTO" in f.name: continue
        try: text = f.read_text(encoding="utf-8", errors="replace")
        except: continue

        for m in type_pat.finditer(text):
            kind, cls_name = m.group(1), m.group(2)
            bases = [b.strip().split('<')[0].strip()
                     for b in (m.group(3) or "").split(',') if b.strip()]
            if cls_name not in result:
                result[cls_name] = {"kind": kind, "bases": bases, "fields": [], "methods": []}
            else:
                for b in bases:
                    if b not in result[cls_name]["bases"]:
                        result[cls_name]["bases"].append(b)

            start = text.find('{', m.end())
            if start == -1: continue
            depth, end = 0, start
            for i, ch in enumerate(text[start:], start):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0: end = i; break
            body = text[start:end]

            for fm in field_pat.finditer(body):
                name = fm.group(3)
                if name in ("return","if","for","while","new","var"): continue
                result[cls_name]["fields"].append(
                    {"name":name,"type":fm.group(2).strip(),"access":fm.group(1)})

            for mm in method_pat.finditer(body):
                name = mm.group(4)
                if name in ("if","for","while","switch","return","new","catch","foreach"): continue
                result[cls_name]["methods"].append({
                    "name":name,"ret":mm.group(3).strip(),
                    "params":[p.strip().split()[-1] for p in mm.group(5).split(',') if p.strip()],
                    "isAsync":"async" in mm.group(2),"access":mm.group(1),
                })

    for d in result.values():
        for key in ("fields","methods"):
            seen = set()
            d[key] = [x for x in d[key] if not (x["name"] in seen or seen.add(x["name"]))]
    return result


def _parse_cpp(scripts_path: str, use_treesitter: bool = False) -> dict:
    """C++ 클래스 파싱. Axmol/Tree-sitter 경로와 레거시 regex 경로 분리."""
    if use_treesitter:
        try:
            from gdep.cpp_ts_parser import parse_project as ts_parse
            project = ts_parse(scripts_path)
            result = {}
            for name, cls in project.classes.items():
                # cpp_ts_parser: CPPClass.properties (fields), CPPClass.functions (methods)
                result[name] = {
                    "kind":    cls.kind,
                    "bases":   cls.bases,
                    "fields":  [{"name": f.name, "type": f.type_, "access": f.access}
                                for f in getattr(cls, "properties", [])],
                    "methods": [{"name": m.name, "ret": getattr(m, "return_type", "void"),
                                 "params": [], "isAsync": False, "access": m.access}
                                for m in getattr(cls, "functions", [])],
                }
            return result
        except Exception:
            pass  # fallback to legacy parser below
    # Legacy regex parser
    from gdep.cpp_parser import parse_project
    project = parse_project(scripts_path, ignore_engine=True)
    result = {}
    for name, cls in project.classes.items():
        result[name] = {
            "kind":    cls.kind,
            "bases":   cls.bases,
            "fields":  [{"name": f.name, "type": f.type_, "access": f.access}
                        for f in getattr(cls, "properties", [])],
            "methods": [{"name": m.name, "ret": m.return_type, "params": [],
                         "isAsync": False, "access": m.access}
                        for m in getattr(cls, "functions", [])],
        }
    return result


def _parse_ue5(scripts_path: str) -> dict:
    from gdep.ue5_parser import parse_project, to_class_map
    proj = parse_project(scripts_path)
    return to_class_map(proj)


@router.get("/list")
def list_classes(path: str = Query(...)):
    """클래스 목록 반환 (C# / C++ / UE5 자동 감지)"""
    try:
        profile = detect(path)
        kind = profile.kind
    except Exception:
        profile = None
        kind = None

    # detect()가 찾은 source_dirs 첫 번째를 실제 파싱 경로로 사용
    # (루트 경로 입력 시에도 Assets/Scripts 등 올바른 경로로 유도)
    if profile and profile.source_dirs:
        parse_path = str(profile.source_dirs[0])
    else:
        parse_path = path

    try:
        if kind == ProjectKind.UNREAL:
            classes = _parse_ue5(parse_path)
        elif kind == ProjectKind.CPP:
            # Axmol 프로젝트는 Tree-sitter 파서 사용
            is_axmol = profile and profile.extra.get("is_axmol", False)
            classes = _parse_cpp(parse_path, use_treesitter=is_axmol)
        else:
            classes = _parse_cs(parse_path)
        return {"classes": classes, "count": len(classes), "kind": kind.name if kind else "UNKNOWN"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))