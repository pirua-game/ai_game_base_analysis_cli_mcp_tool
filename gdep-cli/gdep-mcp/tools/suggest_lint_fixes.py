"""
gdep-mcp/tools/suggest_lint_fixes.py

High-level tool: lint 결과에서 fix suggestion이 있는 이슈만 모아 제안.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.detector import detect


def run(project_path: str, rule_ids: list[str] | None = None) -> str:
    """
    Run the linter and return actionable fix suggestions for detected issues.

    This tool goes beyond reporting problems — it provides concrete code
    snippets showing HOW to fix each anti-pattern found.

    Only issues that have a known fix template are returned (currently:
    UNI-PERF-001, UNI-PERF-002, UE5-BASE-001, UNI-ASYNC-001).

    Use this tool WHEN:
    - User asks "how do I fix these lint issues?"
    - After analyze_impact_and_risk reveals anti-patterns in a class
    - Pre-PR: user wants actionable cleanup steps, not just issue list

    Args:
        project_path: Absolute path to the project root or Scripts/Source directory.
        rule_ids:     Optional list of rule IDs to filter (e.g. ["UNI-PERF-001"]).
                      If None or empty, returns all fixable issues.

    Returns:
        A formatted report of issues grouped by rule, each with a code fix snippet.
    """
    try:
        profile = detect(project_path)
        lint_result = runner.lint(profile, fmt="json")

        if not lint_result.ok:
            return f"[suggest_lint_fixes] Lint failed: {lint_result.error_message}"

        try:
            issues = json.loads(lint_result.stdout) if lint_result.stdout else []
        except json.JSONDecodeError:
            issues = lint_result.data or []

        # Filter by rule_ids if provided
        if rule_ids:
            rule_set = {r.upper() for r in rule_ids}
            issues = [i for i in issues if i.get("rule_id", "").upper() in rule_set]

        # Only keep issues with a fix suggestion
        fixable = [i for i in issues if i.get("fix_suggestion")]
        unfixable_count = len(issues) - len(fixable)

        if not issues:
            return "No lint issues found."

        if not fixable:
            return (
                f"{len(issues)} issue(s) found, but none have an automatic fix template.\n"
                f"Run 'gdep lint' for full details."
            )

        sections: list[str] = [
            f"## Lint Fix Suggestions\n",
            f"- 전체 이슈: {len(issues)}개",
            f"- 자동 수정 제안 가능: {len(fixable)}개",
            f"- 수동 수정 필요: {unfixable_count}개\n",
        ]

        # Group by rule_id
        from collections import defaultdict
        by_rule: dict[str, list] = defaultdict(list)
        for issue in fixable:
            by_rule[issue.get("rule_id", "?")].append(issue)

        for rule_id, rule_issues in sorted(by_rule.items()):
            sections.append(f"### {rule_id}  ({len(rule_issues)}개 발견)\n")
            for issue in rule_issues:
                loc = issue.get("class_name", "?")
                if issue.get("method_name"):
                    loc += f".{issue['method_name']}"
                fp = issue.get("file_path", "")
                file_hint = ""
                if fp:
                    try:
                        file_hint = f"  — {Path(fp).name}"
                    except Exception:
                        file_hint = f"  — {fp}"

                sections.append(f"**{loc}**{file_hint}")
                sections.append(f"> {issue.get('message', '')}\n")
                sections.append("```")
                sections.append(issue["fix_suggestion"])
                sections.append("```\n")

        return "\n".join(sections)

    except Exception as e:
        return f"[suggest_lint_fixes] Error: {e}"
