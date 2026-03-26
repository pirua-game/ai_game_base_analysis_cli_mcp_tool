"""
gdep-mcp/tools/suggest_test_scope.py

High-level tool: 클래스 수정 시 실행해야 할 테스트 파일 자동 산정.
runner.test_scope 래핑.
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
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect


def run(project_path: str, class_name: str, depth: int = 3) -> str:
    """
    Suggest which test files need to run when a specific class is modified.

    Performs reverse-dependency analysis (impact) on the target class,
    then filters the affected class list to test files only, based on
    engine-specific naming patterns:
      - Unity / .NET : *Test*.cs  *Tests.cs  *Spec.cs  or Tests/ directory
      - UE5          : *Spec.cpp  *Test*.cpp            or Tests/ Specs/ directory
      - C++          : *test*.cpp *spec*.cpp test_*.cpp or tests/ directory

    Use this tool WHEN:
    - User asks "what tests do I need to run after changing class X?"
    - PR review: determine the minimal test set for a change
    - CI automation: generate a targeted test-file list programmatically

    Args:
        project_path: Absolute path to the project root or Scripts/Source directory.
                      Examples: "D:/MyGame/Assets/Scripts" (Unity),
                                "F:/MyGame/Source/MyGame" (UE5)
        class_name:   The C++ or C# class name to analyze.
                      Examples: "BattleManager", "APlayerCharacter"
        depth:        Reverse-dependency tracing depth (default 3, max recommended 5).

    Returns:
        A report listing test files that should be executed, grouped with
        the affected class each test covers.
    """
    try:
        profile = detect(project_path)
        result = runner.test_scope(profile, class_name, depth=depth, fmt="json")

        if not result.ok:
            return f"[suggest_test_scope] Error: {result.error_message}"

        try:
            data = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            return result.stdout or "(No output)"

        target = data.get("target_class", class_name)
        affected_count = data.get("affected_count", 0)
        test_files = data.get("test_files", [])
        test_count = len(test_files)

        sections: list[str] = [
            f"## Test Scope: {target} (Depth: {depth})\n",
            f"- Affected classes: {affected_count}",
            f"- Test files found: {test_count}\n",
        ]

        if not test_files:
            sections.append(
                "No test files found.\n"
                f"Consider writing new tests to cover `{target}`."
            )
        else:
            sections.append("### Test files to run\n")
            for item in test_files:
                path_str = item.get("path", "")
                engine = item.get("engine", "?")
                matched = item.get("matched_class", "")
                try:
                    rel = str(Path(path_str).relative_to(Path(project_path)))
                except ValueError:
                    rel = path_str
                cover_hint = f" (covers: {matched})" if matched else ""
                sections.append(f"- `{rel}` [{engine}]{cover_hint}")

        return "\n".join(sections) + confidence_footer(ConfidenceTier.HIGH, "reverse dependency + test pattern")

    except Exception as e:
        return f"[suggest_test_scope] Error: {e}"
