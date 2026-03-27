"""
gdep-mcp/tools/explain_method_logic.py

High-level tool: 메서드 내부 제어 흐름 로직 요약.
Guard / Branch / Loop / Always 패턴을 핀셋으로 추출 → 토큰 절감.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect, ProjectKind


def run(project_path: str, class_name: str, method_name: str) -> str:
    try:
        profile = detect(project_path)

        is_cpp = profile.kind in (ProjectKind.UNREAL, ProjectKind.CPP)

        if is_cpp:
            src_result = runner.read_source(profile, class_name, max_chars=100_000)
            if not src_result.ok:
                return (
                    f"[explain_method_logic] Could not read source for `{class_name}`: "
                    f"{src_result.error_message}"
                )
            source = src_result.stdout
        else:
            # C#: read raw file content (no char limit) so large classes aren't truncated
            from gdep.source_reader import find_class_files
            src = str(profile.source_dirs[0]) if profile.source_dirs else project_path
            cs_result = find_class_files(src, class_name)
            if not cs_result.chunks:
                return (
                    f"[explain_method_logic] Could not find source for `{class_name}`."
                )
            # Concatenate all chunks (partial classes), tracking offsets
            chunk_offsets: list[tuple[int, int, int]] = []  # (start, end, chunk_idx)
            parts: list[str] = []
            offset = 0
            for idx, chunk in enumerate(cs_result.chunks):
                chunk_offsets.append((offset, offset + len(chunk.content), idx))
                parts.append(chunk.content)
                offset += len(chunk.content) + 1  # +1 for \n separator
            source = "\n".join(parts)

        result = _extract_cpp_method(source, method_name) if is_cpp else _extract_cs_method(source, method_name)

        if result is None:
            suggestions = _find_method_elsewhere(project_path, profile, method_name, is_cpp)
            if suggestions:
                suggest_str = ", ".join(f"`{s}`" for s in suggestions[:5])
                return (
                    f"[explain_method_logic] Method `{method_name}` not found in `{class_name}`.\n"
                    f"Found in: {suggest_str}\n"
                    f"Tip: call again with the correct class name."
                )
            return (
                f"[explain_method_logic] Method `{method_name}` not found in `{class_name}`.\n"
                f"Tip: check the exact method name spelling or that the source file was found."
            )

        body, match_pos = result
        items = _parse_control_flow(body)

        # Resolve file reference from source header (cpp) or chunk offset (cs)
        file_ref = ""
        if is_cpp:
            for line in source.split("\n")[:6]:
                if any(ext in line for ext in (".cs", ".cpp", ".h")):
                    file_ref = line.strip().lstrip("#").strip()
                    break
        else:
            if cs_result.chunks and chunk_offsets:
                for (cstart, cend, cidx) in chunk_offsets:
                    if cstart <= match_pos < cend:
                        file_ref = Path(cs_result.chunks[cidx].file_path).name
                        break
                if not file_ref:
                    file_ref = Path(cs_result.chunks[0].file_path).name

        lines = [
            f"## Method: {class_name}.{method_name}",
            "### Control Flow Summary",
        ]
        if not items:
            lines.append("  (No branching logic detected — method appears to be a linear sequence)")
        else:
            for idx, item in enumerate(items, 1):
                # Sub-lines (├─ / └─) keep original indent, not numbered
                if item.startswith("   "):
                    lines.append(item)
                else:
                    lines.append(f"{idx}. {item}")

        if file_ref:
            lines.append(f"\nSource: {file_ref} : {method_name}()")

        return "\n".join(lines) + confidence_footer(ConfidenceTier.HIGH, "source-level control flow")

    except Exception as e:
        return f"[explain_method_logic] Error: {e}"


# ── Method body extractors ─────────────────────────────────────

def _extract_cpp_method(source: str, method_name: str) -> tuple[str, int] | None:
    """Extract C++ method body via cpp_flow utility, falling back to regex.
    Returns (body_text, match_start_position) or None."""
    try:
        from gdep.cpp_flow import _extract_function_body
        result = _extract_function_body(source, method_name)
        if result is not None:
            return (result, 0)
    except Exception:
        pass

    # Fallback 1: ClassName::method_name pattern
    pat = re.compile(
        r'\b\w+\s*::\s*' + re.escape(method_name) + r'\s*\([^{;]*\)\s*(?:const\s*)?\{',
        re.DOTALL,
    )
    m = pat.search(source)
    if not m:
        # Fallback 2: namespace-style (func defined without ClassName:: prefix inside namespace block)
        # e.g.  std::string bigAddNum(std::string a, int b) {
        pat_ns = re.compile(
            r'(?:^|\n)[ \t]*(?:[\w:<>*& ]+[ \t]+)' + re.escape(method_name) + r'\s*\([^;{}]*\)\s*(?:const\s*)?\s*\{',
        )
        m = pat_ns.search(source)
    if not m:
        return None
    start = source.index("{", m.start())
    body = _extract_brace_body(source, start)
    return (body, m.start()) if body else None


def _extract_cs_method(source: str, method_name: str) -> tuple[str, int] | None:
    """Extract C# method body via regex.
    Returns (body_text, match_start_position) or None."""
    pat = re.compile(
        r'(?:(?:public|private|protected|internal|static|virtual|override|async|sealed|abstract|new)\s+)*'
        r'[\w<>\[\],\s]+\s+' + re.escape(method_name) + r'\s*\([^)]*\)\s*(?:\w+[^{]*?)?\{',
        re.DOTALL,
    )
    m = pat.search(source)
    if not m:
        # Simpler fallback
        pat2 = re.compile(r'\b' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{', re.DOTALL)
        m = pat2.search(source)
        if not m:
            return None
    start = source.index("{", m.start())
    body = _extract_brace_body(source, start)
    return (body, m.start()) if body else None


def _extract_brace_body(text: str, brace_start: int) -> str | None:
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1:i]
    return None


# ── Control flow parser ────────────────────────────────────────

_KEYWORDS = frozenset({"if", "while", "for", "foreach", "switch", "return",
                        "throw", "new", "else", "catch", "try", "using", "lock"})


def _extract_call(line: str) -> str | None:
    """Extract the first meaningful call from a code line."""
    m = re.search(r'(\w+(?:\.\w+)*)\s*\(', line)
    if m:
        call = m.group(1)
        if call.split(".")[-1] not in _KEYWORDS:
            return call + "()"
    return None


def _parse_control_flow(body: str) -> list[str]:
    """
    Parse a method body and return human-readable control flow items.
    Patterns: Guard, Branch, Loop, Switch, Exception, Always.
    """
    items: list[str] = []
    lines = body.split("\n")
    n = len(lines)
    i = 0

    while i < n:
        raw = lines[i]
        line = raw.strip()

        # Skip blanks, comments, lone braces
        if not line or line in ("{", "}") or line.startswith("//") or line.startswith("*"):
            i += 1
            continue

        # ── Guard: if (...) { return/throw } ────────────────────
        guard_m = re.match(r"if\s*\((.{1,100})\)", line)
        if guard_m:
            cond = guard_m.group(1).strip()
            lookahead = "\n".join(lines[i: i + 6])
            if re.search(r"\b(return|throw)\b", lookahead):
                # Check it's really a guard (no else, small block)
                block, end_i = _collect_block(lines, i)
                inner = " ".join(block)
                if re.search(r"\b(return|throw)\b", inner) and "else" not in inner:
                    exit_m = re.search(r"\b(return|throw)\s+([^;]{0,50})", inner)
                    exit_str = (exit_m.group(0)[:55].strip() if exit_m else "return/throw")
                    items.append(f"Guard    : if ({cond[:70]}) → {exit_str}")
                    i = end_i
                    continue

            # ── Branch: if / else ────────────────────────────────
            true_calls, false_calls = _extract_branch_calls(lines, i)
            if false_calls:
                items.append(f"Branch   : if ({cond[:70]})")
                items.append(f"   ├─ true  : {', '.join(true_calls[:2]) or '...'}")
                items.append(f"   └─ false : {', '.join(false_calls[:2]) or '...'}")
            else:
                call_str = ", ".join(true_calls[:2]) or "..."
                items.append(f"Branch   : if ({cond[:70]}) → {call_str}")
            block, end_i = _collect_block(lines, i)
            i = end_i
            continue

        # ── Loop: for / foreach / while ──────────────────────────
        loop_m = re.match(r"(for(?:each)?|while)\s*\((.{1,100})\)", line)
        if loop_m:
            keyword   = loop_m.group(1)
            loop_cond = loop_m.group(2).strip()
            block, end_i = _collect_block(lines, i)
            loop_calls = [c for c in (_extract_call(l) for l in block) if c]
            call_str = ", ".join(dict.fromkeys(loop_calls[:3]))
            items.append(f"Loop     : {keyword} ({loop_cond[:60]}) → {call_str or '...'}")
            i = end_i
            continue

        # ── Switch ───────────────────────────────────────────────
        switch_m = re.match(r"switch\s*\((.{1,60})\)", line)
        if switch_m:
            items.append(f"Switch   : switch ({switch_m.group(1).strip()[:60]})")
            _, end_i = _collect_block(lines, i)
            i = end_i
            continue

        # ── try/catch ────────────────────────────────────────────
        if re.match(r"try\s*\{?$", line):
            items.append("Exception: try/catch block")
            i += 1
            continue

        i += 1

    # ── Always: top-level calls ──────────────────────────────────
    always = _top_level_calls(body)
    if always:
        items.append(f"Always   : {', '.join(always[:4])}")

    return items


def _collect_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """Collect lines of the block starting at `start`, return (block_lines, next_i)."""
    block: list[str] = []
    depth = 0
    i = start
    n = len(lines)
    while i < n:
        l = lines[i]
        block.append(l.strip())
        depth += l.count("{") - l.count("}")
        i += 1
        if depth <= 0 and i > start + 1:
            break
    return block, i


def _extract_branch_calls(lines: list[str], start: int) -> tuple[list[str], list[str]]:
    """Return (true_branch_calls, false_branch_calls) for an if/else block."""
    true_calls: list[str] = []
    false_calls: list[str] = []
    in_else = False
    depth = 0
    i = start
    n = len(lines)
    while i < n:
        l = lines[i].strip()
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start and re.match(r"^else\b", l):
            in_else = True
        call = _extract_call(l)
        if call:
            (false_calls if in_else else true_calls).append(call)
        i += 1
        if depth <= 0 and i > start + 1 and not re.match(r"^else\b", l):
            break
    return true_calls, false_calls


def _top_level_calls(body: str) -> list[str]:
    """Return deduplicated top-level (depth-0) method calls."""
    calls: list[str] = []
    seen: set[str] = set()
    depth = 0
    for line in body.split("\n"):
        s = line.strip()
        depth += s.count("{") - s.count("}")
        if depth == 0:
            call = _extract_call(s)
            if call and call not in seen:
                calls.append(call)
                seen.add(call)
    return calls


# ── Method search helper ──────────────────────────────────────

def _find_method_elsewhere(project_path: str, profile, method_name: str, is_cpp: bool) -> list[str]:
    """Search entire project for classes containing the given method."""
    if is_cpp:
        try:
            from gdep.cpp_flow import _find_cpp_files
            src = str(profile.source_dirs[0]) if profile.source_dirs else project_path
            cpp_files = _find_cpp_files(src)
            owners: list[str] = []
            pat = re.compile(r'\b(\w+)\s*::\s*' + re.escape(method_name) + r'\s*\(')
            for cls_name, cpp_path in cpp_files.items():
                try:
                    text = Path(cpp_path).read_text(encoding="utf-8", errors="replace")
                    if pat.search(text):
                        owners.append(cls_name)
                except Exception:
                    continue
            return owners
        except Exception:
            return []

    # ── C# path ──
    try:
        src = str(profile.source_dirs[0]) if profile.source_dirs else project_path
        root = Path(src)
        _IGNORE = {"obj", "bin", "Library", "Packages", "Temp", ".git", "node_modules"}
        pat = re.compile(r'\b' + re.escape(method_name) + r'\s*\(')
        class_pat = re.compile(r'(?:class|struct|interface)\s+(\w+)')
        owners: list[str] = []
        seen: set[str] = set()
        for cs_file in root.rglob("*.cs"):
            if any(part in _IGNORE for part in cs_file.parts):
                continue
            try:
                text = cs_file.read_text(encoding="utf-8", errors="replace")
                if pat.search(text):
                    for m in class_pat.finditer(text):
                        cls = m.group(1)
                        if cls not in seen:
                            owners.append(cls)
                            seen.add(cls)
                            break
            except Exception:
                continue
            if len(owners) >= 10:
                break
        return owners
    except Exception:
        return []
