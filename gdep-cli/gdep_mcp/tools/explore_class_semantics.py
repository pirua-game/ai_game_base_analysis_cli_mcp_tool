"""
gdep-mcp/tools/explore_class_semantics.py

High-level tool: 클래스 구조 탐색.
runner.describe 래퍼.

LLM이 설정되어 있으면(gdep config llm) 캐시된 AI 요약을 포함하고,
설정되어 있지 않으면 파싱된 클래스 구조 데이터만 반환한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect


def run(project_path: str, class_name: str,
        summarize: bool = True, refresh: bool = False) -> str:
    """
    Explore the full semantic structure of a class.

    Provides fields, methods, dependencies (in/out-degree), and engine asset usages.
    When summarize=True and an internal LLM is configured (gdep config llm),
    prepends a cached 3-line AI role summary. If LLM is not configured, returns
    the raw class structure only — the calling AI agent can summarize from context.

    Use this tool to:
    - Quickly understand what an unfamiliar class does
    - Get structured context before asking deeper questions about a class
    - Prepare context for code review or refactoring tasks

    Args:
        project_path: Absolute path to the project Scripts/Source directory.
        class_name:   The class name to explore.
                      Examples: "ManagerBattle", "AHSAttributeSet"
        summarize:    Generate AI 3-line summary if LLM is configured (gdep config llm).
                      If not configured, returns structure only. Default True.
        refresh:      Ignore cache and regenerate summary. Default False.

    Returns:
        Full class structure (fields, methods, refs) with optional AI summary.
    """
    try:
        profile = detect(project_path)

        # LLM 설정 여부 사전 확인 — stdin 대화형 설정(_configure_interactively) 방지
        llm_available = False
        if summarize:
            try:
                from gdep.llm_provider import load_config
                llm_available = load_config() is not None
            except Exception:
                pass

        result = runner.describe(profile, class_name,
                                 fmt="console",
                                 summarize=(summarize and llm_available),
                                 refresh=refresh)
        if not result.ok:
            return f"Could not describe class '{class_name}': {result.error_message}"

        return result.stdout + confidence_footer(ConfidenceTier.HIGH, "source parsing")

    except Exception as e:
        return f"[explore_class_semantics] Error: {e}"
