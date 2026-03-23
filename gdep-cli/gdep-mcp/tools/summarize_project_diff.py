"""
gdep-mcp/tools/summarize_project_diff.py

High-level tool: git diff 결과를 아키텍처 관점으로 요약.
순환참조 증감, 고결합 클래스 영향, 권장 검토 포인트를 제공.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep.runner import _load_cs_cache, _src, ANSI_ESCAPE
from gdep.detector import detect


def _parse_diff_text(text: str) -> dict:
    """Parse gdep diff console output into structured data.

    Handles CLI line-wrapping: long chains are split across multiple lines
    where lines ending with '→' are continued on the next non-empty line.
    """
    data: dict = {
        "changed_files": 0,
        "new_cycles_count": 0,
        "resolved_cycles_count": 0,
        "new_cycles": [],
        "resolved_cycles": [],
    }

    m = re.search(r"Detected\s+(\d+)\s+changed\s+files?", text)
    if m:
        data["changed_files"] = int(m.group(1))

    m = re.search(r"\+\s*(\d+)\s+circular\s+references?\s+added", text)
    if m:
        data["new_cycles_count"] = int(m.group(1))

    m = re.search(r"-\s*(\d+)\s+circular\s+references?\s+resolved", text)
    if m:
        data["resolved_cycles_count"] = int(m.group(1))

    in_new = False
    in_resolved = False
    current_chain: str | None = None

    def _flush(bucket: list) -> None:
        nonlocal current_chain
        if current_chain:
            bucket.append(current_chain.strip())
            current_chain = None

    for line in text.splitlines():
        stripped = line.strip()

        if "New Circular References" in stripped:
            _flush(data["new_cycles"] if in_new else data["resolved_cycles"])
            in_new, in_resolved = True, False
            continue
        if "Resolved Circular References" in stripped:
            _flush(data["new_cycles"] if in_new else data["resolved_cycles"])
            in_new, in_resolved = False, True
            continue

        if not stripped:
            # Blank line inside a chain section means the chain continues
            # (the CLI wraps long chains with a blank separator line)
            continue

        # Skip box-drawing / header lines
        if stripped[0] in "+-|┌└│─" or stripped.startswith("Parsing"):
            continue

        # Lines that contain → are chain content
        if "\u2192" in stripped or "->" in stripped:
            part = stripped.lstrip("? ").strip()
            if current_chain is not None:
                # This is a continuation of a wrapped chain
                current_chain = current_chain.rstrip() + " " + part
            else:
                current_chain = part
            # If this part does NOT end with →, the chain is complete
            if not (current_chain.endswith("\u2192") or current_chain.endswith("->")):
                bucket = data["new_cycles"] if in_new else data["resolved_cycles"]
                if in_new or in_resolved:
                    _flush(bucket)
        else:
            # Non-chain line -flush any pending chain
            bucket = data["new_cycles"] if in_new else data["resolved_cycles"]
            if in_new or in_resolved:
                _flush(bucket)

    # Flush last pending chain
    bucket = data["new_cycles"] if in_new else data["resolved_cycles"]
    _flush(bucket)

    return data


def _classes_in_cycles(cycles: list[str]) -> set[str]:
    """Extract class names from cycle chains like 'A → B → C'."""
    classes: set[str] = set()
    for chain in cycles:
        for part in re.split(r"\s*[\u2192>]+\s*|->\s*", chain):
            name = part.strip()
            if name:
                classes.add(name)
    return classes


def run(project_path: str, commit_ref: str | None = None) -> str:
    """
    Analyze the git diff between the current state and a previous commit,
    and summarize the architectural impact.

    Identifies:
    - How many files changed
    - New vs resolved circular references
    - Whether any high-coupling classes are involved
    - Actionable review recommendations

    Use this tool WHEN:
    - User asks "what does this PR do to the codebase architecture?"
    - PR review: "does this change introduce new circular dependencies?"
    - User asks "is this commit risky from an architecture standpoint?"
    - After a refactoring to verify circular references were resolved

    Args:
        project_path: Absolute path to project root or Scripts/Source directory.
        commit_ref:   Git ref to diff against (e.g. "HEAD~1", "main", a SHA).
                      Defaults to "HEAD~1".

    Note:
        Currently supports Unity / C# projects only.
        For UE5/C++ projects, use inspect_architectural_health instead.
    """
    try:
        profile = detect(project_path)
        commit = commit_ref or "HEAD~1"

        # 1. Run diff via subprocess (same pattern as execute_gdep_cli, explicit timeout)
        src_path = _src(profile)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "gdep.cli", "diff", src_path, "--commit", commit],
                capture_output=True, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL, env=env,
                timeout=45, cwd=str(_GDEP_ROOT),
            )
            diff_stdout = ANSI_ESCAPE.sub("", proc.stdout or "")
            diff_ok = (proc.returncode == 0)
            diff_err = proc.stderr or ""
        except subprocess.TimeoutExpired:
            return (
                "[summarize_project_diff] diff timed out (>45s).\n"
                "The project may be too large for real-time diff analysis.\n"
                "Use execute_gdep_cli([\"diff\", path, \"--commit\", commit_ref]) directly."
            )

        if not diff_ok:
            return (
                f"[summarize_project_diff] Diff not available for this project.\n"
                f"Reason: {diff_err}\n\n"
                "For UE5/C++ projects, use `inspect_architectural_health` instead."
            )

        # 2. Parse diff text
        parsed = _parse_diff_text(diff_stdout)

        # 3. Load coupling data from disk cache only (no fresh scan — diff is already slow)
        #    If cache is missing, coupling cross-ref is skipped gracefully.
        coupling_list: list[dict] = []
        try:
            cached_data = _load_cs_cache(_src(profile))
            if cached_data:
                coupling_list = cached_data.get("coupling", [])
        except Exception:
            pass

        # 4. Cross-ref new cycle classes with high-coupling list
        new_cycle_classes = _classes_in_cycles(parsed["new_cycles"])
        coupling_map = {item["name"]: item["score"] for item in coupling_list}
        affected_high = sorted(
            [(cls, coupling_map[cls]) for cls in new_cycle_classes if cls in coupling_map],
            key=lambda x: -x[1],
        )

        # ── Format report ──────────────────────────────────────────────
        lines: list[str] = [
            f"## PR 아키텍처 영향 요약",
            f"  Baseline: `{commit}` vs 현재 워킹 트리  |  {profile.display}",
            "",
            "### 변경 통계",
            f"- 변경된 파일: **{parsed['changed_files']}개**",
            f"- 신규 순환참조: **+{parsed['new_cycles_count']}개**",
            f"- 해소된 순환참조: **-{parsed['resolved_cycles_count']}개**",
        ]

        net = parsed["resolved_cycles_count"] - parsed["new_cycles_count"]
        if net > 0:
            lines.append(f"- 순환참조 순감소: **-{net}개** (긍정적)")
        elif net < 0:
            lines.append(f"- 순환참조 순증가: **+{-net}개** (주의 필요)")
        else:
            lines.append("- 순환참조 순변화: 없음")

        # High-coupling involvement
        if affected_high:
            lines += [
                "",
                "### 고결합 클래스가 포함된 신규 순환참조",
            ]
            for cls, score in affected_high[:5]:
                lines.append(f"- **{cls}** (결합도 {score}) -새 순환참조에 포함됨")
            total_reach = sum(s for _, s in affected_high[:5])
            lines.append(
                f"\n> 위 클래스들의 변경은 총 {total_reach}개 클래스에 파급 영향을 줄 수 있습니다."
            )

        # New cycle chains
        if parsed["new_cycles"]:
            lines += ["", "### 신규 순환참조 체인"]
            for chain in parsed["new_cycles"][:10]:
                lines.append(f"- `{chain}`")
            if len(parsed["new_cycles"]) > 10:
                lines.append(f"- _(외 {len(parsed['new_cycles']) - 10}개)_")

        # Resolved cycle chains
        if parsed["resolved_cycles"]:
            lines += ["", "### 해소된 순환참조 (긍정적)"]
            for chain in parsed["resolved_cycles"][:5]:
                lines.append(f"- ~~`{chain}`~~")
            if len(parsed["resolved_cycles"]) > 5:
                lines.append(f"- _(외 {len(parsed['resolved_cycles']) - 5}개)_")

        # Recommendations
        recs: list[str] = []
        idx = 1
        if affected_high:
            top_cls, top_score = affected_high[0]
            recs.append(
                f"{idx}. **{top_cls}** (결합도 {top_score}) 변경이 순환참조를 유발 -"
                "Interface 분리 또는 의존 방향 역전 검토"
            )
            idx += 1
        if net < 0:
            recs.append(
                f"{idx}. 순환참조 순증가 ({-net}개) -"
                "신규 참조 방향을 재검토하고 단방향 의존으로 정리 권장"
            )
            idx += 1
        if parsed["changed_files"] == 0 and parsed["new_cycles_count"] == 0:
            recs.append(f"{idx}. 변경 없음 -현재 워킹 트리가 {commit}와 동일합니다.")

        if recs:
            lines += ["", "### 권장 검토 포인트"]
            lines += recs

        return "\n".join(lines)

    except Exception as e:
        return f"[summarize_project_diff] Error: {e}"
