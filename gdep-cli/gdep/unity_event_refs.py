"""
gdep.unity_event_refs
Unity Event (UnityEvent / Button.onClick) persistent binding analysis.

Unity serializes Inspector-wired event callbacks as:
  m_PersistentCalls:
    m_Calls:
    - m_Target: {fileID: 12345}
      m_TargetAssemblyTypeName: MyClass, Assembly-CSharp
      m_MethodName: OnButtonClick
      m_Mode: 1   (1=void, 2=Object, 3=int, 4=float, 5=string, 6=bool)
      m_Arguments: {...}

This module scans .prefab, .unity, .asset files for these patterns
and builds a map of:  MethodName → [list of binding locations]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Data Models ──────────────────────────────────────────────

@dataclass
class EventBinding:
    """A single Unity Event persistent call binding."""
    method_name:   str
    class_name:    str        # From m_TargetAssemblyTypeName
    source_asset:  str        # Relative path of the .prefab/.unity/.asset
    component:     str = ""   # Component name if parseable from context
    mode:          int = 0    # UnityEventCallState (1=void, 2=Object, etc.)


@dataclass
class UnityEventMap:
    """Project-wide map of all Unity Event bindings."""
    assets_root: Path
    # method_name → list of bindings
    method_bindings: dict[str, list[EventBinding]] = field(default_factory=dict)
    # class_name → list of bindings (for class-centric lookup)
    class_bindings:  dict[str, list[EventBinding]] = field(default_factory=dict)

    def get_by_method(self, method_name: str) -> list[EventBinding]:
        return self.method_bindings.get(method_name, [])

    def get_by_class(self, class_name: str) -> list[EventBinding]:
        return self.class_bindings.get(class_name, [])

    @property
    def total_bindings(self) -> int:
        return sum(len(v) for v in self.method_bindings.values())


# ── YAML Parsing Patterns ───────────────────────────────────

# Matches a single m_Calls entry block
# Extracts: m_TargetAssemblyTypeName, m_MethodName, m_Mode
_CALL_BLOCK_PAT = re.compile(
    r'm_TargetAssemblyTypeName:\s*([^\n,]+),\s*([^\n]+)\s*\n'
    r'.*?m_MethodName:\s*(\S+)',
    re.DOTALL
)

# Alternative: find all m_MethodName values + nearby type info
_METHOD_PAT   = re.compile(r'm_MethodName:\s*(\S+)')
_TYPE_PAT     = re.compile(r'm_TargetAssemblyTypeName:\s*([^\n,]+)')
_MODE_PAT     = re.compile(r'm_Mode:\s*(\d+)')

# Marks the start of a PersistentCall entry
_CALLS_SECTION = re.compile(r'm_PersistentCalls:.*?m_Calls:', re.DOTALL)
_CALL_ENTRY    = re.compile(r'-\s+m_Target:.*?(?=-\s+m_Target:|\Z)', re.DOTALL)


def _parse_persistent_calls(text: str) -> list[dict]:
    """
    Parse all m_PersistentCalls sections from a Unity YAML file.
    Returns list of {method_name, class_name, mode} dicts.
    """
    results = []

    # Find all m_PersistentCalls blocks
    # Strategy: split on "m_PersistentCalls:" and parse each block
    parts = text.split("m_PersistentCalls:")
    for part in parts[1:]:
        # Get the m_Calls: sub-section (until next top-level key)
        calls_start = part.find("m_Calls:")
        if calls_start == -1:
            continue

        calls_block = part[calls_start:]
        # End at next same-level key (lines that don't start with spaces)
        lines = calls_block.splitlines()
        call_lines = []
        for line in lines[1:]:  # skip "m_Calls:" itself
            if line and not line[0].isspace() and line[0] != "-":
                break
            call_lines.append(line)

        block_text = "\n".join(call_lines)

        # Find individual call entries
        entries = block_text.split("  - m_Target:")
        for entry in entries[1:]:  # skip first empty
            method_m = _METHOD_PAT.search(entry)
            type_m   = _TYPE_PAT.search(entry)
            mode_m   = _MODE_PAT.search(entry)

            if method_m and type_m:
                raw_type = type_m.group(1).strip()
                # "ClassName, Assembly-Name" → "ClassName"
                class_name = raw_type.split(",")[0].strip()
                method = method_m.group(1).strip()

                # Skip empty / Unity internal
                if method and method != "0" and class_name:
                    results.append({
                        "method_name": method,
                        "class_name":  class_name,
                        "mode":        int(mode_m.group(1)) if mode_m else 0,
                    })

    return results


# ── File Scanner ─────────────────────────────────────────────

_IGNORE_DIRS = {"Library", "Temp", "obj", "Packages", "node_modules", ".git"}


def _should_skip(path: Path) -> bool:
    return any(part in _IGNORE_DIRS for part in path.parts)


def _scan_asset_file(asset_path: Path, assets_root: Path,
                     event_map: UnityEventMap) -> int:
    """Scan a single .prefab/.unity/.asset file for event bindings. Returns count added."""
    try:
        text = asset_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0

    if "m_PersistentCalls" not in text:
        return 0

    try:
        rel_path = str(asset_path.relative_to(assets_root.parent))
    except ValueError:
        rel_path = asset_path.name

    calls = _parse_persistent_calls(text)
    added = 0
    for call in calls:
        binding = EventBinding(
            method_name=call["method_name"],
            class_name=call["class_name"],
            source_asset=rel_path,
            mode=call["mode"],
        )
        # Index by method
        event_map.method_bindings.setdefault(binding.method_name, []).append(binding)
        # Index by class
        event_map.class_bindings.setdefault(binding.class_name, []).append(binding)
        added += 1

    return added


# ── Public API ───────────────────────────────────────────────

def find_assets_root(project_path: str) -> Path | None:
    """Find the Assets/ directory from any path within a Unity project."""
    p = Path(project_path).resolve()
    for candidate in [p] + list(p.parents):
        if candidate.name == "Assets" and candidate.is_dir():
            return candidate
        assets = candidate / "Assets"
        if assets.is_dir():
            return assets
    return None


def build_event_map(project_path: str,
                    progress_cb=None) -> UnityEventMap | None:
    """
    Scan all .prefab, .unity, .asset files and build the complete event binding map.

    Args:
        project_path: Unity project root, Assets folder, or Scripts folder.
        progress_cb:  Optional (current, total) progress callback.

    Returns:
        UnityEventMap or None if the project root cannot be determined.
    """
    assets_root = find_assets_root(project_path)
    if assets_root is None:
        return None

    event_map = UnityEventMap(assets_root=assets_root)

    # Collect target files
    asset_files: list[Path] = []
    for ext in ("*.prefab", "*.unity", "*.asset"):
        for f in assets_root.rglob(ext):
            if not _should_skip(f):
                asset_files.append(f)

    total = len(asset_files)
    for i, asset_file in enumerate(asset_files):
        if progress_cb:
            progress_cb(i + 1, total)
        _scan_asset_file(asset_file, assets_root, event_map)

    return event_map


# ── Result Formatting ─────────────────────────────────────────

def format_event_result(event_map: UnityEventMap | None,
                        method_name: str | None = None) -> str:
    """Format event binding results as a readable string for the MCP tool."""
    if event_map is None:
        return "Could not find Unity Assets root. Is this a Unity project?"

    if event_map.total_bindings == 0:
        return "No Unity Event bindings found in this project."

    lines: list[str] = []

    if method_name:
        # Single method lookup
        bindings = event_map.get_by_method(method_name)
        if not bindings:
            lines.append(f"No Unity Event bindings found for method `{method_name}`.")
            lines.append(
                "Note: This method may only be called from code, not from Inspector bindings."
            )
        else:
            lines.append(f"## Unity Event Bindings for `{method_name}`")
            lines.append(f"Found in {len(bindings)} Inspector binding(s):\n")
            for b in bindings:
                lines.append(f"- **{b.class_name}.{b.method_name}**")
                lines.append(f"  Asset: `{b.source_asset}`")
                if b.mode:
                    mode_names = {1:"void",2:"Object",3:"int",4:"float",5:"string",6:"bool"}
                    lines.append(f"  Argument type: {mode_names.get(b.mode, f'mode {b.mode}')}")
    else:
        # Full summary
        lines.append("## Unity Event Bindings Summary")
        lines.append(f"Total bindings: {event_map.total_bindings}")
        lines.append(f"Unique methods: {len(event_map.method_bindings)}")
        lines.append(f"Unique classes: {len(event_map.class_bindings)}\n")

        lines.append("### All Bound Methods (sorted by binding count)")
        sorted_methods = sorted(
            event_map.method_bindings.items(),
            key=lambda x: len(x[1]), reverse=True
        )
        for meth, binds in sorted_methods[:50]:
            classes = list({b.class_name for b in binds})
            assets  = list({b.source_asset for b in binds})
            lines.append(
                f"- `{meth}` — {len(binds)} binding(s) "
                f"in {len(assets)} asset(s), class(es): {', '.join(classes[:3])}"
            )
        if len(sorted_methods) > 50:
            lines.append(f"... and {len(sorted_methods)-50} more methods")

    return "\n".join(lines)
