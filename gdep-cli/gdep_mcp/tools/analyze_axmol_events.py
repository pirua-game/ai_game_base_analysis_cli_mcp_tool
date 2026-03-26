"""
gdep-mcp/tools/analyze_axmol_events.py

High-level tool: Axmol Engine EventDispatcher + schedule callback binding analysis.
"""
from __future__ import annotations

import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep.axmol_event_refs import build_event_map, format_event_result
from gdep.confidence import ConfidenceTier, confidence_footer


def run(project_path: str, class_name: str | None = None) -> str:
    """
    Scan an Axmol project for event/schedule callback bindings.

    Detects:
    - addEventListenerWithSceneGraphPriority / addEventListenerWithFixedPriority
    - CC_CALLBACK_0/1/2/3(ClassName::method, this) macro bindings
    - schedule / scheduleOnce with CC_SCHEDULE_SELECTOR
    - scheduleUpdate() registrations

    Use this tool WHEN:
    - User asks "which callbacks are registered in this Axmol class?"
    - User asks "where is this method called from in the Axmol event system?"
    - Debugging event listener leaks or unexpected callbacks
    - Reviewing which classes use the scheduler

    Args:
        project_path: Absolute path to Axmol project root or source directory (Classes/).
        class_name:   Optional -- filter results to a specific class name.
                      If None, returns all bindings found in the project.

    Returns:
        A formatted report of all event/schedule bindings grouped by class.
    """
    try:
        event_map = build_event_map(project_path)
        return format_event_result(event_map, class_name) + confidence_footer(ConfidenceTier.HIGH, "source regex")
    except Exception as e:
        return f"[analyze_axmol_events] Error: {e}"
