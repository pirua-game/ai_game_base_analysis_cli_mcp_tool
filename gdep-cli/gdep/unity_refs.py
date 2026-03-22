"""
gdep.unity_refs
Unity Prefab/Scene back-reference analysis.

Flow:
  1. Traverse up from Scripts path to find Assets/ folder location.
  2. Map ClassName → GUID from .cs.meta files.
  3. Search for GUID back-references in .prefab / .unity files.
  4. Result: { "ClassName": ["Prefabs/UI/Login.prefab", "Scenes/Game.unity"] }
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# ── Data Models ──────────────────────────────────────────────

@dataclass
class PrefabRef:
    """Information about prefabs/scenes where a single class is used."""
    class_name:  str
    guid:        str
    usages:      list[str] = field(default_factory=list)  # Relative path from Assets/

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
    """Project-wide back-reference map."""
    assets_root:  Path
    guid_to_class: dict[str, str]          # guid → class_name
    class_to_ref:  dict[str, PrefabRef]    # class_name → PrefabRef

    def get(self, class_name: str) -> PrefabRef | None:
        return self.class_to_ref.get(class_name)

    def classes_used_in(self, asset_path: str) -> list[str]:
        """List of classes used in a specific prefab/scene."""
        return [ref.class_name for ref in self.class_to_ref.values()
                if asset_path in ref.usages]


# ── Project Root Discovery ────────────────────────────────────────

def find_assets_root(scripts_path: str) -> Path | None:
    """
    Traverses up from the Scripts path to find the Assets/ folder.
    Ex: .../TrumpCardClient/Assets/Scripts → .../TrumpCardClient/Assets
    """
    p = Path(scripts_path).resolve()
    # Check if the current path itself is under Assets
    for parent in [p] + list(p.parents):
        if parent.name == "Assets" and parent.is_dir():
            return parent
        assets = parent / "Assets"
        if assets.is_dir():
            return assets
    return None


# ── .meta Parsing ────────────────────────────────────────────────

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
    Parses .cs.meta files in the Scripts folder and returns a { guid: class_name } mapping.
    Uses the filename (without extension) as the class name.
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


# ── Prefab/Scene Back-reference Search ─────────────────────────────────────

# MonoBehaviour script reference pattern in Unity YAML
# m_Script: {fileID: 11500000, guid: abc123def456..., type: 3}
_SCRIPT_REF_PAT = re.compile(
    r'm_Script:\s*\{[^}]*guid:\s*([0-9a-f]{32})[^}]*\}',
    re.IGNORECASE
)


def _find_guids_in_file(asset_path: Path) -> set[str]:
    """Returns a set of GUIDs referenced in a prefab/scene file."""
    try:
        text = asset_path.read_text(encoding="utf-8", errors="replace")
        return set(_SCRIPT_REF_PAT.findall(text))
    except Exception:
        return set()


def build_ref_map(scripts_path: str,
                  progress_cb=None) -> UnityRefMap | None:
    """
    Builds the complete back-reference map.
    - scripts_path: Unity Scripts folder
    - progress_cb: (current, total) callback (optional)
    """
    assets_root = find_assets_root(scripts_path)
    if assets_root is None:
        return None

    # 1. GUID → ClassName map
    guid_to_class = build_guid_map(scripts_path)
    if not guid_to_class:
        return UnityRefMap(
            assets_root=assets_root,
            guid_to_class={},
            class_to_ref={},
        )

    # 2. Initialize PrefabRef
    class_to_ref: dict[str, PrefabRef] = {}
    for guid, cls in guid_to_class.items():
        if cls not in class_to_ref:
            class_to_ref[cls] = PrefabRef(class_name=cls, guid=guid)

    # 3. Collect .prefab + .unity files
    asset_files = (
        list(assets_root.rglob("*.prefab")) +
        list(assets_root.rglob("*.unity"))
    )

    _SKIP_DIRS = {"Packages", "Library", "Temp", "obj"}
    total = len(asset_files)
    completed = [0]

    def _scan(asset_file: Path):
        if any(p in _SKIP_DIRS for p in asset_file.parts):
            return asset_file, set()
        return asset_file, _find_guids_in_file(asset_file)

    max_workers = min(16, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scan, f): f for f in asset_files}
        for fut in as_completed(futures):
            completed[0] += 1
            if progress_cb:
                progress_cb(completed[0], total)
            try:
                asset_file, guids_in_file = fut.result()
            except Exception:
                continue
            if not guids_in_file:
                continue

            try:
                rel_path = str(asset_file.relative_to(assets_root.parent))
            except ValueError:
                rel_path = asset_file.name

            for guid in guids_in_file:
                cls = guid_to_class.get(guid)
                if cls and cls in class_to_ref:
                    if rel_path not in class_to_ref[cls].usages:
                        class_to_ref[cls].usages.append(rel_path)

    # 4. Remove unused classes (optional — keeping for now)
    return UnityRefMap(
        assets_root=assets_root,
        guid_to_class=guid_to_class,
        class_to_ref=class_to_ref,
    )


# ── Summary Utilities (for Agent) ────────────────────────────────────

def format_ref_result(ref: PrefabRef | None, class_name: str) -> str:
    if ref is None:
        return f"Could not find the GUID for class `{class_name}`. The .meta file might be missing or this might not be a Unity project."
    if not ref.usages:
        return f"Class `{class_name}` is not used in any prefabs or scenes."

    lines = [f"## Back-reference results for `{class_name}`",
             f"Used in {ref.total} assets  |  GUID: `{ref.guid[:8]}...`", ""]

    if ref.prefabs:
        lines.append(f"### 📦 Prefabs ({len(ref.prefabs)})")
        for p in sorted(ref.prefabs):
            lines.append(f"- `{p}`")

    if ref.scenes:
        lines.append(f"\n### 🎬 Scenes ({len(ref.scenes)})")
        for s in sorted(ref.scenes):
            lines.append(f"- `{s}`")

    return "\n".join(lines)
