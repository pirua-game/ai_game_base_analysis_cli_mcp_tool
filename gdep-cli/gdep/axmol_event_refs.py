"""
gdep.axmol_event_refs
Axmol Engine EventDispatcher callback binding analysis.

Parses C++ source files for:
  - addEventListenerWithSceneGraphPriority(listener, this, priority)
  - addEventListenerWithFixedPriority(listener, priority)
  - CC_CALLBACK_0/1/2/3(ClassName::method, this) macros
  - schedule(CC_SCHEDULE_SELECTOR(ClassName::method)) / scheduleOnce / scheduleUpdate

Output: callback binding map { caller_class: [{ event_type, callback_method, target_class }] }
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Data Models ──────────────────────────────────────────────

@dataclass
class AxmolBinding:
    """A single Axmol event/schedule callback binding."""
    caller_class:    str   # Class that registers the listener/schedule
    event_type:      str   # e.g. "EventListener(SceneGraphPriority)", "schedule", "scheduleUpdate"
    callback_method: str   # e.g. "onTouchBegan", "update", "tick"
    target_class:    str   # Class that contains the callback method
    source_file:     str   # Relative path of the source file
    line_number:     int = 0


@dataclass
class AxmolEventMap:
    """Project-wide map of all Axmol event/schedule bindings."""
    source_root: Path
    # caller_class -> list of bindings
    class_bindings: dict[str, list[AxmolBinding]] = field(default_factory=dict)

    def get_by_class(self, class_name: str) -> list[AxmolBinding]:
        return self.class_bindings.get(class_name, [])

    @property
    def total_bindings(self) -> int:
        return sum(len(v) for v in self.class_bindings.values())


# ── Regex Patterns ───────────────────────────────────────────

# Function implementation at line start: "ReturnType ClassName::method("
# (more reliable than inline calls like EventListenerXxx::create())
_IMPL_FUNC_PAT = re.compile(
    r'^[\w:*&\s]+\s+(\w+)::(\w+)\s*\(',
    re.MULTILINE
)

# Fallback: any ClassName::MethodName( in context
_IMPL_PAT = re.compile(r'\b(\w+)::(\w+)\s*\(')

# CC_CALLBACK_N(ClassName::method, this)
_CC_CALLBACK_PAT = re.compile(
    r'CC_CALLBACK_(\d)\s*\(\s*(\w+)::(\w+)\s*,\s*this'
)

# addEventListenerWithSceneGraphPriority / addEventListenerWithFixedPriority
_ADD_LISTENER_PAT = re.compile(
    r'addEventListenerWith(SceneGraphPriority|FixedPriority)\s*\('
)

# schedule / scheduleOnce with CC_SCHEDULE_SELECTOR
_SCHEDULE_CALL_PAT = re.compile(
    r'\bschedule(?:Once)?\s*\(\s*CC_SCHEDULE_SELECTOR\s*\(\s*(\w+)::(\w+)\s*\)'
)

# standalone scheduleUpdate()
_SCHEDULE_UPDATE_PAT = re.compile(r'\bscheduleUpdate\s*\(\s*\)')

# CC_SCHEDULE_SELECTOR alone (for cases not matched by _SCHEDULE_CALL_PAT)
_SCHEDULE_SELECTOR_PAT = re.compile(
    r'CC_SCHEDULE_SELECTOR\s*\(\s*(\w+)::(\w+)\s*\)'
)


# ── Helper: guess caller class from surrounding context ──────

def _caller_class(text: str, pos: int) -> str:
    """
    Guess the containing class by scanning backward for function implementations.

    Strategy:
    1. Prefer ClassName::method( patterns at line-start (actual implementations).
    2. Fall back to any ClassName::method( if no line-start match found.
    Searches within the preceding 800 characters.
    """
    region = text[max(0, pos - 800):pos]

    # Prefer implementation patterns (at line start with return type)
    impl_matches = list(_IMPL_FUNC_PAT.finditer(region))
    if impl_matches:
        return impl_matches[-1].group(1)

    # Fallback: any ClassName:: pattern
    all_matches = list(_IMPL_PAT.finditer(region))
    if all_matches:
        return all_matches[-1].group(1)

    return ""


def _pos_to_line(line_starts: list[int], pos: int) -> int:
    """Binary search to convert character position to 1-based line number."""
    lo, hi = 0, len(line_starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_starts[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _build_line_index(text: str) -> list[int]:
    """Return list of character positions where each line starts."""
    starts = [0]
    for i, ch in enumerate(text):
        if ch == '\n':
            starts.append(i + 1)
    return starts


# ── File Parser ──────────────────────────────────────────────

def _parse_file(src_file: Path, source_root: Path) -> list[AxmolBinding]:
    """Parse a single C++ source file for Axmol event bindings."""
    try:
        text = src_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    try:
        rel_path = str(src_file.relative_to(source_root))
    except ValueError:
        rel_path = src_file.name

    line_starts = _build_line_index(text)
    bindings: list[AxmolBinding] = []

    # 1. CC_CALLBACK_N bindings
    #    These appear as arguments to addEventListenerWith*, so we check whether
    #    a listener registration is nearby (within +/-600 chars around the macro).
    for m in _CC_CALLBACK_PAT.finditer(text):
        n, target_cls, method = m.group(1), m.group(2), m.group(3)
        caller = _caller_class(text, m.start()) or target_cls

        # Check if addEventListenerWith* appears within 600 chars before OR after
        window_start = max(0, m.start() - 600)
        window_end   = min(len(text), m.end() + 600)
        window = text[window_start:window_end]
        listener_m = _ADD_LISTENER_PAT.search(window)
        if listener_m:
            event_type = f"EventListener({listener_m.group(1)})"
        else:
            event_type = f"CC_CALLBACK_{n}"

        bindings.append(AxmolBinding(
            caller_class=caller,
            event_type=event_type,
            callback_method=method,
            target_class=target_cls,
            source_file=rel_path,
            line_number=_pos_to_line(line_starts, m.start()),
        ))

    # 2. schedule / scheduleOnce with CC_SCHEDULE_SELECTOR
    for m in _SCHEDULE_CALL_PAT.finditer(text):
        target_cls, method = m.group(1), m.group(2)
        caller = _caller_class(text, m.start()) or target_cls
        bindings.append(AxmolBinding(
            caller_class=caller,
            event_type="schedule",
            callback_method=method,
            target_class=target_cls,
            source_file=rel_path,
            line_number=_pos_to_line(line_starts, m.start()),
        ))

    # 3. scheduleUpdate() -- implicit update() callback
    for m in _SCHEDULE_UPDATE_PAT.finditer(text):
        caller = _caller_class(text, m.start())
        if caller:
            bindings.append(AxmolBinding(
                caller_class=caller,
                event_type="scheduleUpdate",
                callback_method="update",
                target_class=caller,
                source_file=rel_path,
                line_number=_pos_to_line(line_starts, m.start()),
            ))

    return bindings


# ── Scanner ──────────────────────────────────────────────────

_IGNORE_DIRS = {
    "build", "cmake-build-debug", "cmake-build-release", "obj",
    ".git", "node_modules", ".gdep", "ax", "cocos2d",
}


def _should_skip(path: Path) -> bool:
    return any(part in _IGNORE_DIRS for part in path.parts)


# ── Public API ───────────────────────────────────────────────

def build_event_map(source_path: str) -> AxmolEventMap:
    """
    Scan all C++ source files and build the complete Axmol event binding map.

    Args:
        source_path: Axmol project root or source directory (e.g. Classes/).

    Returns:
        AxmolEventMap containing all detected event/schedule bindings.
    """
    root = Path(source_path).resolve()
    event_map = AxmolEventMap(source_root=root)

    src_files: list[Path] = []
    for ext in ("*.cpp", "*.h", "*.hpp", "*.cc"):
        for f in root.rglob(ext):
            if not _should_skip(f):
                src_files.append(f)

    for src_file in src_files:
        for binding in _parse_file(src_file, root):
            event_map.class_bindings.setdefault(binding.caller_class, []).append(binding)

    return event_map


# ── Formatting ───────────────────────────────────────────────

def format_event_result(event_map: AxmolEventMap,
                        class_name: str | None = None) -> str:
    """Format Axmol event binding results as a readable string for the MCP tool."""
    if event_map.total_bindings == 0:
        return "No Axmol event/schedule bindings found in this project."

    lines: list[str] = []

    if class_name:
        bindings = event_map.get_by_class(class_name)
        if not bindings:
            lines.append(f"No Axmol event bindings found for class `{class_name}`.")
            lines.append(
                "Note: this class may register no listeners, or the source was not found."
            )
        else:
            lines.append(f"## Axmol Event Bindings for `{class_name}`")
            lines.append(f"Found {len(bindings)} binding(s):\n")
            for b in bindings:
                lines.append(
                    f"- **{b.event_type}**: `{b.target_class}::{b.callback_method}`"
                )
                lines.append(
                    f"  File: `{b.source_file}`  line {b.line_number}"
                )
    else:
        lines.append("## Axmol Event Bindings Summary")
        lines.append(f"Total bindings : {event_map.total_bindings}")
        lines.append(f"Unique classes : {len(event_map.class_bindings)}\n")

        lines.append("### Bindings by Class")
        for cls, cls_bindings in sorted(event_map.class_bindings.items()):
            if not cls:
                continue
            lines.append(f"\n**{cls}** ({len(cls_bindings)} binding(s))")
            for b in cls_bindings[:15]:
                lines.append(
                    f"  - [{b.event_type}] "
                    f"{b.target_class}::{b.callback_method}"
                    f"  ({b.source_file}:{b.line_number})"
                )
            if len(cls_bindings) > 15:
                lines.append(f"  ... and {len(cls_bindings) - 15} more")

    return "\n".join(lines)
