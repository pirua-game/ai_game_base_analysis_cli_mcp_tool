"""
gdep.unity_refs
Unity 프리팹/씬 역참조 분석.

흐름:
  1. Scripts 경로에서 상위로 탐색해 Assets/ 폴더 위치 확인
  2. .cs.meta 파일에서 클래스명 → GUID 매핑
  3. .prefab / .unity 파일에서 GUID 역참조 검색
  4. 결과: { "ClassName": ["Prefabs/UI/Login.prefab", "Scenes/Game.unity"] }
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


# ── 데이터 모델 ──────────────────────────────────────────────

@dataclass
class PrefabRef:
    """클래스 하나가 사용되는 프리팹/씬 정보"""
    class_name:  str
    guid:        str
    usages:      list[str] = field(default_factory=list)  # Assets/ 기준 상대 경로

    @property
    def prefabs(self) -> list[str]:
        return [u for u in self.usages if u.endswith(".prefab")]

    @property
    def scenes(self) -> list[str]:
        return [u for u in self.usages if u.endswith(".unity")]

    @property
    def total(self) -> int:
        return len(self.usages)


@dataclass
class UnityRefMap:
    """프로젝트 전체 역참조 맵"""
    assets_root:  Path
    guid_to_class: dict[str, str]          # guid → class_name
    class_to_ref:  dict[str, PrefabRef]    # class_name → PrefabRef

    def get(self, class_name: str) -> PrefabRef | None:
        return self.class_to_ref.get(class_name)

    def classes_used_in(self, asset_path: str) -> list[str]:
        """특정 프리팹/씬에서 사용하는 클래스 목록"""
        return [ref.class_name for ref in self.class_to_ref.values()
                if asset_path in ref.usages]


# ── 프로젝트 루트 탐색 ────────────────────────────────────────

def find_assets_root(scripts_path: str) -> Path | None:
    """
    Scripts 경로에서 상위로 올라가며 Assets/ 폴더를 찾습니다.
    예: .../TrumpCardClient/Assets/Scripts → .../TrumpCardClient/Assets
    """
    p = Path(scripts_path).resolve()
    # 현재 경로 자체가 Assets 하위이면 바로 찾기
    for parent in [p] + list(p.parents):
        if parent.name == "Assets" and parent.is_dir():
            return parent
        assets = parent / "Assets"
        if assets.is_dir():
            return assets
    return None


# ── .meta 파싱 ────────────────────────────────────────────────

_GUID_PAT = re.compile(r'^guid:\s*([0-9a-f]{32})', re.MULTILINE)


def _parse_guid(meta_path: Path) -> str | None:
    try:
        text = meta_path.read_text(encoding="utf-8", errors="replace")
        m = _GUID_PAT.search(text)
        return m.group(1) if m else None
    except Exception:
        return None


def build_guid_map(scripts_path: str) -> dict[str, str]:
    """
    Scripts 폴더의 .cs.meta 파일을 파싱해서
    { guid: class_name } 매핑 반환.
    파일명(확장자 제거)을 클래스명으로 사용.
    """
    guid_map: dict[str, str] = {}
    root = Path(scripts_path)
    if not root.exists():
        return guid_map

    for meta in root.rglob("*.cs.meta"):
        guid = _parse_guid(meta)
        if guid:
            # SomeClass.cs.meta → SomeClass
            class_name = meta.name.replace(".cs.meta", "")
            guid_map[guid] = class_name

    return guid_map


# ── 프리팹/씬 역참조 검색 ─────────────────────────────────────

# Unity YAML에서 MonoBehaviour 스크립트 참조 패턴
# m_Script: {fileID: 11500000, guid: abc123def456..., type: 3}
_SCRIPT_REF_PAT = re.compile(
    r'm_Script:\s*\{[^}]*guid:\s*([0-9a-f]{32})[^}]*\}',
    re.IGNORECASE
)


def _find_guids_in_file(asset_path: Path) -> set[str]:
    """프리팹/씬 파일에서 참조된 GUID 집합 반환"""
    try:
        text = asset_path.read_text(encoding="utf-8", errors="replace")
        return set(_SCRIPT_REF_PAT.findall(text))
    except Exception:
        return set()


def build_ref_map(scripts_path: str,
                  progress_cb=None) -> UnityRefMap | None:
    """
    전체 역참조 맵 빌드.
    - scripts_path: Unity Scripts 폴더
    - progress_cb: (current, total) 콜백 (선택)
    """
    assets_root = find_assets_root(scripts_path)
    if assets_root is None:
        return None

    # 1. GUID → 클래스명 맵
    guid_to_class = build_guid_map(scripts_path)
    if not guid_to_class:
        return UnityRefMap(
            assets_root=assets_root,
            guid_to_class={},
            class_to_ref={},
        )

    # 2. PrefabRef 초기화
    class_to_ref: dict[str, PrefabRef] = {}
    for guid, cls in guid_to_class.items():
        if cls not in class_to_ref:
            class_to_ref[cls] = PrefabRef(class_name=cls, guid=guid)

    # 3. .prefab + .unity 파일 수집
    asset_files = (
        list(assets_root.rglob("*.prefab")) +
        list(assets_root.rglob("*.unity"))
    )

    total = len(asset_files)
    for i, asset_file in enumerate(asset_files):
        if progress_cb:
            progress_cb(i + 1, total)

        # 엔진 폴더 스킵
        if any(p in {"Packages", "Library", "Temp", "obj"} for p in asset_file.parts):
            continue

        guids_in_file = _find_guids_in_file(asset_file)
        if not guids_in_file:
            continue

        # Assets/ 기준 상대 경로
        try:
            rel_path = str(asset_file.relative_to(assets_root.parent))
        except ValueError:
            rel_path = asset_file.name

        # 역참조 기록
        for guid in guids_in_file:
            cls = guid_to_class.get(guid)
            if cls and cls in class_to_ref:
                if rel_path not in class_to_ref[cls].usages:
                    class_to_ref[cls].usages.append(rel_path)

    # 4. 사용되지 않는 클래스 제거 (선택 — 일단 유지)
    return UnityRefMap(
        assets_root=assets_root,
        guid_to_class=guid_to_class,
        class_to_ref=class_to_ref,
    )


# ── 요약 유틸 (에이전트용) ────────────────────────────────────

def format_ref_result(ref: PrefabRef | None, class_name: str) -> str:
    if ref is None:
        return f"`{class_name}` 클래스의 GUID를 찾을 수 없어요. .meta 파일이 없거나 Unity 프로젝트가 아닐 수 있어요."
    if not ref.usages:
        return f"`{class_name}` 클래스는 어떤 프리팹/씬에서도 사용되지 않아요."

    lines = [f"## `{class_name}` 역참조 결과",
             f"총 {ref.total}개 에셋에서 사용 중  |  GUID: `{ref.guid[:8]}...`", ""]

    if ref.prefabs:
        lines.append(f"### 📦 프리팹 ({len(ref.prefabs)}개)")
        for p in sorted(ref.prefabs):
            lines.append(f"- `{p}`")

    if ref.scenes:
        lines.append(f"\n### 🎬 씬 ({len(ref.scenes)}개)")
        for s in sorted(ref.scenes):
            lines.append(f"- `{s}`")

    return "\n".join(lines)
