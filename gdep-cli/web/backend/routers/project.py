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


# ── describe 구조화 파서 ──────────────────────────────────────

def _parse_describe_output(stdout: str, class_name: str) -> dict:
    """
    describe 출력에서 inheritance_chain, kind, file_path 등 구조화된 필드를 추출.
    stdout 필드도 유지해 기존 프론트엔드 하위호환 보장.
    """
    inheritance_chain: list[str] = []
    also_implements: list[str] = []
    kind = ""
    file_path = ""

    for line in stdout.splitlines():
        s = line.strip()
        # UE5/C++ 포맷: "  Inheritance chain: A → B → C"
        if s.startswith("Inheritance chain:"):
            raw = s[len("Inheritance chain:"):].strip()
            inheritance_chain = [p.strip() for p in raw.split("→") if p.strip()]
        # Unity C# 포맷: "  chain: A → B → C"
        elif s.startswith("chain:"):
            raw = s[len("chain:"):].strip()
            inheritance_chain = [p.strip() for p in raw.split("→") if p.strip()]
        # 단일 상속: "  Inheritance: Parent" 또는 "  : Parent"
        elif s.startswith("Inheritance:"):
            raw = s[len("Inheritance:"):].strip()
            if raw:
                inheritance_chain = [class_name, raw]
        elif re.match(r"^:\s+\S", s):
            raw = s[1:].strip()
            if raw:
                inheritance_chain = [class_name, raw]
        # also implements
        elif s.startswith("Also implements:") or s.startswith("also:"):
            key = "Also implements:" if "Also implements:" in s else "also:"
            raw = s[len(key):].strip()
            also_implements = [p.strip() for p in raw.split(",") if p.strip()]
        # Kind 줄 (예: "Class  UIBase")
        elif s.lower().startswith("class ") or s.lower().startswith("struct "):
            parts = s.split(None, 1)
            if len(parts) >= 1:
                kind = parts[0]
        # 파일 경로
        elif s.startswith("File:") or s.startswith("Source:"):
            file_path = s.split(":", 1)[1].strip()

    return {
        "class_name":        class_name,
        "kind":              kind,
        "file_path":         file_path,
        "inheritance_chain": inheritance_chain,
        "also_implements":   also_implements,
        "stdout":            stdout,
    }


# 기존 describe 엔드포인트를 구조화된 응답으로 업그레이드
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
    return _parse_describe_output(result.stdout, req.class_name)


# ── Phase 1-2: explain_method_logic ──────────────────────────

class ExplainMethodLogicRequest(BaseModel):
    path:        str
    class_name:  str
    method_name: str


@router.post("/explain-method-logic")
def explain_method_logic(req: ExplainMethodLogicRequest):
    try:
        from gdep_mcp.tools.explain_method_logic import run, _parse_control_flow
        from gdep_mcp.tools.explain_method_logic import (
            _extract_cs_method, _extract_cpp_method
        )

        raw_text = run(req.path, req.class_name, req.method_name)

        # 구조화: "1. Guard    : ..." / "2. Branch   : ..." 줄 파싱
        # run()이 번호를 붙여 출력하므로 "N. " 접두사를 먼저 제거
        items = []
        source_file = ""
        confidence = ""
        _num_prefix = re.compile(r'^\d+\.\s+')
        for line in raw_text.splitlines():
            s = line.strip()
            # "N. Kind : ..." 형식의 번호 접두사 제거
            s_bare = _num_prefix.sub('', s)
            for kind in ("Guard", "Branch", "Loop", "Switch", "Exception", "Always"):
                if s_bare.startswith(kind):
                    rest = s_bare[len(kind):].lstrip(": ").strip()
                    items.append({"type": kind.lower(), "text": rest})
                    break
            if s.startswith("Source:"):
                source_file = s[len("Source:"):].strip()
            # confidence_footer 포맷: "> Confidence: **HIGH** (note)"
            if "Confidence:" in s:
                confidence = s

        return {
            "raw":         raw_text,
            "items":       items,
            "source_file": source_file,
            "confidence":  confidence,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 1-3: get_project_context ───────────────────────────

@router.get("/context")
def get_project_context(path: str = Query(...)):
    try:
        from gdep.init_context import build_context_output
        context = build_context_output(path)
        agents_md = Path(path) / ".gdep" / "AGENTS.md"
        # project root 탐색 (최대 3단계 상위)
        p = Path(path)
        for _ in range(4):
            candidate = p / ".gdep" / "AGENTS.md"
            if candidate.exists():
                agents_md = candidate
                break
            p = p.parent
        return {
            "context":       context,
            "has_agents_md": agents_md.exists(),
            "agents_md_path": str(agents_md) if agents_md.exists() else "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 1-4: gdep init ─────────────────────────────────────

class InitRequest(BaseModel):
    path:  str
    force: bool = False


@router.post("/init")
def init_project(req: InitRequest):
    try:
        from gdep.init_context import build_context_output
        from gdep.detector import detect as _detect
        import json as _json

        profile = _detect(req.path)
        root = profile.root

        agents_dir = root / ".gdep"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agents_md = agents_dir / "AGENTS.md"

        if agents_md.exists() and not req.force:
            return {
                "success":       False,
                "agents_md_path": str(agents_md),
                "message":       "AGENTS.md already exists. Use force=true to overwrite.",
            }

        content = build_context_output(req.path)
        agents_md.write_text(content, encoding="utf-8")
        return {
            "success":        True,
            "agents_md_path": str(agents_md),
            "message":        f"AGENTS.md created at {agents_md}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))