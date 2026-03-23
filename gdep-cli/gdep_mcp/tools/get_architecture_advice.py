"""
gdep-mcp/tools/get_architecture_advice.py

High-level tool: combine scan + lint + impact and return architecture advice.
LLM call is attempted if gdep LLM is configured; otherwise returns structured
data-driven findings.
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


def run(project_path: str, focus_class: str | None = None) -> str:
    """
    Diagnose the architecture of a game project and suggest improvements.

    Combines scan (coupling/cycles/dead-code) + lint (anti-patterns) +
    impact analysis for the highest-risk class into a single report.

    If an LLM is configured (gdep config llm), the report is enriched with
    natural-language advice from the model.
    Results are cached in .gdep/cache/advice.md and reused until metrics change.

    USE THIS TOOL WHEN:
    - User asks "what is the technical debt in this project?"
    - User asks "what should I refactor first?"
    - User asks "diagnose the architecture of this project"
    - User asks "give me refactoring priorities"
    - User wants a high-level overview before starting a large change

    Args:
        project_path: Absolute path to the project root or source directory.
        focus_class:  Optional class name to center the advice around.
                      Impact analysis will pivot on this class.
                      If None, the highest-coupling class is used.

    Returns:
        A structured architecture advice report with:
        - Current state summary (classes, cycles, dead-code, lint issues)
        - Data-driven findings or LLM-generated natural-language advice
        - Impact analysis for the focus/top-coupling class
    """
    try:
        profile = detect(project_path)
        result = runner.advise(profile, focus_class=focus_class)
        if not result.ok:
            return f"[get_architecture_advice] Error: {result.error_message}"
        return result.stdout
    except Exception as e:
        return f"[get_architecture_advice] Error: {e}"
