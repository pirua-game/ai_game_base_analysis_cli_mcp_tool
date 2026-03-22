"""
gdep-mcp/tools/explore_class_semantics.py

High-level tool: 클래스 구조 + AI 3줄 요약 탐색.
runner.describe(summarize=True) 래퍼.
"""
from __future__ import annotations

import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.detector import detect


def run(project_path: str, class_name: str,
        summarize: bool = True, refresh: bool = False) -> str:
    """
    Explore the full semantic structure of a class, including an AI-generated summary.

    Provides fields, methods, dependencies (in/out-degree), engine asset usages,
    and an AI-generated 3-line role summary (cached for reuse).

    Use this tool to:
    - Quickly understand what an unfamiliar class does
    - Get structured context before asking deeper questions about a class
    - Prepare context for code review or refactoring tasks

    Args:
        project_path: Absolute path to the project Scripts/Source directory.
        class_name:   The class name to explore.
                      Examples: "ManagerBattle", "AHSAttributeSet"
        summarize:    If True (default), prepend an AI-generated 3-line role summary.
                      Requires LLM config (run: gdep config llm).
                      Summary is cached in .gdep_cache/summaries/.
        refresh:      If True, regenerate the summary even if cached. Default: False.

    Returns:
        Full class structure (fields, methods, refs) with optional AI summary.
    """
    try:
        profile = detect(project_path)
        result = runner.describe(profile, class_name,
                                 fmt="console",
                                 summarize=summarize,
                                 refresh=refresh)
        if result.ok:
            return result.stdout
        return f"Could not describe class '{class_name}': {result.error_message}"

    except Exception as e:
        return f"[explore_class_semantics] Error: {e}"
