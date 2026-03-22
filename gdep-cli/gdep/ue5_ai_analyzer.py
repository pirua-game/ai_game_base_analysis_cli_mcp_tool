"""
gdep.ue5_ai_analyzer
UE5 Behavior Tree and StateTree asset analyzer.

Both use binary .uasset parsing (no UE Editor required).

BehaviorTree:
  - Scans for BTTask_*/BTDecorator_*/BTService_* class names
  - Extracts Blackboard asset references
  - Links BT assets to AIController classes that use them

StateTree:
  - Scans for /Script/StateTreeModule references
  - Extracts StateTreeAIComponent usage and linked ST_ assets
  - Extracts Task class names (patterns like 'Delay Task', 'Move To')
  - Maps AIControllers → StateTree assets
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Binary string extraction ─────────────────────────────────
_STR_PAT = re.compile(rb'[\x20-\x7E]{5,}')

# ── BehaviorTree patterns — 바이너리 기반 (파일명 독립) ──────
# uasset은 UE 직렬화 포맷으로 문자열 사이에 null 바이트가 있어
# '/Script/AIModule.BehaviorTree' 연속 패턴이 존재하지 않음.
# AIModule과 BehaviorTree를 별도로 탐지하고 BTTask/BTDecorator/BTService로 보완.
_BT_ASSET_PAT     = re.compile(rb'AIModule|BehaviorTreeComponent|/Script/AIModule')
_BT_CONTENT_PAT   = re.compile(rb'BehaviorTree')   # BehaviorTree 단어 존재 확인
_BT_TASK_PAT      = re.compile(rb'BTTask_\w+')
_BT_DECORATOR_PAT = re.compile(rb'BTDecorator_\w+')
_BT_SERVICE_PAT   = re.compile(rb'BTService_\w+')
_BLACKBOARD_PAT   = re.compile(rb'BlackboardData|BlackboardAsset|Blackboard_')
_BB_KEY_PAT       = re.compile(rb'BlackboardKey\w*|BBKey_\w+')
_AICONTROLLER_REF = re.compile(rb'AIController')
_GAME_PATH_PAT    = re.compile(rb'/Game/[\w/]+')

# ── StateTree patterns — 바이너리 기반 (파일명 독립) ──────────
# uasset null 바이트 구조로 인해 모듈명을 분리해서 탐지
_ST_ASSET_PAT     = re.compile(rb'StateTreeModule|GameplayStateTreeModule|StateTreeComponent')
_ST_REF_PAT       = re.compile(rb'/Game/[\w/]+ST_\w+|ST_\w+\.uasset')
_ST_AI_COMP_PAT   = re.compile(rb'StateTreeAIComponent|StateTreeRef|StateTreeReference')
_ST_SCHEMA_PAT    = re.compile(rb'Schema\w*')
_ST_CONTEXT_PAT   = re.compile(rb'ContextActorClass|ContextDataDescs')

# Compact state info fields
_COMPACT_STATE_PAT = re.compile(rb'CompactStateTreeState')

_IGNORE_DIRS = {"__ExternalActors__", "__ExternalObjects__", "Collections", "Developers"}


# ── Data Models ───────────────────────────────────────────────

@dataclass
class BTAssetInfo:
    asset_name:   str
    asset_path:   str
    tasks:        list[str] = field(default_factory=list)
    decorators:   list[str] = field(default_factory=list)
    services:     list[str] = field(default_factory=list)
    blackboards:  list[str] = field(default_factory=list)
    game_refs:    list[str] = field(default_factory=list)


@dataclass
class StateTreeAssetInfo:
    asset_name:    str
    asset_path:    str
    tasks:         list[str] = field(default_factory=list)   # Human-readable task names
    task_classes:  list[str] = field(default_factory=list)   # C++ class refs
    context_types: list[str] = field(default_factory=list)
    linked_by:     list[str] = field(default_factory=list)   # AI Controllers that use this ST


@dataclass
class AIAssetMap:
    project_path:  str
    bt_assets:     list[BTAssetInfo]          = field(default_factory=list)
    st_assets:     list[StateTreeAssetInfo]   = field(default_factory=list)
    # asset_name → list of AI Controller asset names using it
    bt_users:      dict[str, list[str]]       = field(default_factory=dict)
    st_users:      dict[str, list[str]]       = field(default_factory=dict)


# ── Binary extraction helpers ─────────────────────────────────

def _strings(data: bytes, min_len: int = 5) -> list[str]:
    return [m.group().decode("ascii", "ignore")
            for m in re.finditer(rb'[\x20-\x7E]{' + str(min_len).encode() + rb',}', data)]


def _decode_set(matches) -> list[str]:
    seen = set()
    result = []
    for m in matches:
        s = m.group().decode("ascii", "ignore")
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


# ── BehaviorTree scanning ─────────────────────────────────────

def _scan_bt_asset(asset_path: Path) -> BTAssetInfo | None:
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    # uasset은 문자열 사이 null 바이트가 있어 '/Script/AIModule.BehaviorTree' 연속 패턴이 없음.
    # AIModule + BehaviorTree 단어 각각 체크하거나, BTTask/BTDecorator/BTService 존재로 판별.
    has_bt_marker = bool(
        (_BT_ASSET_PAT.search(data) and _BT_CONTENT_PAT.search(data)) or
        _BT_TASK_PAT.search(data) or
        _BT_DECORATOR_PAT.search(data) or
        _BT_SERVICE_PAT.search(data)
    )
    if not has_bt_marker:
        return None

    info = BTAssetInfo(
        asset_name=asset_path.stem,
        asset_path=str(asset_path),
    )

    info.tasks      = list(dict.fromkeys(
        m.decode("ascii","ignore") for m in _BT_TASK_PAT.findall(data)
    ))
    info.decorators = list(dict.fromkeys(
        m.decode("ascii","ignore") for m in _BT_DECORATOR_PAT.findall(data)
    ))
    info.services   = list(dict.fromkeys(
        m.decode("ascii","ignore") for m in _BT_SERVICE_PAT.findall(data)
    ))

    # Blackboard references
    bb_paths = _GAME_PATH_PAT.findall(data)
    info.blackboards = list(dict.fromkeys(
        p.decode("ascii","ignore") for p in bb_paths
        if b'Blackboard' in p or b'BB_' in p
    ))
    info.game_refs = list(dict.fromkeys(
        p.decode("ascii","ignore") for p in bb_paths
    ))[:20]

    return info if (info.tasks or info.decorators or info.services
                    or info.blackboards or info.game_refs) else None


# ── StateTree scanning ────────────────────────────────────────

# Human-readable task name pattern: title-cased words with spaces, e.g. "Delay Task", "Move To"
_HUMAN_TASK_PAT = re.compile(rb'[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}')
_KNOWN_TASK_WORDS = {
    "Delay Task", "Move To", "Wait", "Play Anim Montage", "Run Behavior",
    "Run EQS Query", "Set Tag", "Clear Tag", "Bool Compare", "Int Compare",
    "Float Compare", "Move Directly Toward", "Follow Path",
}


def _scan_st_asset(asset_path: Path) -> StateTreeAssetInfo | None:
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    if not _ST_ASSET_PAT.search(data):
        return None

    info = StateTreeAssetInfo(
        asset_name=asset_path.stem,
        asset_path=str(asset_path),
    )

    # Human-readable task names
    human_names = list(dict.fromkeys(
        m.group().decode("ascii","ignore")
        for m in _HUMAN_TASK_PAT.finditer(data)
    ))
    info.tasks = [n for n in human_names
                  if n in _KNOWN_TASK_WORDS or
                     any(kw in n for kw in ["Task", "Move", "Wait", "Delay",
                                            "Compare", "Check", "Play", "Set"])][:20]

    # C++ Task/Evaluator class refs from /Script/
    module_cls = re.findall(rb'/Script/\w+\.(\w+Task\w*|\w+Evaluator\w*|\w+Condition\w*)', data)
    info.task_classes = list(dict.fromkeys(
        m.decode("ascii","ignore") for m in module_cls
    ))[:20]

    # Context types
    game_refs = _GAME_PATH_PAT.findall(data)
    info.context_types = list(dict.fromkeys(
        p.decode("ascii","ignore") for p in game_refs
    ))[:15]

    return info


def _scan_ai_controller(asset_path: Path,
                        st_map: dict[str, StateTreeAssetInfo],
                        bt_map: dict[str, BTAssetInfo]) -> tuple[list[str], list[str]]:
    """Return (bt_refs, st_refs) that an AI Controller asset uses."""
    try:
        data = asset_path.read_bytes()
    except Exception:
        return [], []

    all_strings = _strings(data)
    bt_refs, st_refs = [], []

    for s in all_strings:
        name = Path(s).stem if "/" in s else s
        if name in bt_map:
            bt_refs.append(name)
        if name in st_map or "ST_" in s:
            # Extract the ST asset name
            m = re.search(r'ST_\w+', s)
            if m:
                st_refs.append(m.group())

    # Also look for explicit StateTreeRef pattern
    if _ST_AI_COMP_PAT.search(data):
        for m in re.finditer(rb'/Game/[\w/]*(ST_\w+)', data):
            st_refs.append(m.group(1).decode("ascii","ignore"))

    return list(dict.fromkeys(bt_refs)), list(dict.fromkeys(st_refs))


# ── Project scanner ───────────────────────────────────────────

def _find_content_root(project_path: str) -> Path | None:
    p = Path(project_path).resolve()
    for parent in [p] + list(p.parents):
        content = parent / "Content"
        if content.is_dir():
            return content
    return None


def _find_all_content_roots(project_path: str) -> list[tuple[Path, str]]:
    """
    Content + Plugins/*/Content 루트를 모두 반환.
    반환값: [(content_root, label), ...]
      label = "Project" | "Plugin:플러그인명"
    """
    content_root = _find_content_root(project_path)
    roots: list[tuple[Path, str]] = []
    if content_root:
        roots.append((content_root, "Project"))
        plugins_dir = content_root.parent / "Plugins"
        if plugins_dir.is_dir():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                # GameFeatures 플러그인은 하위 플러그인을 또 포함할 수 있음
                plugin_content = plugin_dir / "Content"
                if plugin_content.is_dir():
                    roots.append((plugin_content, f"Plugin:{plugin_dir.name}"))
                # GameFeatures/XxxPlugin/Content 패턴
                for sub in plugin_dir.iterdir():
                    if sub.is_dir():
                        sub_content = sub / "Content"
                        if sub_content.is_dir():
                            roots.append((sub_content, f"Plugin:{plugin_dir.name}/{sub.name}"))
    return roots


def _is_lfs_pointer(path: Path) -> bool:
    """Git LFS 포인터 파일인지 확인."""
    try:
        return path.read_bytes()[:40].startswith(b'version https://git-lfs')
    except Exception:
        return False


def _lfs_fallback_ai(project_path: str) -> tuple[list[str], list[str]]:
    """LFS 프로젝트에서 파일명 기반 BT_*/ST_* 목록 반환 (파일명 fallback)."""
    content_root = _find_content_root(project_path)
    bt_names: list[str] = []
    st_names: list[str] = []
    if content_root is None:
        return bt_names, st_names
    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            stem = Path(fname).stem
            # LFS fallback은 파일명으로만 판별 (바이너리 읽기 불가)
            if stem.startswith("BT_"):
                bt_names.append(stem)
            elif stem.startswith("ST_"):
                st_names.append(stem)
    return sorted(bt_names), sorted(st_names)


def _get_all_content_roots_paths(project_path: str) -> list[Path]:
    return [r for r, _ in _find_all_content_roots(project_path)]


def _scan_project(project_path: str) -> AIAssetMap:
    all_roots = _find_all_content_roots(project_path)
    result = AIAssetMap(project_path=project_path)

    if not all_roots:
        return result

    bt_by_name:  dict[str, BTAssetInfo]        = {}
    st_by_name:  dict[str, StateTreeAssetInfo] = {}
    ai_ctrl_paths: list[Path]                  = []

    for content_root, source_label in all_roots:
        if not content_root.exists():
            continue
        for root, dirs, files in os.walk(content_root):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for fname in files:
                if not fname.endswith(".uasset"):
                    continue
                fpath = Path(root) / fname
                stem  = fpath.stem

                if _is_lfs_pointer(fpath):
                    continue

                try:
                    chunk = fpath.read_bytes()[:4096]
                except Exception:
                    continue

                is_bt = bool(
                    (_BT_ASSET_PAT.search(chunk) and _BT_CONTENT_PAT.search(chunk)) or
                    _BT_TASK_PAT.search(chunk) or
                    _BT_DECORATOR_PAT.search(chunk) or
                    _BT_SERVICE_PAT.search(chunk)
                )
                is_st = bool(_ST_ASSET_PAT.search(chunk))

                if is_bt and stem not in bt_by_name:
                    info = _scan_bt_asset(fpath)
                    if info:
                        info.source_label = source_label  # type: ignore[attr-defined]
                        bt_by_name[stem] = info
                        result.bt_assets.append(info)
                elif is_st and stem not in st_by_name:
                    info = _scan_st_asset(fpath)
                    if info:
                        info.source_label = source_label  # type: ignore[attr-defined]
                        st_by_name[stem] = info
                        result.st_assets.append(info)

                if not is_bt and not is_st:
                    if (_AICONTROLLER_REF.search(chunk) or
                            "AIController" in stem or "AIC_" in stem):
                        ai_ctrl_paths.append(fpath)

    # Cross-reference: AI Controllers → BT/ST
    for ctrl_path in ai_ctrl_paths:
        bt_refs, st_refs = _scan_ai_controller(ctrl_path, st_by_name, bt_by_name)
        ctrl_name = ctrl_path.stem
        for bt_name in bt_refs:
            result.bt_users.setdefault(bt_name, []).append(ctrl_name)
        for st_name in st_refs:
            result.st_users.setdefault(st_name, []).append(ctrl_name)
            if st_name in st_by_name:
                st_by_name[st_name].linked_by.append(ctrl_name)

    return result


# ── Public API ────────────────────────────────────────────────

def _ai_map_to_dict(result: AIAssetMap) -> dict:
    import dataclasses
    return dataclasses.asdict(result)


def _ai_map_from_dict(d: dict) -> AIAssetMap:
    def _bt(x):  return BTAssetInfo(**{k: v for k, v in x.items()
                                       if k in BTAssetInfo.__dataclass_fields__})
    def _st(x):  return StateTreeAssetInfo(**{k: v for k, v in x.items()
                                              if k in StateTreeAssetInfo.__dataclass_fields__})
    return AIAssetMap(
        project_path=d["project_path"],
        bt_assets=[_bt(x) for x in d.get("bt_assets", [])],
        st_assets=[_st(x) for x in d.get("st_assets", [])],
        bt_users=d.get("bt_users", {}),
        st_users=d.get("st_users", {}),
    )


def _cached_scan(project_path: str) -> AIAssetMap:
    from .uasset_cache import fingerprint_content, load_cache, save_cache
    cache_key = "ai_analyzer_scan"
    roots = _get_all_content_roots_paths(project_path)
    fp = fingerprint_content(roots)
    cached = load_cache(project_path, cache_key)
    if cached and cached.get("_fp") == fp:
        try:
            return _ai_map_from_dict(cached["data"])
        except Exception:
            pass
    result = _scan_project(project_path)
    save_cache(project_path, cache_key, {"_fp": fp, "data": _ai_map_to_dict(result)})
    return result


def analyze_behavior_tree(project_path: str,
                          asset_name: str | None = None) -> str:
    result = _cached_scan(project_path)

    assets = result.bt_assets
    if not assets:
        bt_names, st_names = _lfs_fallback_ai(project_path)
        if bt_names:
            lines = [
                f"# BehaviorTree Assets [{Path(project_path).name}]",
                "> ⚠️ Git LFS 포인터 프로젝트 — 파일명 기반 목록 (바이너리 파싱 불가)\n",
                f"## BehaviorTree (BT_*) — {len(bt_names)}개",
            ]
            for s in bt_names[:50]:
                lines.append(f"  - `{s}`")
            if len(bt_names) > 50:
                lines.append(f"  ... +{len(bt_names)-50} more")
            return "\n".join(lines)
        return (
            "No BehaviorTree assets found.\n"
            "BT assets are expected to be named 'BT_*' or contain BehaviorTree references.\n"
            f"Searched under: {project_path}"
        )

    if asset_name:
        assets = [a for a in assets
                  if a.asset_name.lower() == asset_name.lower()
                  or asset_name.lower() in a.asset_name.lower()]

    lines = ["# BehaviorTree Analysis", f"Project: {project_path}", ""]

    for bt in assets:
        source = getattr(bt, 'source_label', 'Project')
        label  = f"  `[{source}]`" if source != 'Project' else ''
        lines.append(f"## {bt.asset_name}{label}")
        lines.append(f"File: {bt.asset_path}")

        users = result.bt_users.get(bt.asset_name, [])
        if users:
            lines.append(f"Used by AI Controllers: {', '.join(users)}")

        if bt.tasks:
            lines.append(f"\n### Tasks ({len(bt.tasks)})")
            for t in bt.tasks:
                lines.append(f"  - {t}")

        if bt.decorators:
            lines.append(f"\n### Decorators ({len(bt.decorators)})")
            for d in bt.decorators:
                lines.append(f"  - {d}")

        if bt.services:
            lines.append(f"\n### Services ({len(bt.services)})")
            for s in bt.services:
                lines.append(f"  - {s}")

        if bt.blackboards:
            lines.append("\n### Blackboard References")
            for b in bt.blackboards:
                lines.append(f"  - {b}")

        lines.append("")

    return "\n".join(lines)


def analyze_state_tree(project_path: str,
                       asset_name: str | None = None) -> str:
    result = _cached_scan(project_path)

    assets = result.st_assets
    if not assets:
        bt_names, st_names = _lfs_fallback_ai(project_path)
        if st_names:
            lines = [
                f"# StateTree Assets [{Path(project_path).name}]",
                "> ⚠️ Git LFS 포인터 프로젝트 — 파일명 기반 목록 (바이너리 파싱 불가)\n",
                f"## StateTree (ST_*) — {len(st_names)}개",
            ]
            for s in st_names[:50]:
                lines.append(f"  - `{s}`")
            if len(st_names) > 50:
                lines.append(f"  ... +{len(st_names)-50} more")
            return "\n".join(lines)
        return (
            "No StateTree assets found.\n"
            "StateTree assets are expected to be named 'ST_*' or contain StateTreeModule references.\n"
            f"Searched under: {project_path}"
        )

    if asset_name:
        assets = [a for a in assets
                  if a.asset_name.lower() == asset_name.lower()
                  or asset_name.lower() in a.asset_name.lower()]

    lines = ["# StateTree Analysis", f"Project: {project_path}", ""]

    for st in assets:
        source = getattr(st, 'source_label', 'Project')
        label  = f"  `[{source}]`" if source != 'Project' else ''
        lines.append(f"## {st.asset_name}{label}")
        lines.append(f"File: {st.asset_path}")

        if st.linked_by:
            lines.append(f"Linked by: {', '.join(st.linked_by)}")

        if st.tasks:
            lines.append("\n### Task Names (from asset data)")
            for t in st.tasks:
                lines.append(f"  - {t}")

        if st.task_classes:
            lines.append("\n### C++ Task/Evaluator Classes")
            for tc in st.task_classes:
                lines.append(f"  - {tc}")

        if st.context_types:
            lines.append("\n### Asset References")
            for ct in st.context_types[:10]:
                lines.append(f"  - {ct}")

        lines.append("")

    return "\n".join(lines)
