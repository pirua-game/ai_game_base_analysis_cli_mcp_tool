"""
gdep.cpp_runner
Standard C++ project analysis runner.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cpp_parser import (
    CPPProject,
    compute_coupling,
    find_cycles,
    to_class_map,
)

try:
    from .cpp_ts_parser import parse_project  # Tree-sitter (default)
    _TS_AVAILABLE = True
except ImportError:
    from .cpp_parser import parse_project as _parse_project_regex  # type: ignore
    _TS_AVAILABLE = False
    def parse_project(root_path: str, deep: bool = False):  # type: ignore
        return _parse_project_regex(root_path)
from .analyzer.linter import Linter


@dataclass
class RunResult:
    ok:     bool
    stdout: str
    stderr: str = ""
    data:   Any = None

    @property
    def error_message(self) -> str:
        return self.stderr or "Error"


# ── Cache ────────────────────────────────────────────────────
_PROJECT_CACHE: dict[str, Any] = {}


def _get_project(src: str, deep: bool = False):
    cache_key = f"{src}_{deep}"
    if cache_key not in _PROJECT_CACHE:
        _PROJECT_CACHE[cache_key] = parse_project(src, deep=deep)
    return _PROJECT_CACHE[cache_key]


def clear_cache(src: str | None = None):
    if src:
        keys_to_del = [k for k in _PROJECT_CACHE if k.startswith(src)]
        for k in keys_to_del:
            _PROJECT_CACHE.pop(k, None)
    else:
        _PROJECT_CACHE.clear()


# ── scan ─────────────────────────────────────────────────────

def scan(src: str, top: int = 20, circular: bool = True, dead_code: bool = False, include_refs: bool = False, fmt: str = "console", deep: bool = False) -> RunResult:
    try:
        proj     = _get_project(src, deep=deep)
        coupling = compute_coupling(proj)
        cycles   = find_cycles(proj) if circular else []

        # Orphan nodes (Dead Code)
        dead_nodes = [c for c in coupling if c['score'] == 0]
        active_coupling = [c for c in coupling if c['score'] > 0]

        data = {
            "summary": {
                "path": src,
                "fileCount": len(set(c.source_file for c in list(proj.classes.values()) + list(proj.structs.values()))),
                "classCount": len(proj.classes),
                "structCount": len(proj.structs),
                "enumCount": len(proj.enums),
                "deadCount": len(dead_nodes),
            },
            "coupling": active_coupling[:top],
            "deadNodes": dead_nodes,
            "cycles": cycles,
        }

        if fmt == "json":
            return RunResult(ok=True, stdout=json.dumps(data, indent=2, ensure_ascii=False), data=data)

        # Console output
        total_files = data["summary"]["fileCount"]
        lines = [
            f"┌─ C++ scan results {'─'*50}┐",
            f"│ Path:   {src}",
            f"│ Files:  {total_files}  |  Classes: {len(proj.classes)}  |  "
            f"Structs: {len(proj.structs)}  |  Enums: {len(proj.enums)}",
            f"│ Orphan Nodes: {len(dead_nodes)} found",
            f"└{'─'*60}┘",
            "",
            f"── Top Classes by Coupling (in-degree, top {top}) ──",
            f"  {'Rank':<4} {'Class':<40} {'Score':>5}",
            "  " + "─" * 55,
        ]
        for rank, item in enumerate(active_coupling[:top], 1):
            lines.append(f"  {rank:<4} {item['name']:<40} {item['score']:>5}")

        lines += ["", "── Circular Dependency Detection ──"]
        if cycles:
            for c in cycles[:20]:
                lines.append(f"  ↻ {c}")
        else:
            lines.append("  No circular dependencies found")

        if dead_code:
            lines += ["", "── [Dead Code] Unreferenced Classes (Ref count: 0) ──"]
            if not dead_nodes:
                lines.append("  No orphan nodes found")
            else:
                lines.append(f"  {'Class':<40} {'File':<25}")
                lines.append("  " + "─" * 65)
                for d in dead_nodes:
                    lines.append(f"  {d['name']:<40} {Path(d['file']).name:<25}")

        return RunResult(ok=True, stdout="\n".join(lines), data=data)
    except Exception as e:
        import traceback
        return RunResult(ok=False, stdout="", stderr=f"{str(e)}\n{traceback.format_exc()}")


# ── describe ─────────────────────────────────────────────────

def describe(src: str, class_name: str) -> RunResult:
    try:
        from .cpp_ts_parser import _normalize_cpp_type
        clear_cache(src)
        proj = _get_project(src, deep=True)
        all_items = {**proj.classes, **proj.structs, **proj.enums}

        norm_name = _normalize_cpp_type(class_name)
        cls = all_items.get(norm_name) or all_items.get(class_name)

        if not cls:
            for k, v in all_items.items():
                if k.lower() == norm_name.lower() or k.lower() == class_name.lower():
                    cls = v
                    break

        if not cls:
            return RunResult(ok=False, stdout="",
                             stderr=f"Could not find class `{class_name}`.")

        lines = [
            f"── {cls.kind.upper()}: {class_name} ──",
            f"  File: {cls.source_file}",
        ]
        if cls.namespace:
            lines.append(f"  Namespace: {cls.namespace}")
        if cls.bases:
            lines.append(f"  Inheritance: {', '.join(cls.bases)}")

        if cls.kind == "enum":
            lines += ["", "── Enum Values ──"]
            for v in cls.enum_values:
                lines.append(f"  • {v}")
            return RunResult(ok=True, stdout="\n".join(lines))

        lines += ["", f"── Fields ({len(cls.properties)} items) ──"]
        for p in cls.properties[:40]:
            static = " static" if p.is_static else ""
            const  = " const" if p.is_const else ""
            lines.append(f"  {p.access:10} {p.type_:30} {p.name}{static}{const}")

        lines += ["", f"── Methods ({len(cls.functions)} items) ──"]
        for f in cls.functions[:40]:
            virt = " virtual"  if f.is_virtual  else ""
            ovr  = " override" if f.is_override else ""
            stat = " static" if f.is_static else ""
            cnst = " const" if f.is_const else ""
            lines.append(f"  {f.access:10} {f.return_type:15} {f.name}(){virt}{ovr}{stat}{cnst}")

        if cls.dependencies:
            lines += ["", f"── Behavioral Dependencies (--deep, {len(cls.dependencies)} items) ──"]
            for d in sorted(cls.dependencies)[:40]:
                lines.append(f"  • {d}")

        return RunResult(ok=True, stdout="\n".join(lines))
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── flow ─────────────────────────────────────────────────────

def flow(
    src:           str,
    class_name:    str,
    method_name:   str,
    depth:         int = 3,
    focus_classes: list[str] | None = None,
    fmt:           str = "json",
) -> RunResult:
    # TODO: flow analysis logic for standard C++ (if needed)
    return RunResult(ok=False, stdout="", stderr="Standard C++ flow analysis is not yet supported.")


# ── read_source ───────────────────────────────────────────────

def read_source(src: str, class_name: str, max_chars: int = 8000) -> RunResult:
    try:
        proj = _get_project(src)
        all_items = {**proj.classes, **proj.structs, **proj.enums}
        cls = all_items.get(class_name)
        if not cls:
            return RunResult(ok=False, stdout="",
                             stderr=f"Could not find class `{class_name}`.")

        source_path = Path(cls.source_file)
        # If header, attempt to find matching source file
        parts = []
        if source_path.exists():
            parts.append(f"// ── {source_path.name} ──\n" + source_path.read_text(encoding='utf-8', errors='replace'))

            if source_path.suffix in ('.h', '.hpp', '.hxx'):
                for ext in ('.cpp', '.cc', '.cxx'):
                    cpp_path = source_path.with_suffix(ext)
                    if cpp_path.exists():
                        parts.append(f"// ── {cpp_path.name} ──\n" + cpp_path.read_text(encoding='utf-8', errors='replace'))
                        break

        content = "\n\n".join(parts)
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... ({len(content)} chars total, showing first {max_chars})"

        return RunResult(ok=True, stdout=content)
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── impact ───────────────────────────────────────────────────

def impact(src: str, target_class: str, depth: int = 3) -> RunResult:
    try:
        from .analyzer.impact_analyzer import ImpactAnalyzer
        from .cpp_ts_parser import _normalize_cpp_type

        # Use deep=True to get more accurate dependencies if available
        proj = _get_project(src, deep=True)

        # Normalize target class name
        norm_name = _normalize_cpp_type(target_class)
        all_items = {**proj.classes, **proj.structs, **proj.enums}
        actual_name = norm_name if norm_name in all_items else target_class

        analyzer = ImpactAnalyzer(proj)
        impact_tree = analyzer.trace_impact(actual_name, max_depth=depth)

        lines = [
            f"── Impact Analysis: {actual_name} (Depth: {depth}) ──",
            "",
        ]

        tree_lines = analyzer.format_as_tree(impact_tree)
        lines.extend(tree_lines)

        if len(tree_lines) <= 1:
            lines.append("  (No impacted classes found)")

        return RunResult(ok=True, stdout="\n".join(lines), data=impact_tree)
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── lint ─────────────────────────────────────────────────────

def lint(src: str, fmt: str = "console") -> RunResult:
    """
    C++ project anti-pattern linting.
    """
    try:
        clear_cache(src)
        proj = _get_project(src, deep=True)

        linter = Linter()
        # For now, standard CPP uses circular dependency check primarily
        # UE5 rules are skipped if not a UE5 project (project is CPPProject here)
        results = []

        # General checks for standard CPP
        linter._check_circular_dependencies(proj)
        results = linter.results

        if fmt == "json":
            data = [vars(r) for r in results]
            return RunResult(ok=True, stdout=json.dumps(data, indent=2, ensure_ascii=False), data=data)

        if not results:
            return RunResult(ok=True, stdout="✓ No anti-patterns detected.")

        lines = [
            f"┌─ C++ Anti-pattern Scanner Results {'─'*35}┐",
            f"│ Path:   {src}",
            f"│ Found:  {len(results)} issues",
            f"└{'─'*60}┘",
            "",
        ]

        for r in results:
            color_bullet = "!" if r.severity == "Warning" else "•"
            header = f"{color_bullet} [{r.severity:7}] {r.class_name}"
            lines.append(header)
            lines.append(f"  {r.message}")
            if r.suggestion:
                lines.append(f"  Suggestion: {r.suggestion}")
            lines.append("")

        return RunResult(ok=True, stdout="\n".join(lines), data=[vars(r) for r in results])
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))
