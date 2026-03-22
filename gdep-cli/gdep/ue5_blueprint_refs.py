"""
gdep.ue5_blueprint_refs
UE5 Blueprint/Asset back-reference analysis.

Extracts class references from UE5 .uasset binaries.
They are stored as ASCII strings in the format '/Script/ModuleName.ClassName'.

Important: Internally, UE5 removes C++ prefixes (A, U, F, I, E) when storing them.
Ex) AARPlayerCharacter → ARPlayerCharacter (A removed)
    UARAttributeSet    → ARAttributeSet    (U removed)

Therefore, prefixes are considered when mapping back-reference results to actual C++ class names.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_IGNORE_DIRS = {
    "__ExternalActors__",
    "__ExternalObjects__",
    "Collections",
    "Developers",
}

# Pattern for class references extracted from UE5 binaries
_MODULE_CLASS_PAT = re.compile(rb'/Script/(\w+)\.(\w+)')

# UE5 C++ prefixes (used to generate actual class name candidates)
_UE_PREFIXES = ('A', 'U', 'F', 'I', 'E', 'T')


# ── Data Classes ──────────────────────────────────────────────

@dataclass
class BlueprintRef:
    class_name:    str
    raw_name:      str          # Original name extracted from the binary
    module_name:   str
    usages:        list[str] = field(default_factory=list)

    @property
    def blueprints(self) -> list[str]:
        return [u for u in self.usages if u.endswith('.uasset')]

    @property
    def maps(self) -> list[str]:
        return [u for u in self.usages if u.endswith('.umap')]

    @property
    def total(self) -> int:
        return len(self.usages)


@dataclass
class UE5RefMap:
    content_root:  Path
    module_name:   str
    # raw_name (binary extraction) → BlueprintRef
    raw_to_ref:    dict[str, BlueprintRef] = field(default_factory=dict)
    # cpp_class_name → BlueprintRef (actual class name with prefix)
    class_to_ref:  dict[str, BlueprintRef] = field(default_factory=dict)

    def get(self, class_name: str) -> BlueprintRef | None:
        """Search back-references by C++ class name (including prefix normalization)."""
        # Exact match
        if class_name in self.class_to_ref:
            return self.class_to_ref[class_name]
        # Search raw_name after removing prefix
        for prefix in _UE_PREFIXES:
            if class_name.startswith(prefix):
                raw = class_name[len(prefix):]
                if raw in self.raw_to_ref:
                    return self.raw_to_ref[raw]
        # Direct search by raw_name
        if class_name in self.raw_to_ref:
            return self.raw_to_ref[class_name]
        return None


# ── Content Root / Module Name Discovery ────────────────────────────────

def find_content_root(project_path: str) -> Path | None:
    """프로젝트 Content 폴더 하나만 반환 (하위 호환)."""
    roots = collect_content_roots(project_path)
    return roots[0][0] if roots else None


def collect_content_roots(project_path: str) -> list[tuple[Path, str]]:
    """
    프로젝트 Content + 모든 Plugin Content 폴더를 반환.
    Returns: [(content_path, source_label), ...]
      source_label: "Project" 또는 "Plugin/플러그인명"
    """
    p = Path(project_path).resolve()

    # 프로젝트 루트 탐색
    project_root: Path | None = None
    for parent in [p] + list(p.parents):
        if list(parent.glob("*.uproject")):
            project_root = parent
            break
        if (parent / "Content").is_dir() and not project_root:
            project_root = parent

    if project_root is None:
        # Source 폴더가 입력된 경우 상위에서 찾기
        for parent in p.parents:
            if (parent / "Content").is_dir():
                project_root = parent
                break

    if project_root is None:
        return []

    results: list[tuple[Path, str]] = []

    # 1. 프로젝트 Content
    project_content = project_root / "Content"
    if project_content.is_dir():
        results.append((project_content, "Project"))

    # 2. Plugins/<플러그인명>/Content
    plugins_root = project_root / "Plugins"
    if plugins_root.is_dir():
        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            # GameFeatures 플러그인은 하위에 또 플러그인이 있을 수 있음
            plugin_content = plugin_dir / "Content"
            if plugin_content.is_dir():
                results.append((plugin_content, f"Plugin/{plugin_dir.name}"))
            # GameFeatures/<sub-plugin>/Content
            for sub in sorted(plugin_dir.iterdir()):
                if sub.is_dir() and (sub / "Content").is_dir():
                    results.append((sub / "Content",
                                    f"Plugin/{plugin_dir.name}/{sub.name}"))

    return results


def detect_module_name(project_path: str) -> str:
    p = Path(project_path).resolve()
    for parent in [p] + list(p.parents):
        uprojects = list(parent.glob("*.uproject"))
        if uprojects:
            return uprojects[0].stem
    for part in p.parts[::-1]:
        if part not in ("Source", "Content", ""):
            return part
    return "Game"


# ── Asset Scanning ─────────────────────────────────────────────────

def _extract_class_refs(asset_path: Path, module_bytes: bytes) -> set[str]:
    """
    Extracts class references for the given module from .uasset/.umap binaries.
    Excludes _C suffix (Blueprint-generated classes).
    return: {raw_class_name, ...}
    """
    try:
        data = asset_path.read_bytes()
    except Exception:
        return set()

    found = set()
    for m in _MODULE_CLASS_PAT.finditer(data):
        if m.group(1) == module_bytes:
            cls = m.group(2).decode('ascii', errors='ignore')
            if cls and not cls.endswith('_C'):
                found.add(cls)
    return found


def build_ref_map(source_path: str, progress_cb=None) -> UE5RefMap | None:
    content_root = find_content_root(source_path)
    if content_root is None:
        return None

    module_name  = detect_module_name(source_path)
    module_bytes = module_name.encode('ascii')

    # Collect .uasset / .umap files
    asset_files = []
    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if fname.endswith(('.uasset', '.umap')):
                asset_files.append(Path(root) / fname)

    ref_map = UE5RefMap(
        content_root=content_root,
        module_name=module_name,
    )
    total = len(asset_files)

    # ── Parallel I/O with ThreadPoolExecutor ──────────────────
    completed = [0]  # list to allow mutation in closure

    def _scan(asset_path: Path):
        return asset_path, _extract_class_refs(asset_path, module_bytes)

    max_workers = min(16, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scan, p): p for p in asset_files}
        for fut in as_completed(futures):
            completed[0] += 1
            if progress_cb:
                progress_cb(completed[0], total)
            try:
                asset_path, raw_refs = fut.result()
            except Exception:
                continue
            if not raw_refs:
                continue

            try:
                rel_path = str(asset_path.relative_to(content_root.parent))
            except ValueError:
                rel_path = asset_path.name

            for raw_cls in raw_refs:
                if raw_cls not in ref_map.raw_to_ref:
                    ref_map.raw_to_ref[raw_cls] = BlueprintRef(
                        class_name=raw_cls,
                        raw_name=raw_cls,
                        module_name=module_name,
                    )
                ref = ref_map.raw_to_ref[raw_cls]
                if rel_path not in ref.usages:
                    ref.usages.append(rel_path)

    # Build class_to_ref: Map prefix candidates → BlueprintRef
    for raw_cls, ref in ref_map.raw_to_ref.items():
        ref_map.class_to_ref[raw_cls] = ref
        for prefix in _UE_PREFIXES:
            candidate = prefix + raw_cls
            if candidate not in ref_map.class_to_ref:
                ref_map.class_to_ref[candidate] = ref

    return ref_map


# ── Serialization for API response ─────────────────────────────────────────

def ref_map_to_dict(ref_map: UE5RefMap) -> dict:
    """Converts the map to a dictionary for backend API response."""
    result = {}
    for raw_cls, ref in ref_map.raw_to_ref.items():
        if ref.usages:
            result[raw_cls] = {
                "blueprints": ref.blueprints,
                "maps":       ref.maps,
                "total":      ref.total,
            }
    return result


# ── Formatting for Agent ───────────────────────────────────────────

def format_ref_result(ref: BlueprintRef | None, class_name: str) -> str:
    if ref is None:
        return (
            f"Could not find class `{class_name}` in Blueprints. "
            "It might be a C++-only class or not directly used in Blueprints."
        )
    if not ref.usages:
        return f"Class `{class_name}` is not used in any Blueprints or maps."

    lines = [
        f"## UE5 Blueprint back-reference for `{class_name}`",
        f"Used in {ref.total} assets total",
        "",
    ]
    if ref.blueprints:
        lines.append(f"### 📋 Blueprints ({len(ref.blueprints)})")
        for p in sorted(ref.blueprints):
            lines.append(f"- `{Path(p).name}` — `{p}`")
    if ref.maps:
        lines.append(f"\n### 🗺️ Maps ({len(ref.maps)})")
        for m in sorted(ref.maps):
            lines.append(f"- `{Path(m).name}` — `{m}`")

    return "\n".join(lines)
