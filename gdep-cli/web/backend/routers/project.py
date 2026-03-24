"""
/api/project
프로젝트 감지, scan, describe, read_source 엔드포인트
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.detector import detect, ProjectKind
from gdep import runner

router = APIRouter()


def _get_profile(path: str):
    try:
        return detect(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"프로젝트 감지 실패: {e}")


def _is_ue5(profile) -> bool:
    return profile.kind == ProjectKind.UNREAL


def _parse_scan_output(stdout: str) -> dict:
    lines = stdout.splitlines()
    coupling, cycles = [], []
    in_table = in_cycles = False
    for line in lines:
        s = line.strip()
        if "── 결합도 상위" in s:  in_table = True;  continue
        if in_table and ("순위" in s or s.startswith("─")): continue
        if in_table and s.startswith("──"):  in_table = False; continue
        if in_table and s:
            parts = s.split()
            if len(parts) >= 3 and parts[0].isdigit():
                try: coupling.append({"rank":int(parts[0]),"name":parts[1],"score":int(parts[-1])})
                except: pass
        if "── 순환 참조" in s:   in_cycles = True;  continue
        if in_cycles and s.startswith("↻"): cycles.append(s[1:].strip())
        elif in_cycles and s.startswith("──") and "순환" not in s: in_cycles = False
    return {"coupling": coupling, "cycles": cycles}


# ── 엔드포인트 ────────────────────────────────────────────────

@router.get("/detect")
def detect_project(path: str = Query(...)):
    profile = _get_profile(path)
    return {
        "kind":        profile.kind.name,
        "engine":      profile.engine or "",
        "language":    profile.language or "",
        "display":     profile.display,
        "name":        profile.name,
        "root":        str(profile.root),
        "source_dirs": [str(d) for d in profile.source_dirs],
    }


class ScanRequest(BaseModel):
    path:         str
    top:          int  = 20
    circular:     bool = True
    dead_code:    bool = False
    deep:         bool = False
    include_refs: bool = False


@router.post("/scan")
def scan(req: ScanRequest):
    profile = _get_profile(req.path)

    if _is_ue5(profile):
        from gdep.ue5_runner import scan as ue5_scan
        src = str(profile.source_dirs[0]) if profile.source_dirs else req.path
        result = ue5_scan(src, top=req.top, circular=req.circular,
                          dead_code=req.dead_code, deep=req.deep)
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.error_message)
        if result.data:
            return result.data
        return _parse_scan_output(result.stdout)

    # 항상 JSON 포맷으로 요청 → result.data에 구조화된 데이터 확보
    fmt = "json"
    result = runner.scan(profile, circular=req.circular, top=req.top,
                         dead_code=req.dead_code, deep=req.deep,
                         include_refs=req.include_refs, fmt=fmt)
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    if result.data:
        data = result.data
        # coupling 배열 정규화: rank 필드 보장, cycles 배열 변환
        coupling = data.get("coupling", [])
        for i, item in enumerate(coupling):
            item.setdefault("rank", i + 1)
        # cycles: gdep JSON은 [[node,...]] 리스트로 옴 → "A → B → A" 문자열로 변환
        raw_cycles = data.get("cycles", [])
        cycles_str = []
        for cycle in raw_cycles:
            if isinstance(cycle, list):
                cycles_str.append(" → ".join(cycle))
            else:
                cycles_str.append(str(cycle))
        return {
            "coupling":  coupling,
            "cycles":    cycles_str,
            "deadNodes": data.get("deadNodes", []),
        }
    return _parse_scan_output(result.stdout)


class ImpactRequest(BaseModel):
    path:         str
    target_class: str
    depth:        int = 3


def _parse_impact_stdout(stdout: str) -> dict | None:
    """
    gdep.exe impact 텍스트 출력을 트리 구조로 파싱.
    예시:
      BattleCore (BattleCore.cs)
      ├── Abilitiable (BattleStruct.cs)
      │   ├── BattleCore (BattleCore.cs) [RECURSIVE]
      └── UIBattle (UIBattle.cs)
    """
    lines = stdout.splitlines()

    # 진입점 줄 찾기 (들여쓰기 없고 '──' 로 시작하지 않는 첫 번째 내용 줄)
    root_line_idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("──") or s.startswith("Building"):
            continue
        root_line_idx = i
        break

    if root_line_idx is None:
        return None

    def parse_node_text(text: str) -> dict:
        """'ClassName (file.cs) [RECURSIVE]' → {name, file, children:[]}"""
        recursive = "[RECURSIVE]" in text
        text = text.replace("[RECURSIVE]", "").strip()
        m = re.match(r'^(.+?)\s+\((.+?)\)$', text)
        if m:
            return {"name": m.group(1).strip(), "file": m.group(2).strip(),
                    "children": [], "recursive": recursive}
        return {"name": text.strip(), "file": "", "children": [], "recursive": recursive}

    def get_depth(line: str) -> int:
        """트리 접두사 문자 수로 depth 계산"""
        count = 0
        for ch in line:
            if ch in "│├└─ ":
                count += 1
            else:
                break
        # depth = 접두사 길이 // 4 (├── = 4chars per level)
        return count // 4

    def strip_prefix(line: str) -> str:
        """├── / └── / │   등 트리 접두사 제거 후 순수 텍스트 반환"""
        return re.sub(r'^[│├└─\s]+', '', line).strip()

    # 루트 노드
    root_text = strip_prefix(lines[root_line_idx])
    root = parse_node_text(root_text)

    # 스택 기반 트리 빌드
    stack: list[tuple[int, dict]] = [(-1, root)]  # (depth, node)

    for line in lines[root_line_idx + 1:]:
        if not line.strip():
            continue
        # "── Asset Usages" 같은 섹션 구분선 만나면 중단
        if re.match(r'^[\s─]+$', line) or "Asset Usages" in line:
            break

        depth = get_depth(line)
        text  = strip_prefix(line)
        if not text:
            continue

        node = parse_node_text(text)

        # 스택에서 현재 depth의 부모 찾기
        while len(stack) > 1 and stack[-1][0] >= depth:
            stack.pop()

        parent = stack[-1][1]
        parent["children"].append(node)
        stack.append((depth, node))

    return root


@router.post("/impact")
def impact(req: ImpactRequest):
    profile = _get_profile(req.path)
    result = runner.impact(profile, req.target_class, depth=req.depth)
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)

    # C++/UE5는 runner가 이미 dict 트리를 data에 담아서 반환
    tree = result.data
    # C# (Unity/Dotnet)는 텍스트 출력 → 파싱
    if tree is None and result.stdout:
        tree = _parse_impact_stdout(result.stdout)

    return {"stdout": result.stdout, "tree": tree}


class LintRequest(BaseModel):
    path: str
    fmt:  str = "json"


@router.post("/lint")
def lint(req: LintRequest):
    profile = _get_profile(req.path)
    result = runner.lint(profile, fmt="json")
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    import json as _json
    try:
        issues = _json.loads(result.stdout) if result.stdout else []
    except Exception:
        issues = []
    return {"issues": issues, "count": len(issues)}


class DescribeRequest(BaseModel):
    path:       str
    class_name: str


@router.post("/describe")
def describe(req: DescribeRequest):
    profile = _get_profile(req.path)

    if _is_ue5(profile):
        from gdep.ue5_runner import describe as ue5_describe
        src = str(profile.source_dirs[0]) if profile.source_dirs else req.path
        result = ue5_describe(src, req.class_name)
    else:
        result = runner.describe(profile, req.class_name)

    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    return {"stdout": result.stdout}


class ReadSourceRequest(BaseModel):
    path:       str
    class_name: str
    max_chars:  int = 8000


@router.post("/read_source")
def read_source(req: ReadSourceRequest):
    profile = _get_profile(req.path)

    if _is_ue5(profile):
        from gdep.ue5_runner import read_source as ue5_read_source
        src = str(profile.source_dirs[0]) if profile.source_dirs else req.path
        result = ue5_read_source(src, req.class_name, max_chars=req.max_chars)
    else:
        result = runner.read_source(profile, req.class_name, max_chars=req.max_chars)

    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error_message)
    return {"content": result.stdout}


# ── Stage 42: 신규 엔드포인트 ─────────────────────────────────

from typing import Optional


class TestScopeRequest(BaseModel):
    path:       str
    class_name: str
    depth:      int = 3


@router.post("/test-scope")
def test_scope(req: TestScopeRequest):
    profile = _get_profile(req.path)
    result = runner.test_scope(profile, req.class_name, depth=req.depth, fmt="json")
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    import json as _json
    try:
        data = _json.loads(result.stdout) if result.stdout else (result.data or {})
    except Exception:
        data = result.data or {}
    return {
        "target_class":    data.get("target_class", req.class_name),
        "affected_count":  data.get("affected_count", 0),
        "test_file_count": data.get("test_file_count", 0),
        "test_files":      data.get("test_files", []),
    }


class AdviseRequest(BaseModel):
    path:        str
    focus_class: Optional[str] = None
    refresh:     bool = False


@router.post("/advise")
def advise(req: AdviseRequest):
    profile = _get_profile(req.path)
    result = runner.advise(profile, focus_class=req.focus_class, fmt="console")
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    return {"report": result.stdout}


class LintFixRequest(BaseModel):
    path:     str
    rule_ids: Optional[list] = None


@router.post("/lint-fix")
def lint_fix(req: LintFixRequest):
    profile = _get_profile(req.path)
    result = runner.lint(profile, fmt="json")
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error_message)
    import json as _json
    try:
        issues = _json.loads(result.stdout) if result.stdout else (result.data or [])
    except Exception:
        issues = result.data or []
    if req.rule_ids:
        rule_set = {r.upper() for r in req.rule_ids}
        issues = [i for i in issues if i.get("rule_id", "").upper() in rule_set]
    fixable = [i for i in issues if i.get("fix_suggestion")]
    return {
        "total":   len(issues),
        "fixable": len(fixable),
        "results": fixable,
    }


class DiffSummaryRequest(BaseModel):
    path:   str
    commit: Optional[str] = None


@router.post("/diff-summary")
def diff_summary(req: DiffSummaryRequest):
    from gdep_mcp.tools.summarize_project_diff import run as _diff_run
    report = _diff_run(req.path, commit_ref=req.commit)
    return {"report": report}