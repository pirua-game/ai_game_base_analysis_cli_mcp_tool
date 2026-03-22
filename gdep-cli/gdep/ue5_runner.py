"""
gdep.ue5_runner
UE5 project analysis runner.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ue5_parser import (
    UE5Project,
    compute_coupling,
    find_cycles,
    to_class_map,
)

# ── Module-level BP map cache (invalidated when Content mtime changes) ──────
_bp_map_cache: dict[str, Any] = {}   # key: content_root str → {"mtime": float, "bp_map": ...}
try:
    from .ue5_ts_parser import parse_project  # Tree-sitter (default)
    _TS_AVAILABLE = True
except ImportError:
    from .ue5_parser import parse_project as _parse_project_regex  # type: ignore
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

# ── Disk Cache (mtime-based) ──────────────────────────────────

def _get_src_fingerprint(src: str) -> str:
    """Fast MD5 fingerprint of .h/.cpp mtimes using os.scandir."""
    root = Path(src)
    mtimes = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.name.endswith((".h", ".cpp")):
                        try:
                            mtimes.append(f"{entry.path}:{entry.stat().st_mtime_ns}")
                        except OSError:
                            pass
        except PermissionError:
            pass
    mtimes.sort()
    return hashlib.md5("\n".join(mtimes).encode()).hexdigest()


def _split_src_tag(src: str) -> tuple[str, str]:
    """Split 'C:/path/to/src:tagname' into ('C:/path/to/src', 'tagname').
    Handles Windows drive letters (C:, D:, F: etc.) correctly."""
    # Find the LAST colon that is NOT a drive letter (i.e., not at index 1)
    idx = src.rfind(":")
    if idx > 1:  # > 1 means it's not a drive letter colon
        return src[:idx], src[idx+1:]
    return src, ""


def _cache_path(src: str, deep: bool, tag: str = "") -> Path:
    clean_src, _ = _split_src_tag(src)
    cache_dir = Path(clean_src).resolve().parent / ".gdep_cache"
    cache_dir.mkdir(exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    prefix = "deep" if deep else "fast"
    return cache_dir / f"ue5_scan_{prefix}{suffix}.json"


def _load_disk_cache(src: str, deep: bool):
    """Return cached scan data if fingerprint matches, else None."""
    clean_src, tag = _split_src_tag(src)
    cp = _cache_path(clean_src, deep, tag)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        if data.get("fingerprint") == _get_src_fingerprint(clean_src):
            return data.get("project")
    except Exception:
        pass
    return None


def _save_disk_cache(src: str, deep: bool, project_data: Any) -> None:
    """Serialize scan data to disk with the current fingerprint."""
    clean_src, tag = _split_src_tag(src)
    try:
        cp = _cache_path(clean_src, deep, tag)
        payload = {
            "fingerprint": _get_src_fingerprint(clean_src),
            "saved_at": time.time(),
            "project": project_data,
        }
        cp.write_text(json.dumps(payload, ensure_ascii=False, default=str),
                      encoding="utf-8")
    except Exception:
        pass


def _get_project(src: str, deep: bool = False):
    """
    Return parsed UE5Project.
    Priority: memory cache → disk cache → fresh parse.
    Disk cache is invalidated when any .h/.cpp mtime changes.
    """
    cache_key = f"{src}_{deep}"

    # 1. Memory cache (fastest — same process lifetime)
    if cache_key in _PROJECT_CACHE:
        return _PROJECT_CACHE[cache_key]

    # 2. Disk cache (survives CLI restarts; invalidated by mtime)
    disk = _load_disk_cache(src, deep)
    if disk is not None:
        # Disk cache stores raw dicts; we need to reconstruct the project object.
        # For now, store and return as-is when the caller only needs JSON-serialisable data.
        # For object-based operations (describe, flow), skip disk cache.
        pass  # fall through to fresh parse for object-based callers

    # 3. Fresh parse
    proj = parse_project(src, deep=deep)
    _PROJECT_CACHE[cache_key] = proj
    return proj


def clear_cache(src: str | None = None):
    if src:
        # Delete all caches related to a specific path
        keys_to_del = [k for k in _PROJECT_CACHE if k.startswith(src)]
        for k in keys_to_del:
            _PROJECT_CACHE.pop(k, None)
    else:
        _PROJECT_CACHE.clear()


# ── scan ─────────────────────────────────────────────────────

def scan(src: str, top: int = 20, circular: bool = True, dead_code: bool = False, include_refs: bool = False, fmt: str = "console", deep: bool = False) -> RunResult:
    try:
        # ── Try scan-level disk cache (mtime-based) ──────────
        # Only for the default (non-include_refs) case since refs are heavy separately.
        scan_cache_key = f"scan_{src}_{deep}_{circular}"
        cached_data = None
        if not include_refs:
            cached_data = _load_disk_cache(src + ":scan", deep)
            if cached_data and isinstance(cached_data, dict):
                # Cache hit — skip parse entirely
                data = cached_data
                proj = None
            else:
                cached_data = None

        if cached_data is None:
            proj     = _get_project(src, deep=deep)
            coupling = compute_coupling(proj)
            cycles   = find_cycles(proj) if circular else []
            dead_nodes   = [c for c in coupling if c['score'] == 0]
            active_coupling = [c for c in coupling if c['score'] > 0]
            data = {
                "summary": {
                    "path": src,
                    "fileCount": len(set(c.source_file for c in list(proj.classes.values()) + list(proj.structs.values()))),
                    "classCount": len(proj.classes),
                    "structCount": len(proj.structs),
                    "enumCount": len(proj.enums),
                    "deadCount": len(dead_nodes),
                    "engineRefApplied": False,
                },
                "coupling": active_coupling,
                "deadNodes": dead_nodes,
                "cycles": cycles,
            }
            if not include_refs:
                _save_disk_cache(src + ":scan", deep, data)
        else:
            dead_nodes = data["deadNodes"]
            active_coupling = data["coupling"]
            cycles = data["cycles"]
            proj = None

        # ── Blueprint back-references (always re-runs, results heavy to cache) ──
        if include_refs:
            from . import ue5_blueprint_refs
            ref_map = ue5_blueprint_refs.build_ref_map(src)
            if ref_map:
                for item in active_coupling:
                    engine_ref = ref_map.get(item["name"])
                    if engine_ref and engine_ref.total > 0:
                        item["score"] += engine_ref.total
                        item["engine_ref"] = engine_ref.total
                active_coupling.sort(key=lambda x: x["score"], reverse=True)
                data["summary"]["engineRefApplied"] = True

        if fmt == "json":
            out_data = dict(data)
            out_data["coupling"] = active_coupling[:top]
            return RunResult(ok=True, stdout=json.dumps(out_data, indent=2, ensure_ascii=False), data=out_data)

        total_files = data["summary"]["fileCount"]
        class_count = data["summary"]["classCount"]
        struct_count = data["summary"]["structCount"]
        enum_count   = data["summary"]["enumCount"]
        ref_hint = " (Engine back-refs included)" if data["summary"].get("engineRefApplied") else ""
        lines = [
            f"┌─ UE5 scan results {'─'*50}┐",
            f"│ Path:   {src}",
            f"│ Files:  {total_files}  |  Classes: {class_count}  |  "
            f"Structs: {struct_count}  |  Enums: {enum_count}",
            f"│ Orphan Nodes: {len(dead_nodes)}{ref_hint} found",
            f"└{'─'*60}┘",
            "",
            f"── Top Classes by Coupling (in-degree, top {top}) ──",
            f"  {'Rank':<4} {'Class':<40} {'Score':>5}",
            "  " + "─" * 55,
        ]
        for rank, item in enumerate(active_coupling[:top], 1):
            engine_hint = f" (+{item['engine_ref']})" if "engine_ref" in item else ""
            lines.append(f"  {rank:<4} {item['name']:<40} {item['score']:>5}{engine_hint}")

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
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── describe ─────────────────────────────────────────────────

def describe(src: str, class_name: str) -> RunResult:
    try:
        from .ue5_ts_parser import _normalize_cpp_type
        # Clear cache and run deep analysis to ensure accurate method body information
        clear_cache(src)
        proj = _get_project(src, deep=True)
        all_items = {**proj.classes, **proj.structs, **proj.enums}

        # Normalize class name (remove A/U prefixes, etc.)
        norm_name = _normalize_cpp_type(class_name)
        cls = all_items.get(norm_name) or all_items.get(class_name)

        if not cls:
            # Case-insensitive fallback search
            for k, v in all_items.items():
                if k.lower() == norm_name.lower() or k.lower() == class_name.lower():
                    cls = v
                    break

        if not cls:
            return RunResult(ok=False, stdout="",
                             stderr=f"Could not find class `{class_name}` (Normalized: {norm_name}).")

        lines = [
            f"── {cls.kind.upper()}: {class_name} ──",
            f"  File: {cls.source_file}",
        ]
        if cls.specifiers:
            lines.append(f"  UE Specifiers: {', '.join(cls.specifiers)}")
        if cls.bases:
            lines.append(f"  Inheritance: {', '.join(cls.bases)}")
        if cls.module_api:
            lines.append(f"  Module API: {cls.module_api}")

        if cls.kind == "enum":
            lines += ["", "── Enum Values ──"]
            for v in cls.enum_values:
                lines.append(f"  • {v}")
            return RunResult(ok=True, stdout="\n".join(lines))

        lines += ["", f"── UPROPERTY ({len(cls.properties)} items) ──"]
        for p in cls.properties[:40]:
            repl  = " [Replicated]" if p.is_replicated else ""
            specs = f"  [{', '.join(p.specifiers[:3])}]" if p.specifiers else ""
            lines.append(f"  {p.access:10} {p.type_:30} {p.name}{specs}{repl}")

        lifecycle = [f for f in cls.functions if f.is_lifecycle]
        others    = [f for f in cls.functions if not f.is_lifecycle]

        if lifecycle:
            lines += ["", f"── Lifecycle Methods ({len(lifecycle)} items) ──"]
            for f in lifecycle:
                specs = f"  [{', '.join(f.specifiers[:2])}]" if f.specifiers else ""
                lines.append(f"  ⚡ {f.access:10} {f.return_type:15} {f.name}(){specs}")

        if others:
            lines += ["", f"── General Methods ({len(others)} items) ──"]
            for f in others[:30]:
                uf   = f"  [UF:{', '.join(f.specifiers[:2])}]" if f.specifiers else ""
                virt = " virtual"  if f.is_virtual  else ""
                ovr  = " override" if f.is_override else ""
                lines.append(f"  {f.access:10} {f.return_type:15} {f.name}(){uf}{virt}{ovr}")

        if cls.dependencies:
            lines += ["", f"── Behavioral Dependencies (--deep, {len(cls.dependencies)} items) ──"]
            for d in sorted(cls.dependencies)[:40]:
                lines.append(f"  • {d}")

        # ── Blueprint implementations (C++ → BP reverse mapping) ────────
        try:
            from .ue5_blueprint_mapping import build_bp_map, format_cpp_to_bps
            from .ue5_blueprint_refs import find_content_root

            # Use module-level cache keyed by content_root path.
            # Invalidate when Content directory mtime changes.
            content_root = find_content_root(src)
            bp_map = None
            if content_root and content_root.exists():
                cr_key   = str(content_root)
                cr_mtime = content_root.stat().st_mtime
                cached   = _bp_map_cache.get(cr_key)
                if cached and cached["mtime"] == cr_mtime:
                    bp_map = cached["bp_map"]
                else:
                    bp_map = build_bp_map(src)
                    _bp_map_cache[cr_key] = {"mtime": cr_mtime, "bp_map": bp_map}

            if bp_map:
                candidates = [class_name]
                for prefix in ('A', 'U', 'F', 'I', 'E'):
                    if class_name.startswith(prefix):
                        candidates.append(class_name[1:])
                    else:
                        candidates.append(prefix + class_name)
                bps = []
                seen: set[str] = set()
                for c in candidates:
                    for m in bp_map.cpp_to_bps.get(c, []):
                        if m.bp_class not in seen:
                            seen.add(m.bp_class)
                            bps.append(m)
                if bps:
                    lines += [""]
                    lines.append(format_cpp_to_bps(class_name, bps))
        except Exception:
            pass  # BP mapping is best-effort; never fail describe

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
    """
    UE5-specific flow analysis.
    Prevents false positives from BindAction / delegate patterns.
    """
    try:
        from .ue5_flow import flow_to_json
        data = flow_to_json(src, class_name, method_name,
                            max_depth=depth,
                            focus_classes=focus_classes)
        stdout = json.dumps(data, ensure_ascii=False, indent=2)
        return RunResult(ok=True, stdout=stdout, data=data)
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── read_source ───────────────────────────────────────────────

def read_source(src: str, class_name: str, max_chars: int = 8000) -> RunResult:
    try:
        proj = _get_project(src)
        all_items = {**proj.classes, **proj.structs, **proj.enums}
        cls = all_items.get(class_name)
        if not cls:
            return RunResult(ok=False, stdout="",
                             stderr=f"Could not find class `{class_name}`.")

        source_h   = Path(cls.source_file)
        source_cpp = source_h.with_suffix('.cpp')

        parts = []
        if source_h.exists():
            parts.append(
                f"// ── {source_h.name} ──\n"
                + source_h.read_text(encoding='utf-8', errors='replace')
            )
        if source_cpp.exists():
            parts.append(
                f"// ── {source_cpp.name} ──\n"
                + source_cpp.read_text(encoding='utf-8', errors='replace')
            )

        content = "\n\n".join(parts)
        if len(content) > max_chars:
            content = (content[:max_chars]
                       + f"\n\n... ({len(content)} chars total, showing first {max_chars})")

        return RunResult(ok=True, stdout=content)
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))


# ── impact ───────────────────────────────────────────────────

def impact(src: str, target_class: str, depth: int = 3) -> RunResult:
    try:
        from .analyzer.impact_analyzer import ImpactAnalyzer
        from .ue5_ts_parser import _normalize_cpp_type

        # Use deep=True to get more accurate dependencies if available
        proj = _get_project(src, deep=True)

        # Normalize target class name
        norm_name = _normalize_cpp_type(target_class)
        all_items = {**proj.classes, **proj.structs, **proj.enums}

        actual_name = target_class
        if norm_name in all_items:
            actual_name = norm_name
        elif target_class in all_items:
            actual_name = target_class
        else:
            # Fallback search for name without prefix or with prefix
            found = False
            for k in all_items.keys():
                if k.lower() == norm_name.lower() or k.lower() == target_class.lower():
                    actual_name = k
                    found = True
                    break

            if not found:
                # Try prefix-insensitive search (ARPlayerCharacter -> AARPlayerCharacter)
                for k in all_items.keys():
                    for prefix in ('A', 'U', 'F', 'I', 'E', 'T'):
                        if k == prefix + norm_name or k == prefix + target_class:
                            actual_name = k
                            found = True
                            break
                    if found: break

        analyzer = ImpactAnalyzer(proj)

        # Inject Blueprint dependencies
        from . import ue5_blueprint_refs
        ref_map = ue5_blueprint_refs.build_ref_map(src)
        if ref_map:
            for name in all_items.keys():
                ref = ref_map.get(name)
                if ref:
                    for usage in ref.usages:
                        asset_name = Path(usage).stem
                        # Add as external impact: name (C++ class) -> asset_name (Blueprint)
                        analyzer.add_external_impact(name, asset_name, usage)

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
    UE5-specific anti-pattern linting.
    Requires deep=True to analyze method bodies.
    """
    try:
        # Clear cache to ensure we get a fresh deep analysis for method bodies
        clear_cache(src)
        proj = _get_project(src, deep=True)

        linter = Linter()
        results = linter.lint_ue5(proj)

        if fmt == "json":
            # Convert LintResult objects to dicts
            data = [vars(r) for r in results]
            return RunResult(ok=True, stdout=json.dumps(data, indent=2, ensure_ascii=False), data=data)

        # Console output
        if not results:
            return RunResult(ok=True, stdout="✓ No anti-patterns detected.")

        lines = [
            f"┌─ UE5 Anti-pattern Scanner Results {'─'*34}┐",
            f"│ Path:   {src}",
            f"│ Found:  {len(results)} issues",
            f"└{'─'*60}┘",
            "",
        ]

        # Sort by severity (Error -> Warning -> Info) and then by Class
        severity_map = {"Error": 0, "Warning": 1, "Info": 2}
        sorted_results = sorted(results, key=lambda x: (severity_map.get(x.severity, 3), x.class_name))

        for r in sorted_results:
            color_bullet = "×" if r.severity == "Error" else "!" if r.severity == "Warning" else "•"
            header = f"{color_bullet} [{r.severity:7}] {r.class_name}.{r.method_name}" if r.method_name else f"{color_bullet} [{r.severity:7}] {r.class_name}"
            lines.append(header)
            lines.append(f"  {r.message}")
            if r.suggestion:
                lines.append(f"  Suggestion: {r.suggestion}")
            if r.file_path:
                lines.append(f"  File: {Path(r.file_path).name}")
            lines.append("")

        return RunResult(ok=True, stdout="\n".join(lines), data=[vars(r) for r in results])
    except Exception as e:
        return RunResult(ok=False, stdout="", stderr=str(e))
