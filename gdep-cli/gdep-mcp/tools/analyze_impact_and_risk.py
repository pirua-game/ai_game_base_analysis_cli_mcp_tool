"""
gdep-mcp/tools/analyze_impact_and_risk.py

High-level tool: 특정 클래스 수정 전 파급 효과 + 안티패턴 통합 진단.
runner.impact + runner.lint 결합.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# gdep 패키지 경로를 sys.path에 추가 (gdep-mcp는 gdep-cli 하위에 위치)
_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.detector import detect


def run(project_path: str, class_name: str) -> str:
    """
    Analyze the impact and risks of modifying a specific class before making changes.

    Combines reverse-dependency tracing (who calls this class, what assets use it)
    with engine-specific anti-pattern scanning (lint rules).

    Use this tool BEFORE modifying or refactoring a class to understand:
    - Which classes and assets will be affected (blast radius)
    - Whether the target class already has known anti-patterns

    Args:
        project_path: Absolute path to the project root or Scripts/Source directory.
                      Examples: "D:/MyGame/Assets/Scripts" (Unity),
                                "F:/MyGame/Source/MyGame" (UE5)
        class_name:   The C++ or C# class name to analyze.
                      Examples: "BattleManager", "APlayerCharacter"

    Returns:
        A report containing:
        - Impact tree: which classes/prefabs/blueprints depend on this class
        - Lint results: anti-patterns found in or around this class
    """
    try:
        profile = detect(project_path)
        sections: list[str] = []

        # ── Impact Analysis ──────────────────────────────────────────
        impact_result = runner.impact(profile, class_name, depth=4)
        sections.append("## Impact Analysis")
        if impact_result.ok:
            sections.append(impact_result.stdout)
        else:
            sections.append(f"Impact analysis failed: {impact_result.error_message}")

        # ── Lint Analysis ────────────────────────────────────────────
        lint_result = runner.lint(profile, fmt="json")
        sections.append("\n## Lint / Anti-pattern Scan")
        if lint_result.ok:
            try:
                issues = json.loads(lint_result.stdout) if lint_result.stdout else []
                # Filter to issues related to the target class (if possible)
                related = [i for i in issues
                           if i.get("class_name", "").lower() == class_name.lower()]
                all_issues = related if related else issues

                if not all_issues:
                    sections.append("✓ No anti-patterns detected.")
                else:
                    for issue in all_issues[:20]:
                        loc = f"{issue.get('class_name','?')}.{issue.get('method_name','')}"
                        sections.append(
                            f"- [{issue.get('severity','?')}] {loc}: "
                            f"{issue.get('message','')} "
                            f"(Rule: {issue.get('rule_id','')})"
                        )
                    if len(all_issues) > 20:
                        sections.append(f"... and {len(all_issues)-20} more issues")
            except (json.JSONDecodeError, TypeError):
                sections.append(lint_result.stdout or "No lint output")
        else:
            sections.append(f"Lint failed: {lint_result.error_message}")

        return "\n".join(sections)

    except Exception as e:
        return f"[analyze_impact_and_risk] Error: {e}"
