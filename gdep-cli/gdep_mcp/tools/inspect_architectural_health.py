"""
gdep-mcp/tools/inspect_architectural_health.py

High-level tool: 프로젝트 전체 아키텍처 건강 검진.
runner.scan(deep + circular + dead_code + include_refs) + runner.lint 결합.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect


def run(project_path: str, include_dead_code: bool = True,
        include_refs: bool = True, top: int = 15) -> str:
    """
    Run a full architectural health check on the entire project.

    Identifies technical debt in one shot:
    - Circular dependencies (structural rot)
    - Dead code / orphan classes (maintenance burden)
    - High-coupling classes (refactoring risk)
    - Engine anti-patterns: GetComponent in Update, SpawnActor in Tick, etc.
    - Engine asset usages (Unity prefabs, UE5 blueprints) for accurate dead-code detection

    Use this tool for:
    - Initial codebase audit on a new project
    - Pre-sprint technical debt assessment
    - CI quality gate checks

    Args:
        project_path:      Absolute path to the project Scripts/Source directory.
        include_dead_code: Whether to detect unreferenced classes. Default: True.
        include_refs:      Factor in engine asset refs (prefabs/blueprints) for dead-code
                           filtering. Default: True. May be slow on large projects.
        top:               How many high-coupling classes to show. Default: 15.

    Returns:
        A comprehensive health report with coupling rank, cycles, dead code, and lint issues.
    """
    try:
        profile = detect(project_path)
        sections: list[str] = [
            "# Architectural Health Report",
            f"Project: {profile.display}  |  Path: {project_path}",
            "",
        ]

        # ── Deep Scan ────────────────────────────────────────────────
        scan_result = runner.scan(
            profile,
            circular=True,
            dead_code=include_dead_code,
            deep=True,
            include_refs=include_refs,
            top=top,
            fmt="json",
        )

        if scan_result.ok:
            try:
                data = scan_result.data or json.loads(scan_result.stdout)
                summary = data.get("summary", {})

                sections.append("## Summary")
                sections.append(
                    f"- Files: {summary.get('fileCount', '?')}  |  "
                    f"Classes: {summary.get('classCount', '?')}  |  "
                    f"Dead Code: {summary.get('deadCount', 0)}"
                )

                # High-coupling
                coupling = data.get("coupling", [])
                if coupling:
                    sections.append(f"\n## High-Coupling Classes (top {top})")
                    for i, c in enumerate(coupling[:top], 1):
                        eng = f" +{c['engine_ref']} asset refs" if c.get("engine_ref") else ""
                        sections.append(f"  {i:>2}. {c['name']} — score {c['score']}{eng}")

                # Cycles
                cycles = data.get("cycles", [])
                sections.append(f"\n## Circular Dependencies ({len(cycles)} found)")
                if cycles:
                    for cy in cycles[:20]:
                        sections.append(f"  ↻ {cy}")
                    if len(cycles) > 20:
                        sections.append(f"  ... and {len(cycles)-20} more")
                else:
                    sections.append("  ✓ None detected")

                # Dead code
                dead_nodes = data.get("deadNodes", [])
                if include_dead_code:
                    sections.append(f"\n## Dead Code / Orphan Classes ({len(dead_nodes)} found)")
                    if dead_nodes:
                        for d in dead_nodes[:30]:
                            sections.append(f"  • {d['name']}  ({Path(d['file']).name})")
                        if len(dead_nodes) > 30:
                            sections.append(f"  ... and {len(dead_nodes)-30} more")
                    else:
                        sections.append("  ✓ None detected")

            except (json.JSONDecodeError, TypeError, AttributeError):
                sections.append("## Scan Results")
                sections.append(scan_result.stdout)
        else:
            sections.append(f"## Scan Failed\n{scan_result.error_message}")

        # ── Lint ─────────────────────────────────────────────────────
        lint_result = runner.lint(profile, fmt="json")
        sections.append("\n## Anti-pattern Scan (Lint)")
        if lint_result.ok:
            try:
                issues = json.loads(lint_result.stdout) if lint_result.stdout else []
                if not issues:
                    sections.append("  ✓ No anti-patterns detected")
                else:
                    by_severity: dict[str, list] = {}
                    for iss in issues:
                        sev = iss.get("severity", "Info")
                        by_severity.setdefault(sev, []).append(iss)

                    for sev in ("Error", "Warning", "Info"):
                        grp = by_severity.get(sev, [])
                        if grp:
                            sections.append(f"  {sev} ({len(grp)}):")
                            for iss in grp[:10]:
                                loc = f"{iss.get('class_name','?')}.{iss.get('method_name','')}"
                                sections.append(
                                    f"    - {loc}: {iss.get('message','')} "
                                    f"[{iss.get('rule_id','')}]"
                                )
                            if len(grp) > 10:
                                sections.append(f"    ... and {len(grp)-10} more")
            except (json.JSONDecodeError, TypeError):
                sections.append(lint_result.stdout or "No output")
        else:
            sections.append(f"  Lint not available: {lint_result.error_message}")

        return "\n".join(sections) + confidence_footer(ConfidenceTier.HIGH, "full scan + lint")

    except Exception as e:
        return f"[inspect_architectural_health] Error: {e}"
