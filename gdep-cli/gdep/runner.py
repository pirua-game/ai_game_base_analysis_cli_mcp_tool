"""
gdep.runner
Integrated caller for gdep.exe (C#) and cpp_runner (C++).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .detector import ProjectKind, ProjectProfile

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


@dataclass
class RunResult:
    ok:     bool
    stdout: str
    stderr: str
    data:   Any = None

    @property
    def error_message(self) -> str:
        return self.stderr or "Unknown error"


@dataclass
class _GdepCmd:
    """Resolved gdep invocation: either ['dotnet', 'gdep.dll'] or ['gdep.exe']."""
    args: list[str]
    is_dll: bool = False


def _find_dotnet() -> str | None:
    """Return path to dotnet executable, or None if not found."""
    return shutil.which("dotnet")


def find_gdep(extra_hint: str | None = None) -> _GdepCmd | None:
    """
    Resolve the gdep C# parser.

    Priority (highest → lowest):
    1. GDEP_DLL env var  → dotnet <path/to/gdep.dll>
    2. GDEP_EXE env var  → legacy exe path
    3. publish_dll/gdep.dll  → dotnet (framework-dependent, OS-agnostic)
    4. publish/gdep.dll      → dotnet (legacy publish dir, already contains dll)
    5. publish/gdep.exe      → Windows native exe (legacy fallback)
    6. publish_mac/gdep      → macOS native exe (legacy fallback)
    7. extra_hint            → user-supplied path
    8. PATH 'gdep'           → system-installed binary
    """
    pkg_dir = Path(__file__).parent          # gdep package dir (works for pip install)
    here = pkg_dir.parent                    # gdep-cli/ in dev, site-packages/ when installed
    root = here.parent                       # project root in dev; irrelevant when installed

    # --- 1. GDEP_DLL explicit override ---
    dll_env = os.environ.get("GDEP_DLL", "")
    if dll_env and Path(dll_env).exists():
        dotnet = _find_dotnet()
        if dotnet:
            return _GdepCmd(args=[dotnet, dll_env], is_dll=True)

    # --- 2. GDEP_EXE explicit override (legacy) ---
    exe_env = os.environ.get("GDEP_EXE", "")
    if exe_env and Path(exe_env).exists():
        return _GdepCmd(args=[exe_env])

    # --- 3 & 4. DLL search: package bin/ first (pip install), then dev publish dirs ---
    dll_candidates = [
        pkg_dir / "bin" / "gdep.dll",        # pip-installed package (gdep/bin/gdep.dll)
        root / "publish_dll" / "gdep.dll",
        root / "publish" / "gdep.dll",
    ]
    dotnet = _find_dotnet()
    for dll_path in dll_candidates:
        if dll_path.is_file() and dotnet:
            return _GdepCmd(args=[dotnet, str(dll_path)], is_dll=True)

    # --- 5 & 6. Legacy native binaries ---
    native_candidates = [
        root / "publish" / "gdep.exe",
        root / "publish" / "gdep",
        root / "publish_mac" / "gdep",
        here / "gdep.exe",
        here / "gdep",
        here / "gdep_bin" / "gdep.exe",
        *([] if not extra_hint else [Path(extra_hint)]),
    ]
    for p in native_candidates:
        if p.is_file():
            return _GdepCmd(args=[str(p)])

    # --- 7. PATH fallback ---
    sys_gdep = shutil.which("gdep")
    if sys_gdep:
        return _GdepCmd(args=[sys_gdep])

    return None


def _decode(b: bytes) -> str:
    if not b: return ""
    for enc in ["utf-8", "cp949", "utf-8-sig"]:
        try: return b.decode(enc)
        except (UnicodeDecodeError, AttributeError): continue
    return b.decode("utf-8", errors="replace")


def _clean(t: str) -> str:
    return ANSI_ESCAPE.sub("", t)


def _parse_json(stdout: str) -> Any:
    s = stdout.find("{")
    if s == -1: return None
    chunk = stdout[s:]
    try: return json.loads(chunk[:chunk.rfind("}")+1])
    except json.JSONDecodeError: return None


def _is_cpp(profile: ProjectProfile) -> bool:
    return profile.kind in (ProjectKind.CPP, ProjectKind.UNREAL)


def _src(profile: ProjectProfile) -> str:
    return str(profile.source_dirs[0]) if profile.source_dirs else str(profile.root)


def run(args: list[str], timeout: int = 180,
        gdep_path: str | None = None) -> RunResult:
    cmd = find_gdep(gdep_path)
    if not cmd:
        return RunResult(
            ok=False, stdout="",
            stderr=(
                "gdep C# parser not found. "
                "Make sure 'dotnet' runtime is installed and gdep.dll exists in publish/ or publish_dll/. "
                "See README.md for setup instructions."
            ),
        )
    try:
        full_cmd = cmd.args + args
        proc = subprocess.run(full_cmd, capture_output=True, timeout=timeout)
        stdout = _clean(_decode(proc.stdout))
        stderr = _clean(_decode(proc.stderr))
        data   = _parse_json(stdout) if "--format" in args and "json" in args else None
        return RunResult(ok=proc.returncode == 0, stdout=stdout,
                         stderr=stderr, data=data)
    except subprocess.TimeoutExpired:
        return RunResult(ok=False, stdout="", stderr=f"Execution timed out ({timeout}s)")
    except FileNotFoundError as e:
        return RunResult(ok=False, stdout="", stderr=f"File not found: {e}")
    except PermissionError as e:
        return RunResult(ok=False, stdout="", stderr=f"Permission denied executing gdep parser: {e}")


def _format_cs_scan_console(data: dict, top: int, circular: bool, dead_code: bool) -> str:
    """Rebuild console output from cached scan data dict."""
    summary  = data.get("summary", {})
    coupling = data.get("coupling", [])
    cycles   = data.get("cycles", [])
    dead     = data.get("deadNodes", [])

    lines = [
        f"\n┌─ gdep scan results {'─'*49}┐",
        f"\n│ Path {summary.get('path', '')}",
        f"\n│ Files {summary.get('fileCount', '?')}  |  Classes {summary.get('classCount', '?')}  |"
        f"  References {summary.get('referenceCount', '?')}",
        f"\n│ (Fields/Props {summary.get('fieldCount','?')} · "
        f"Inheritance {summary.get('inheritanceCount','?')})  |"
        f"  Orphan Nodes {summary.get('deadCount','?')}",
        f"\n└{'─'*60}┘\n",
        "\n\n── Top Classes by Coupling (in-degree, excluding inheritance)\n",
    ]

    header = f"  {'Rank':<6} {'Class':<36} {'Namespace':<24} {'Ref Count':>9}"
    lines.append(header)
    lines.append("─" * 79)

    for rank, item in enumerate(coupling[:top], 1):
        eng = f" [+{item['engine_ref']}]" if "engine_ref" in item else ""
        lines.append(
            f"  {rank:<6} {item['name']:<36} {item.get('namespace',''):<24} "
            f"{item['score']:>9}{eng}"
        )

    if circular and cycles:
        lines.append("\n\n── Detecting Circular References\n")
        lines.append(f"{len(cycles)} circular references found\n")
        for c in cycles[:20]:
            lines.append(f"  ? {c}")

    if dead_code and dead:
        lines.append("\n\n── [Dead Code] Classes with no references (Ref Count 0)\n")
        lines.append(f"  {'Class':<26} {'Namespace':<26} {'File Path'}")
        lines.append("─" * 79)
        for d in dead[:50]:
            lines.append(
                f"  {d['name']:<26} {d.get('namespace',''):<26} {d.get('file','')}"
            )

    return "\n".join(lines)


def _cs_fingerprint(src: str) -> str:
    """MD5 fingerprint of all .cs file mtimes under src.
    Uses os.scandir for speed instead of rglob."""
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
                    elif entry.name.endswith(".cs"):
                        try:
                            mtimes.append(f"{entry.path}:{entry.stat().st_mtime_ns}")
                        except OSError:
                            pass
        except PermissionError:
            pass
    mtimes.sort()
    return hashlib.md5("\n".join(mtimes).encode()).hexdigest()


def _cs_cache_path(profile: "ProjectProfile") -> Path:
    cache_dir = Path(profile.root) / ".gdep" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cs_scan.json"


def _load_cs_cache(profile: "ProjectProfile") -> dict | None:
    cp = _cs_cache_path(profile)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        src = _src(profile)
        if data.get("fingerprint") == _cs_fingerprint(src):
            return data.get("scan_result")
    except Exception:
        pass
    return None


def _save_cs_cache(profile: "ProjectProfile", scan_result: dict) -> None:
    try:
        cp = _cs_cache_path(profile)
        src = _src(profile)
        payload = {
            "fingerprint": _cs_fingerprint(src),
            "saved_at": time.time(),
            "scan_result": scan_result,
        }
        cp.write_text(json.dumps(payload, ensure_ascii=False, default=str),
                      encoding="utf-8")
    except Exception:
        pass


def scan(profile: ProjectProfile, circular: bool = False,
         dead_code: bool = False,
         deep: bool = False,
         include_refs: bool = False,
         top: int = 20, namespace: str | None = None,
         ignore: list[str] | None = None,
         fmt: str = "console") -> RunResult:
    # 1. Determine and call engine-specific Runner
    if _is_cpp(profile):
        if profile.kind == ProjectKind.UNREAL:
            from . import ue5_runner
            return ue5_runner.scan(_src(profile), top=top, circular=circular, dead_code=dead_code, include_refs=include_refs, fmt=fmt, deep=deep)
        from . import cpp_runner
        return cpp_runner.scan(_src(profile), top=top, circular=circular, dead_code=dead_code, include_refs=include_refs, fmt=fmt, deep=deep)

    # 2. Process C# (Unity/Dotnet)
    src  = _src(profile)

    # ── mtime-based disk cache for C# scan (skips dotnet subprocess) ──
    if not include_refs and fmt != "json":
        cached = _load_cs_cache(profile)
        if cached:
            # Rebuild console output from cached data
            _rebuild_console = _format_cs_scan_console(cached, top, circular, dead_code)
            return RunResult(ok=True, stdout=_rebuild_console, stderr="", data=cached)

    # Use JSON internally — always needed for cache saving and refs merging
    # console output is reconstructed from JSON data after
    internal_fmt = "json"

    args = ["scan", src, "--top", "999", "--format", internal_fmt]
    if circular:         args.append("--circular")
    if dead_code:        args.append("--dead-code")
    if deep:             args.append("--deep")
    if namespace:        args += ["--namespace", namespace]
    if ignore:
        for p in ignore: args += ["--ignore", p]

    result = run(args)

    # Save scan result to disk cache (only for basic scan without refs)
    if not include_refs and result.ok and result.data:
        _save_cs_cache(profile, result.data)

    # If caller wants console output, reconstruct it from JSON data
    if fmt != "json" and not include_refs and result.ok and result.data:
        console_out = _format_cs_scan_console(result.data, top, circular, dead_code)
        return RunResult(ok=True, stdout=console_out, stderr="", data=result.data)

    # 3. Integrate engine back-references (Prefab/Blueprint) for C# projects
    if include_refs and result.ok and result.data:
        result = _merge_engine_refs_json(profile, result, dead_code, top, fmt)

    return result


def _merge_engine_refs_json(profile: ProjectProfile, code_result: RunResult,
                            dead_code: bool, top: int, fmt: str) -> RunResult:
    """Merge engine back-references based on JSON data and reformat the result."""
    src = _src(profile)
    ref_map = None

    if profile.kind == ProjectKind.UNITY:
        from . import unity_refs
        ref_map = unity_refs.build_ref_map(src)
    elif profile.kind == ProjectKind.UNREAL:
        from . import ue5_blueprint_refs
        ref_map = ue5_blueprint_refs.build_ref_map(src)

    if not ref_map:
        return code_result

    data = code_result.data
    # data structure: { "summary": {...}, "coupling": [...], "deadNodes": [...], "cycles": [...] }

    # 1. Sum coupling scores
    for item in data.get("coupling", []):
        class_name = item["name"]
        engine_ref = ref_map.get(class_name)
        if engine_ref and engine_ref.total > 0:
            item["score"] = item.get("score", 0) + engine_ref.total
            item["engine_ref"] = engine_ref.total

    # Re-sort Top N
    data["coupling"].sort(key=lambda x: x["score"], reverse=True)

    # 2. Filter Dead Code
    original_dead_nodes = data.get("deadNodes", [])
    new_dead_nodes = []
    for node in original_dead_nodes:
        class_name = node["name"]
        engine_ref = ref_map.get(class_name)
        if not engine_ref or engine_ref.total == 0:
            new_dead_nodes.append(node)

    data["deadNodes"] = new_dead_nodes
    data["summary"]["deadCount"] = len(new_dead_nodes)

    if fmt == "json":
        return RunResult(ok=True, stdout=json.dumps(data, indent=2, ensure_ascii=False),
                         stderr=code_result.stderr, data=data)

    # 3. Re-generate in console format (mimicking gdep.exe style)
    lines = []
    summary = data["summary"]
    lines.append("")
    lines.append("╭─ gdep scan results ──────────────────────────────────────────────╮")
    lines.append(f"│ Path:   {summary['path']}                                │")
    lines.append(f"│ Files:  {summary['fileCount']}  |  "
                 f"Classes: {summary['classCount']}  |  "
                 f"Refs:    {summary['refCount']}")
    lines.append(f"│ Orphan Nodes: [yellow]{summary['deadCount']}[/] (Engine back-refs included)")
    lines.append("╰──────────────────────────────────────────────────────────────────╯")
    lines.append("")

    lines.append("[yellow]── High-Coupling Classes (in-degree, excluding inheritance)[/]")
    lines.append(f"{'Rank':<4} {'Class':<25} {'Namespace':<20} {'Refs':>8}")
    lines.append("-" * 65)

    for i, item in enumerate(data["coupling"][:top], 1):
        color = "red" if item["score"] >= 10 else "yellow" if item["score"] >= 5 else "green"
        engine_hint = f" [gray](+{item['engine_ref']})[/]" if "engine_ref" in item else ""
        lines.append(f"{i:<4} {item['name']:<25} {item['ns']:<20} [{color}]{item['score']}[/]{engine_hint}")

    if dead_code:
        lines.append("")
        lines.append("[yellow]── [[Dead Code]] Unreferenced Classes (Ref count: 0)[/]")
        if not new_dead_nodes:
            lines.append("[green]No orphan nodes found[/]")
        else:
            lines.append(f"{'Class':<25} {'Namespace':<20} {'File Path':<30}")
            lines.append("-" * 75)
            for node in new_dead_nodes:
                lines.append(f"{node['name']:<25} {node['ns']:<20} [gray]{node['file']}[/]")

    return RunResult(ok=True, stdout="\n".join(lines), stderr=code_result.stderr, data=data)


def flow(profile: ProjectProfile, class_name: str, method_name: str,
         depth: int = 4, focus_classes: list[str] | None = None,
         fmt: str = "json") -> RunResult:
    if _is_cpp(profile):
        if profile.kind == ProjectKind.UNREAL:
            from . import ue5_runner
            return ue5_runner.flow(_src(profile), class_name, method_name,
                                  depth=depth, focus_classes=focus_classes, fmt=fmt)
        from . import cpp_runner
        return cpp_runner.flow(_src(profile), class_name, method_name,
                               depth=depth, focus_classes=focus_classes, fmt=fmt)
    src  = _src(profile)
    args = ["flow", src, "--class", class_name, "--method", method_name,
            "--depth", str(depth), "--format", fmt]
    if focus_classes:
        args += ["--focus-class", ",".join(focus_classes)]
    return run(args)


def describe(profile: ProjectProfile, class_name: str,
             fmt: str = "console", summarize: bool = False,
             refresh: bool = False) -> RunResult:
    # 1. Run basic analysis
    if _is_cpp(profile):
        if profile.kind == ProjectKind.UNREAL:
            from . import ue5_runner
            result = ue5_runner.describe(_src(profile), class_name)
        else:
            from . import cpp_runner
            result = cpp_runner.describe(_src(profile), class_name)
    else:
        result = run(["describe", _src(profile), class_name, "--format", fmt])

    if not result.ok:
        return result

    # 2. LLM Summary processing (supported for console output)
    if summarize and fmt == "console":
        summary = _get_class_summary(profile, class_name, result.stdout, refresh)
        if summary:
            # Prepend summary to the output
            header = f"\n[bold cyan]── Semantic Summary (AI) ──────────────────────────[/]\n{summary}\n"
            result.stdout = header + result.stdout

    return result


def _get_class_summary(profile: ProjectProfile, class_name: str,
                       context: str, refresh: bool) -> str | None:
    """Retrieve cached summary or call LLM to generate one."""
    cache_dir = Path(profile.root) / ".gdep" / "cache" / "summaries"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{class_name}.txt"

    if not refresh and cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception:
            pass

    # Call LLM
    from .llm_provider import summarize_class
    summary = summarize_class(class_name, context)

    if summary and "Failed" not in summary and "Configuration missing" not in summary:
        try:
            cache_file.write_text(summary, encoding="utf-8")
        except Exception:
            pass

    return summary


def read_source(profile: ProjectProfile, class_name: str,
                max_chars: int = 8000) -> RunResult:
    src = _src(profile)
    if _is_cpp(profile):
        if profile.kind == ProjectKind.UNREAL:
            from . import ue5_runner
            return ue5_runner.read_source(src, class_name, max_chars=max_chars)
        from . import cpp_runner
        return cpp_runner.read_source(src, class_name, max_chars=max_chars)
    from .source_reader import find_class_files, format_for_llm
    result = find_class_files(src, class_name)
    if not result.chunks:
        return RunResult(ok=False, stdout="",
                         stderr=f"Could not find file for class `{class_name}`.")
    return RunResult(ok=True, stdout=format_for_llm(result, max_chars), stderr="")


def impact(profile: ProjectProfile, target_class: str, depth: int = 3) -> RunResult:
    if _is_cpp(profile):
        if profile.kind == ProjectKind.UNREAL:
            from . import ue5_runner
            return ue5_runner.impact(_src(profile), target_class, depth=depth)
        from . import cpp_runner
        return cpp_runner.impact(_src(profile), target_class, depth=depth)

    # C# (Unity/Dotnet)
    src = _src(profile)
    # C# always uses --deep for impact analysis
    result = run(["impact", src, target_class, "--depth", str(depth), "--deep"])

    # Merge Unity asset references
    if result.ok and profile.kind == ProjectKind.UNITY:
        from . import unity_refs
        ref_map = unity_refs.build_ref_map(src)
        if ref_map:
            ref = ref_map.get(target_class)
            if ref and ref.usages:
                asset_lines = ["", "── Asset Usages ──"]
                for usage in sorted(ref.usages):
                    asset_lines.append(f"└── {usage}")
                result.stdout += "\n" + "\n".join(asset_lines)

    return result


def graph(profile: ProjectProfile, fmt: str = "mermaid",
          output: str | None = None, cycles_only: bool = False) -> RunResult:
    if _is_cpp(profile):
        return RunResult(ok=False, stdout="",
                         stderr="`graph` command only supports C# projects.")
    args = ["graph", _src(profile), "--format", fmt]
    if output:      args += ["--output", output]
    if cycles_only: args.append("--cycles-only")
    return run(args)


def lint(profile: ProjectProfile, fmt: str = "console") -> RunResult:
    """Run engine-specific anti-pattern linter."""
    src = _src(profile)

    if profile.kind == ProjectKind.UNREAL:
        from . import ue5_runner
        return ue5_runner.lint(src, fmt=fmt)
    elif profile.kind == ProjectKind.CPP:
        from . import cpp_runner
        return cpp_runner.lint(src, fmt=fmt)

    # Unity/C#
    if profile.kind == ProjectKind.UNITY:
        # 1. Run gdep.exe lint (which outputs JSON)
        res = run(["lint", src])
        if not res.ok:
            return res

        # 2. Process results through Linter
        from .analyzer.linter import Linter
        linter = Linter()
        # gdep lint output is JSON list of issues
        try:
            raw_issues = json.loads(res.stdout)
            results = linter.lint_unity(raw_issues, source_path=src)
        except json.JSONDecodeError:
            return RunResult(ok=False, stdout="", stderr="Failed to parse gdep lint output.")

        if fmt == "json":
            data = [vars(r) for r in results]
            return RunResult(ok=True, stdout=json.dumps(data, indent=2, ensure_ascii=False), stderr="", data=data)

        # 3. Format console output (UE5 style)
        if not results:
            return RunResult(ok=True, stdout="✓ No anti-patterns detected.", stderr="")

        lines = [
            f"┌─ Unity Anti-pattern Scanner Results {'─'*32}┐",
            f"│ Path:   {src}",
            f"│ Found:  {len(results)} issues",
            f"└{'─'*60}┘",
            "",
        ]

        # Sort by severity and then by Class
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

        return RunResult(ok=True, stdout="\n".join(lines), stderr="", data=[vars(r) for r in results])

    return RunResult(ok=False, stdout="", stderr=f"Linting not supported for {profile.display} projects.")


def diff(profile: ProjectProfile, commit: str | None = None,
         fail_on_cycles: bool = False) -> RunResult:
    if _is_cpp(profile):
        return RunResult(ok=False, stdout="",
                         stderr="`diff` command only supports C# projects.")
    args = ["diff", _src(profile)]
    if commit:         args += ["--commit", commit]
    if fail_on_cycles: args.append("--fail-on-cycles")
    return run(args)


# ── Test-scope helpers ────────────────────────────────────────

_TEST_EXTENSIONS = {
    ProjectKind.UNITY:  [".cs"],
    ProjectKind.DOTNET: [".cs"],
    ProjectKind.UNREAL: [".cpp", ".h"],
    ProjectKind.CPP:    [".cpp", ".h"],
}

_TEST_DIR_NAMES = {"tests", "test", "specs", "spec", "unittests"}

_TEST_STEM_KEYWORDS = {
    ProjectKind.UNITY:  ["test", "tests", "spec"],
    ProjectKind.DOTNET: ["test", "tests", "spec"],
    ProjectKind.UNREAL: ["spec", "test"],
    ProjectKind.CPP:    ["test", "spec"],
}

_TEST_STEM_PREFIX = {
    ProjectKind.CPP:    ["test_"],
    ProjectKind.UNREAL: ["test_"],
}


def _find_test_files(src: str, kind: "ProjectKind") -> list:
    """Recursively scan src for test-pattern files. Returns list of Paths."""
    root = Path(src)
    exts = set(_TEST_EXTENSIONS.get(kind, [".cs", ".cpp", ".h"]))
    keywords = _TEST_STEM_KEYWORDS.get(kind, ["test", "spec"])
    prefixes = _TEST_STEM_PREFIX.get(kind, [])

    results = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file():
                        p = Path(entry.path)
                        if p.suffix.lower() not in exts:
                            continue
                        stem_lower = p.stem.lower()
                        in_test_dir = any(
                            part.lower() in _TEST_DIR_NAMES
                            for part in p.parts
                        )
                        name_is_test = (
                            any(kw in stem_lower for kw in keywords)
                            or any(stem_lower.startswith(px) for px in prefixes)
                        )
                        if in_test_dir or name_is_test:
                            results.append(p)
        except (PermissionError, OSError):
            pass
    return results


def _parse_affected_classes(impact_text: str) -> set:
    """Extract class names from impact tree text output.

    Handles both C# output  (ClassName (file.cs))
    and tree-prefix lines  (  ├── ClassName (file.cs)).
    """
    pattern = re.compile(r'(?:^|[├└│─\s]+)([A-Z][A-Za-z0-9_]+)(?:\s*\(|$)', re.MULTILINE)
    _SKIP = {"RECURSIVE", "Assets", "Scripts", "Content", "Source", "Tests", "Specs"}
    names: set = set()
    for m in pattern.finditer(impact_text):
        candidate = m.group(1)
        if len(candidate) >= 3 and candidate not in _SKIP:
            names.add(candidate)
    return names


def _engine_tag(kind: "ProjectKind") -> str:
    tags = {
        ProjectKind.UNITY:  "Unity",
        ProjectKind.DOTNET: ".NET",
        ProjectKind.UNREAL: "UE5",
        ProjectKind.CPP:    "C++",
    }
    return tags.get(kind, "?")


def _format_test_scope_console(target_class: str, depth: int,
                                affected_count: int, matched: list,
                                src: str) -> str:
    src_root = Path(src)
    lines = [
        f"\n── Test Scope: {target_class} (Depth: {depth}) ──\n",
        f"  Affected classes: {affected_count}",
        f"  Test files found: {len(matched)}\n",
    ]
    if not matched:
        lines.append("  (No test files found — consider writing new tests)")
    else:
        for i, item in enumerate(matched):
            connector = "└──" if i == len(matched) - 1 else "├──"
            try:
                rel = Path(item["path"]).relative_to(src_root)
                dir_part = str(rel.parent) if rel.parent != Path(".") else ""
                fname = rel.name
            except ValueError:
                fname = Path(item["path"]).name
                dir_part = ""
            tag = item.get("engine", "?")
            dir_display = f"{dir_part}/" if dir_part else ""
            matched_cls = item.get("matched_class", "")
            cls_hint = f"  ← {matched_cls}" if matched_cls else ""
            lines.append(
                f"  {connector} {fname:<40} [{tag}]  {dir_display}{cls_hint}"
            )
    lines.append("")
    return "\n".join(lines)


def test_scope(profile: ProjectProfile, target_class: str,
               depth: int = 3, fmt: str = "console") -> RunResult:
    """Find test files to run when target_class is modified.

    Steps:
    1. Run impact() to get the BFS reverse-dependency tree.
    2. Parse affected class names from the output.
    3. Scan source dir for test-pattern files.
    4. Match test files whose name references any affected class.
    """
    # 1. Impact analysis
    impact_result = impact(profile, target_class, depth=depth)
    if not impact_result.ok:
        return impact_result

    # 2. Parse affected classes
    affected = _parse_affected_classes(impact_result.stdout)
    affected.add(target_class)
    affected_count = max(0, len(affected) - 1)

    # 3. Find test files
    src = _src(profile)
    test_files = _find_test_files(src, profile.kind)

    # 4. Match: test file stem contains an affected class name (or vice-versa)
    matched: list = []
    seen: set = set()
    for tf in test_files:
        stem_lower = tf.stem.lower()
        best_match: str = ""
        for cls in sorted(affected):
            if cls.lower() in stem_lower or stem_lower in cls.lower():
                best_match = cls
                break
        if not best_match and target_class.lower() in stem_lower:
            best_match = target_class
        # Include files in a Tests/ directory even without a specific class match
        if not best_match:
            in_test_dir = any(p.lower() in _TEST_DIR_NAMES for p in tf.parts)
            if not in_test_dir:
                continue  # skip: no class match and not in a test dir

        key = str(tf)
        if key not in seen:
            seen.add(key)
            matched.append({
                "path": str(tf),
                "matched_class": best_match,
                "engine": _engine_tag(profile.kind),
            })

    # Sort: specific class matches first, then alphabetical
    matched.sort(key=lambda x: (0 if x["matched_class"] else 1, x["path"]))

    if fmt == "json":
        data: dict = {
            "target_class": target_class,
            "depth": depth,
            "affected_count": affected_count,
            "test_file_count": len(matched),
            "test_files": matched,
        }
        return RunResult(
            ok=True,
            stdout=json.dumps(data, indent=2, ensure_ascii=False),
            stderr="",
            data=data,
        )

    return RunResult(
        ok=True,
        stdout=_format_test_scope_console(
            target_class, depth, affected_count, matched, src),
        stderr="",
    )


# ── Architecture Advisor ──────────────────────────────────────

def advise(profile: ProjectProfile,
           focus_class: str | None = None,
           fmt: str = "console") -> RunResult:
    """Combine scan + lint + impact and return structured architecture advice.

    If an LLM is configured (gdep config llm), the structured context is sent
    to the LLM for natural-language advice.  Without an LLM config the function
    returns the structured data-driven report directly -- still useful.

    Cache: .gdep/cache/advice.md  (invalidated when scan summary changes)
    """
    src = Path(_src(profile))
    cache_dir = Path(profile.root) / ".gdep" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "advice.md"

    # 1. Scan
    scan_res = scan(profile, circular=True, dead_code=True, fmt="json")
    if not scan_res.ok:
        return RunResult(ok=False, stdout="", stderr=f"[advise] scan failed: {scan_res.error_message}")

    scan_data: dict = scan_res.data or {}
    summary   = scan_data.get("summary", {})
    coupling  = scan_data.get("coupling", [])   # [{name, score, file}]
    dead_nodes = scan_data.get("deadNodes", []) # [{name, score, file}]
    cycles    = scan_data.get("cycles", [])     # list of cycle lists/strs

    # 2. Lint
    lint_res = lint(profile, fmt="json")
    try:
        lint_issues: list = json.loads(lint_res.stdout) if lint_res.stdout else (lint_res.data or [])
    except Exception:
        lint_issues = []

    # 3. Cache key = hash of scan summary + lint issue count
    import hashlib as _hl
    cache_key = _hl.md5(
        json.dumps({
            "summary": summary,
            "coupling_top3": coupling[:3],
            "cycle_count": len(cycles),
            "lint_count": len(lint_issues),
            "focus": focus_class,
        }, sort_keys=True).encode()
    ).hexdigest()

    # Return cached advice if key matches
    if cache_file.exists():
        try:
            cached_text = cache_file.read_text(encoding="utf-8")
            first_line  = cached_text.splitlines()[0] if cached_text else ""
            if first_line.startswith(f"<!-- gdep-advice-key:{cache_key} -->"):
                text = "\n".join(cached_text.splitlines()[1:])
                return RunResult(ok=True, stdout=text, stderr="")
        except Exception:
            pass

    # 4. Impact analysis for focus class or top-coupling class
    impact_text = ""
    impact_target = focus_class or (coupling[0]["name"] if coupling else None)
    if impact_target:
        imp_res = impact(profile, impact_target, depth=3)
        if imp_res.ok:
            # Keep first 30 lines to avoid bloat
            impact_lines = [l for l in imp_res.stdout.splitlines() if l.strip()][:30]
            impact_text = "\n".join(impact_lines)

    # 5. Build structured context (used both as LLM input and fallback output)
    ctx_lines: list[str] = []
    ctx_lines.append(f"Project: {profile.name}  Engine: {profile.display}")
    ctx_lines.append(
        f"Files: {summary.get('fileCount', '?')}  "
        f"Classes: {summary.get('classCount', '?')}  "
        f"Structs: {summary.get('structCount', 0)}  "
        f"Enums: {summary.get('enumCount', 0)}"
    )
    ctx_lines.append(f"Dead code candidates: {summary.get('deadCount', 0)}")
    ctx_lines.append(f"Circular dependencies: {len(cycles)}")
    ctx_lines.append(f"Lint issues: {len(lint_issues)}")
    ctx_lines.append("")

    ctx_lines.append("Top coupling classes:")
    for c in coupling[:10]:
        ctx_lines.append(f"  {c['name']} (in-degree={c['score']})  {c.get('file','')}")

    if dead_nodes:
        ctx_lines.append("")
        ctx_lines.append("Orphan classes (dead code candidates):")
        for d in dead_nodes[:10]:
            ctx_lines.append(f"  {d['name']}  {d.get('file','')}")

    if cycles:
        ctx_lines.append("")
        ctx_lines.append("Circular dependencies (sample, up to 5):")
        for cy in cycles[:5]:
            if isinstance(cy, list):
                ctx_lines.append("  " + " -> ".join(str(n) for n in cy))
            else:
                ctx_lines.append(f"  {cy}")

    if lint_issues:
        ctx_lines.append("")
        ctx_lines.append("Lint issues (sample, up to 10):")
        for issue in lint_issues[:10]:
            rule = issue.get("rule_id", "?")
            sev  = issue.get("severity", "?")
            cls  = issue.get("class_name", "?")
            msg  = issue.get("message", "")
            ctx_lines.append(f"  [{sev}] {rule}  {cls}: {msg}")

    if impact_text:
        ctx_lines.append("")
        ctx_lines.append(f"Impact analysis for '{impact_target}':")
        ctx_lines.append(impact_text)

    structured_ctx = "\n".join(ctx_lines)

    # 6. Try LLM call
    llm_advice = _call_llm_for_advice(structured_ctx, focus_class)

    # 7. Format final output
    advice_text = _format_advice(
        profile=profile,
        summary=summary,
        coupling=coupling,
        dead_nodes=dead_nodes,
        cycles=cycles,
        lint_issues=lint_issues,
        impact_target=impact_target,
        impact_text=impact_text,
        llm_text=llm_advice,
        focus_class=focus_class,
    )

    # 8. Cache
    try:
        cache_file.write_text(
            f"<!-- gdep-advice-key:{cache_key} -->\n{advice_text}",
            encoding="utf-8",
        )
    except Exception:
        pass

    return RunResult(ok=True, stdout=advice_text, stderr="")


def _call_llm_for_advice(context: str, focus_class: str | None) -> str:
    """Call configured LLM with structured context. Returns '' on any failure."""
    try:
        from .llm_provider import chat, load_config
        cfg = load_config()
        if not cfg:
            return ""
        focus_note = f" with focus on class '{focus_class}'" if focus_class else ""
        prompt = (
            f"You are an expert game software architect. "
            f"Analyze the following project metrics{focus_note} "
            f"and provide concise, actionable architecture advice.\n\n"
            f"Structure your response as:\n"
            f"1. IMMEDIATE (fix now): top 1-2 critical issues with concrete steps\n"
            f"2. MID-TERM (next sprint): structural improvements\n"
            f"3. LONG-TERM (backlog): strategic direction\n\n"
            f"Keep each item to 2 sentences maximum. "
            f"Cite the actual class names from the data.\n\n"
            f"--- Project Data ---\n{context}"
        )
        messages = [
            {"role": "system", "content": "You are a specialist in game software architecture."},
            {"role": "user",   "content": prompt},
        ]
        resp = chat(cfg, messages)
        return resp["message"]["content"].strip()
    except Exception:
        return ""


def _format_advice(*, profile, summary, coupling, dead_nodes, cycles,
                   lint_issues, impact_target, impact_text, llm_text,
                   focus_class) -> str:
    """Render the final advise report (ASCII-safe for cp949 terminals)."""
    lines: list[str] = []
    sep = "-" * 60

    lines.append(sep)
    focus_note = f"  (focus: {focus_class})" if focus_class else ""
    lines.append(f"-- Architecture Advice: {profile.name}{focus_note} --")
    lines.append(sep)
    lines.append("")

    # Summary block
    lines.append("[Current State]")
    lines.append(
        f"  Classes : {summary.get('classCount', '?')}  "
        f"Dead: {summary.get('deadCount', 0)}  "
        f"Cycles: {len(cycles)}  "
        f"Lint: {len(lint_issues)}"
    )
    if coupling:
        top3 = ", ".join(f"{c['name']}({c['score']})" for c in coupling[:3])
        lines.append(f"  High-coupling TOP 3: {top3}")
    lines.append("")

    # LLM advice block (if available)
    if llm_text:
        lines.append("[AI Architecture Advice]")
        lines.append("")
        for ln in llm_text.splitlines():
            lines.append(f"  {ln}")
        lines.append("")
    else:
        # Data-driven fallback advice
        lines.append("[Data-driven Findings]")
        lines.append("")

        item = 1

        # Cycles
        if cycles:
            lines.append(f"  {item}. Circular dependencies detected: {len(cycles)}")
            for cy in cycles[:3]:
                if isinstance(cy, list):
                    lines.append("     " + " -> ".join(str(n) for n in cy))
                else:
                    lines.append(f"     {cy}")
            lines.append("     -> Consider introducing interfaces or mediator pattern.")
            lines.append("")
            item += 1

        # High coupling
        if coupling and coupling[0]["score"] >= 4:
            top = coupling[0]
            lines.append(f"  {item}. High-coupling class: {top['name']} (in-degree={top['score']})")
            lines.append("     -> Single Responsibility Principle violation suspected.")
            lines.append("        Consider splitting into smaller focused classes.")
            lines.append("")
            item += 1

        # Dead code
        if dead_nodes:
            lines.append(f"  {item}. Orphan classes (unreferenced): {len(dead_nodes)}")
            names = ", ".join(d["name"] for d in dead_nodes[:5])
            lines.append(f"     -> {names}")
            lines.append("        Confirm intentional before removal.")
            lines.append("")
            item += 1

        # Lint
        errors = [i for i in lint_issues if i.get("severity") == "Error"]
        warnings = [i for i in lint_issues if i.get("severity") == "Warning"]
        if errors:
            lines.append(f"  {item}. Lint errors: {len(errors)} (run 'gdep lint --fix' for fix suggestions)")
            for e in errors[:3]:
                lines.append(f"     [{e.get('rule_id','')}] {e.get('class_name','')}: {e.get('message','')}")
            lines.append("")
            item += 1
        elif warnings:
            lines.append(f"  {item}. Lint warnings: {len(warnings)}")
            lines.append("")
            item += 1

        if item == 1:
            lines.append("  No significant issues found. Architecture looks healthy.")
            lines.append("")

    # Impact block
    if impact_text and impact_target:
        lines.append(f"[Impact: {impact_target}]")
        for ln in impact_text.splitlines()[:15]:
            lines.append(f"  {ln}")
        lines.append("")

    # Tip
    if not llm_text:
        lines.append("[Tip] Configure an LLM for natural-language advice:")
        lines.append("  gdep config llm")
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


def hints_generate(profile: ProjectProfile) -> RunResult:
    if _is_cpp(profile):
        return RunResult(ok=False, stdout="",
                         stderr="`hints` command only supports C# projects.")
    gdep_dir = Path(profile.root) / ".gdep"
    gdep_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(gdep_dir / ".gdep-hints.json")
    return run(["hints", "generate", _src(profile), "--output", out_path])


def hints_show(profile: ProjectProfile) -> RunResult:
    if _is_cpp(profile):
        return RunResult(ok=False, stdout="",
                         stderr="`hints` command only supports C# projects.")
    gdep_dir = str(Path(profile.root) / ".gdep")
    return run(["hints", "show", gdep_dir])
